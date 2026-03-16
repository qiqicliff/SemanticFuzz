import asyncio
import subprocess
import tempfile
import os
import json
import time
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
import logging
from pathlib import Path

from openai import OpenAI
from global_config import global_config

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


COMMON_BUGS = {
    "bug": "report a bug",
    "crash": "crash",
    "heap_overflow": "heap-buffer-overflow"
}

@dataclass
class TestResult:
    """测试结果数据类"""
    cpu_output: str
    cuda_output: str
    cpu_error: Optional[str]
    cuda_error: Optional[str]
    cpu_execution_time: float
    cuda_execution_time: float
    is_inconsistent: bool
    inconsistency_reason: Optional[str]
    test_code: str
    timestamp: float
    test_id: Optional[str] = None

@dataclass
class OracleResult:
    """预言机结果数据类"""
    is_vulnerability: bool
    confidence: float
    analysis: str
    recommendation: str
    bug_type: Optional[str] = "unknown"

class LLMDifferentialOracle:
    """基于LLM的API差分测试预言机"""

    def __init__(self, 
                 api_key: str = "sk-KLhWFi0gK3884TSqAb59Eb6475914dE4Ab8560A83e5aEe47",
                 base_url: str = "http://192.168.131.248:30000/v1",
                 model: str = "qwen3-next-80b-a3b-instruct",
                 max_workers: int = 4,
                 timeout: int = 60,
                 coverage_on_device: Optional[str] = None):
        """
        初始化LLM差分测试预言机
        """
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self.max_workers = max_workers
        self.timeout = timeout
        self.executor = self._get_global_executor(max_workers)
        self.results_dir = Path(global_config.fuzz_result) / "differential_results"
        self.results_dir.mkdir(exist_ok=True)
        self.vuln_dir = Path(global_config.fuzz_result) / "vulns"
        self.vuln_dir.mkdir(exist_ok=True)
        self.coverage_on_device = coverage_on_device if coverage_on_device in (None, "cpu", "cuda") else None
        self._owns_executor = False
        self.total_tests = 0
        self.vulnerabilities_found = 0
        self.results_cache = {}

    _global_executors = {}

    @classmethod
    def _get_global_executor(cls, max_workers):
        """获取或创建全局线程池"""
        if max_workers not in cls._global_executors:
            cls._global_executors[max_workers] = ThreadPoolExecutor(max_workers=max_workers)
        return cls._global_executors[max_workers]

    @classmethod
    def shutdown_all_executors(cls):
        """关闭所有全局线程池"""
        for executor in cls._global_executors.values():
            executor.shutdown(wait=True)
        cls._global_executors.clear()

    async def test_code_differential(self, code: str, test_id: str = None) -> TestResult:
        """
        异步测试代码在CPU和CUDA上的差异
        """
        if test_id and test_id in self.results_cache:
            return self.results_cache[test_id]

        cpu_code = self._replace_device(code, "cpu")
        cuda_code = self._replace_device(code, "cuda")

        loop = asyncio.get_event_loop()
        cpu_future = loop.run_in_executor(
            self.executor, 
            self._execute_code_safe, 
            cpu_code,
            self.coverage_on_device == "cpu1",
            "cpu"
        )
        cuda_future = loop.run_in_executor(
            self.executor, 
            self._execute_code_safe, 
            cuda_code,
            self.coverage_on_device == "cuda1",
            "cuda"
        )

        cpu_result, cuda_result = await asyncio.gather(cpu_future, cuda_future)

        test_result = TestResult(
            cpu_output=cpu_result["output"],
            cuda_output=cuda_result["output"],
            cpu_error=cpu_result["error"],
            cuda_error=cuda_result["error"],
            cpu_execution_time=cpu_result["execution_time"],
            cuda_execution_time=cuda_result["execution_time"],
            is_inconsistent=False,
            inconsistency_reason=None,
            test_code=code,
            timestamp=time.time(),
            test_id=test_id
        )

        if test_id:
            self.results_cache[test_id] = test_result

        self.total_tests += 1
        return test_result

    def _replace_device(self, code: str, device: str) -> str:
        """替换代码中的设备设置"""
        import re
        patterns = [
            r'DEVICE\s*=\s*["\']cpu["\']',
            r'DEVICE\s*=\s*["\']cuda["\']',
            r'device\s*=\s*["\']cpu["\']',
            r'device\s*=\s*["\']cuda["\']'
        ]
        for pattern in patterns:
            if re.search(pattern, code, re.IGNORECASE):
                replacement = f'DEVICE = "{device}"'
                code = re.sub(pattern, replacement, code, flags=re.IGNORECASE)
                break
        else:
            code = f'DEVICE = "{device}"\n{code}'
        return code

    def _dump_data(self, line: str, file_name: str):
        try:
            out_dir = Path(global_config.log_path)
            out_dir.mkdir(exist_ok=True, parents=True)
            with open(out_dir / file_name, 'a', encoding='utf-8') as f:
                f.write(line + "\n")
        except Exception:
            pass

    def _match_common_bugs(self, output: str, error: str) -> Optional[str]:
        """匹配常见bug类型"""
        text = (output or "") + " " + (error or "")
        for key, val in COMMON_BUGS.items():
            if  val in text.lower():
                return key
        return None
    def _save_code_to_output_dir(self, code: str, out_dir: Path) -> str:
        out_dir.mkdir(exist_ok=True, parents=True)
        # 获取递增序号
        existing = [int(f.stem) for f in out_dir.glob("*.py") if f.stem.isdigit()]
        next_idx = max(existing) + 1 if existing else 1
        new_file = out_dir / f"{next_idx}.py"
        with open(new_file, "w", encoding="utf-8") as f:
            f.write(code)
        return f"{next_idx}.py"
    def _execute_code_safe(self, code: str, use_coverage: bool = False, device_label: str = None) -> Dict[str, Any]:
        """安全执行Python代码，增加bug标注和生命周期管理"""
        start_time = time.time()
        temp_file = None
        bug_type = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write(code)
                temp_file = f.name

            cmd = ['python', temp_file]
            # if use_coverage:
            #     cmd = ['coverage', 'run', '-p', temp_file]

            # 统一30秒超时
            timeout_sec = min(self.timeout, 30)
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout_sec,
                    env=os.environ.copy()
                )
                execution_time = time.time() - start_time

                # 匹配bug类型
                bug_type = self._match_common_bugs(result.stdout, result.stderr)
                if bug_type:
                    out_dir = Path(global_config.output_dir)
                    new_file = self._save_code_to_output_dir(code, out_dir)
                    self._dump_data(
                        f"{new_file}{{device={device_label}, returncode={result.returncode}, bug_type={bug_type}}}", 'bug.txt'
                    )

                # 记录error和crash
                if result.returncode != 0:
                    label = device_label or "unknown"
                    if result.returncode != 1:  # crash 情况
                        out_dir = Path(global_config.output_dir)
                        new_file = self._save_code_to_output_dir(code, out_dir)
                        line = f"{new_file}{{device={label}, returncode={result.returncode}}}"
                        self._dump_data(line, 'llm_runcrash.txt')

                return {
                    "output": result.stdout.strip(),
                    "error": result.stderr.strip() if result.stderr else None,
                    "execution_time": execution_time,
                    "return_code": result.returncode,
                    "bug_type": bug_type
                }
            except subprocess.TimeoutExpired:
                # 超时强制杀死进程
                try:
                    if temp_file and os.path.exists(temp_file):
                        os.unlink(temp_file)
                except Exception:
                    pass
                return {
                    "output": "",
                    "error": "Execution timeout",
                    "execution_time": timeout_sec,
                    "return_code": -1,
                    "bug_type": "timeout"
                }
            finally:
                # 资源回收
                if temp_file and os.path.exists(temp_file):
                    try:
                        os.unlink(temp_file)
                    except Exception:
                        pass
        except Exception as e:
            return {
                "output": "",
                "error": str(e),
                "execution_time": time.time() - start_time,
                "return_code": -1,
                "bug_type": "exception"
            }
    
    async def analyze_with_llm(self, test_result: TestResult) -> OracleResult:
        """
        使用LLM分析测试结果，仅返回二值置信度（0=一致，1=不一致）。
        优先进行快速规则判定，能直接确定时跳过LLM调用。
        """
        # 快速规则：运行状态/输出完全一致 → 一致(0)
        if (
            (test_result.cpu_error is None and test_result.cuda_error is None)
            and (test_result.cpu_output.strip() == test_result.cuda_output.strip())
        ):
            oracle_result = OracleResult(
                is_vulnerability=False,
                confidence=0.0,
                analysis="",
                recommendation="",
                bug_type="consistent"
            )
            test_result.is_inconsistent = False
            test_result.inconsistency_reason = ""
            return oracle_result

        # 快速规则：一边成功一边报错 → 不一致(1)
        if (test_result.cpu_error is None) ^ (test_result.cuda_error is None):
            oracle_result = OracleResult(
                is_vulnerability=True,
                confidence=1.0,
                analysis="",
                recommendation="",
                bug_type="one_side_error"
            )
            test_result.is_inconsistent = True
            test_result.inconsistency_reason = ""
            self.vulnerabilities_found += 1
            await self._record_vulnerability(test_result, oracle_result)
            return oracle_result

        # 快速规则：两边都报错且错误文本完全一致 → 一致(0)
        if (test_result.cpu_error or "") == (test_result.cuda_error or "") and (test_result.cpu_error is not None):
            oracle_result = OracleResult(
                is_vulnerability=False,
                confidence=0.0,
                analysis="",
                recommendation="",
                bug_type="both_error_same"
            )
            test_result.is_inconsistent = False
            test_result.inconsistency_reason = ""
            return oracle_result

        # 进入LLM最简判别
        prompt = self._build_analysis_prompt(test_result)
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                self.executor, self._call_llm_api, prompt
            )
            oracle_result = self._parse_llm_response(response, test_result)

            # LLM只返回0/1，无法区分细类；保留unknown或依据上下文做粗分类
            if oracle_result.is_vulnerability and oracle_result.bug_type == "unknown":
                # 简单启发：若两边都无错但输出不同 → output_diff；否则 both_error_diff
                if (test_result.cpu_error is None and test_result.cuda_error is None):
                    oracle_result.bug_type = "output_diff"
                elif (test_result.cpu_error is not None and test_result.cuda_error is not None):
                    oracle_result.bug_type = "both_error_diff"

            test_result.is_inconsistent = oracle_result.is_vulnerability
            test_result.inconsistency_reason = ""

            if oracle_result.is_vulnerability:
                await self._record_vulnerability(test_result, oracle_result)
                self.vulnerabilities_found += 1

            return oracle_result
        except Exception as e:
            logger.error(f"LLM分析失败: {e}")
            return OracleResult(
                is_vulnerability=False,
                confidence=0.0,
                analysis="",
                recommendation="",
                bug_type="unknown"
            )
    
    def _build_analysis_prompt(self, test_result: TestResult) -> str:
        """构建极简LLM判别提示词，仅返回二值置信度。"""
        cpu_out = (test_result.cpu_output or "").strip()
        cuda_out = (test_result.cuda_output or "").strip()
        cpu_err = (test_result.cpu_error or "").strip()
        cuda_err = (test_result.cuda_error or "").strip()
        code_str = (test_result.test_code or "").strip()
        prompt = f'''结合源代码，判断下面的CPU与CUDA输出和错误是否存在数值层面真正不一致，不一致为1，否则为0，输出JSON格式：{{"confidence": 0或1, "reason": "一句话原因"}}。

判断标准：
1. 如果CPU和CUDA的输出数值差异在合理范围内（如精度差异、随机数差异），并且错误类型相同（忽略临时文件路径、时间戳等变量信息），则返回0。
2. 如果输出数值差异超出了合理范围，并且错误类型不同或错误原因不同，则返回1。
3. 特别注意：如果输出数值有差异，但报错类型相同，并且不一致根因为原代码中未设置随机数种子导致输出不同，而不是API设计差异导致的bug，应返回0。

具体规则：
- 错误类型相同且错误原因相同（忽略临时文件路径、时间戳等变量信息）,0。
- 错误根源是模型/张量跨设备导致的转换问题或随机采样未设置固定种子导致的不一致,0。
- 输出差异在合理范围内（如精度差异、随机数差异）,0。
- 两边都成功且输出在合理范围内一致,0。


源码：\n{code_str}\n
CPU输出: {cpu_out[:300]}{'...' if len(cpu_out) > 300 else ''}\n
CPU错误: {cpu_err[:300]}{'...' if len(cpu_err or '') > 300 else ''}\n
CUDA输出: {cuda_out[:300]}{'...' if len(cuda_out) > 300 else ''}\n
CUDA错误: {cuda_err[:300]}{'...' if len(cuda_err or '') > 300 else ''}\n
'''
        return prompt
    
    def _call_llm_api(self, prompt: str) -> str:
        """调用LLM API"""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                stream=False,
                timeout=self.timeout,
                response_format={"type": "json_object"}
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"LLM API调用失败: {e}")
            raise
    
    def _parse_llm_response(self, response: str, test_result: TestResult) -> OracleResult:
        """解析LLM响应，仅读取confidence(0/1)。"""
        try:
            data = json.loads(response)
            conf = data.get("confidence", 0)
            conf = 1 if str(conf).strip() == "1" else 0
        except json.JSONDecodeError:
            logger.warning(f"LLM响应解析失败: {response}")
            # 尝试从文本中提取0/1
            conf = 1 if "1" in response and "0" not in response else 0

        return OracleResult(
            is_vulnerability=bool(conf),
            confidence=float(conf),
            analysis="",
            recommendation="",
            bug_type="unknown"
        )
    
    async def _record_vulnerability(self, test_result: TestResult, oracle_result: OracleResult):
        """记录发现的漏洞：分类存储并按 api_name_idx 命名（若可用）。"""
        timestamp = int(test_result.timestamp)
        bug_type = oracle_result.bug_type or "unknown"
        out_dir = self.vuln_dir / bug_type
        out_dir.mkdir(parents=True, exist_ok=True)

        base_name = test_result.test_id or f"vuln_{timestamp}_{self.vulnerabilities_found}"
        json_path = out_dir / f"{base_name}.json"
        py_path = out_dir / f"{base_name}.py"

        vulnerability_data = {
            "timestamp": test_result.timestamp,
            "test_id": test_result.test_id,
            "bug_type": bug_type,
            "cpu_output": test_result.cpu_output,
            "cuda_output": test_result.cuda_output,
            "cpu_error": test_result.cpu_error,
            "cuda_error": test_result.cuda_error,
            "cpu_execution_time": test_result.cpu_execution_time,
            "cuda_execution_time": test_result.cuda_execution_time,
            "confidence": int(oracle_result.confidence)
        }

        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(vulnerability_data, f, indent=2, ensure_ascii=False)
        with open(py_path, 'w', encoding='utf-8') as f:
            f.write(test_result.test_code)

        logger.info(f"[VULN] {bug_type} -> {base_name}")
    
    async def batch_test(self, codes: List[str], batch_size: int = 10) -> List[Tuple[str, TestResult, OracleResult]]:
        """
        批量测试代码
        
        Args:
            codes: 代码列表
            batch_size: 批处理大小
            
        Returns:
            测试结果列表: [(test_id, test_result, oracle_result), ...]
        """
        results = []
        
        for i in range(0, len(codes), batch_size):
            batch = codes[i:i + batch_size]
            batch_tasks = []
            
            for j, code in enumerate(batch):
                test_id = f"batch_{i}_{j}"
                task = self._process_single_test(code, test_id)
                batch_tasks.append(task)
            
            # 并发执行批次
            batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
            
            for result in batch_results:
                if isinstance(result, Exception):
                    logger.error(f"批次测试失败: {result}")
                else:
                    results.append(result)
        
        return results
    
    async def _process_single_test(self, code: str, test_id: str) -> Tuple[str, TestResult, OracleResult]:
        """处理单个测试"""
        test_result = await self.test_code_differential(code, test_id)
        oracle_result = await self.analyze_with_llm(test_result)
        return test_id, test_result, oracle_result
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取测试统计信息"""
        return {
            "total_tests": self.total_tests,
            "vulnerabilities_found": self.vulnerabilities_found,
            "vulnerability_rate": self.vulnerabilities_found / max(self.total_tests, 1),
            "cache_size": len(self.results_cache)
        }
    
    def clear_cache(self):
        """清理缓存"""
        self.results_cache.clear()
        logger.info("缓存已清理")
    
    async def close(self):
        """关闭预言机，清理资源"""
        # 只关闭自己创建的executor，不关闭全局共享的
        if self._owns_executor:
            self.executor.shutdown(wait=True)
        logger.info("LLM差分测试预言机已关闭")


# 异步上下文管理器支持
class AsyncLLMDifferentialOracle(LLMDifferentialOracle):
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()


# 使用示例
async def main():
    """使用示例"""
    # 创建预言机实例
    oracle = AsyncLLMDifferentialOracle()
    
    # 测试代码示例
    test_codes = [
        '''
import torch
DEVICE = "cpu"
x = torch.randn(3, 3)
y = torch.randn(3, 3)
result = torch.mm(x, y)
print(f"Result shape: {result.shape}")
print(f"Result sum: {result.sum().item()}")
''',
        '''
import torch
DEVICE = "cpu"
x = torch.tensor([1, 2, 3], dtype=torch.float32)
y = torch.tensor([4, 5, 6], dtype=torch.float32)
result = x + y
print(f"Result: {result}")
'''
    ]
    
    try:
        # 批量测试
        results = await oracle.batch_test(test_codes, batch_size=2)
        
        # 输出结果
        for test_id, test_result, oracle_result in results:
            print(f"\n=== 测试 {test_id} ===")
            print(f"是否发现漏洞: {oracle_result.is_vulnerability}")
            print(f"置信度: {oracle_result.confidence}")
            print(f"分析: {oracle_result.analysis}")
            print(f"建议: {oracle_result.recommendation}")
        
        # 输出统计信息
        stats = oracle.get_statistics()
        print(f"\n=== 统计信息 ===")
        print(f"总测试数: {stats['total_tests']}")
        print(f"发现漏洞数: {stats['vulnerabilities_found']}")
        print(f"漏洞率: {stats['vulnerability_rate']:.2%}")
        
    finally:
        await oracle.close()


if __name__ == "__main__":
    asyncio.run(main()) 
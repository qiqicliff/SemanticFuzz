import os
import itertools,utils
from tqdm import tqdm
from get_activate_param import get_active_param_constraints
from utils import tensor_type_permutations
from get_success_partition import check_param_partition_list
from concurrent.futures import ThreadPoolExecutor, as_completed
import time,pair_wise

import signal

# 定义处理单个 api_doc 的函数
# 定义主函数
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
from typing import Dict, Set, Any, Optional, Iterator
from tqdm import tqdm


try:
    import orjson as orjson
    JSON_OPTS = orjson.OPT_NON_STR_KEYS | orjson.OPT_SERIALIZE_NUMPY
except ImportError:
    import json as orjson
    JSON_OPTS = None
    print("[WARNING] orjson未安装，使用标准库json（性能较低）")

# 尝试导入布隆过滤器
try:
    from pybloom_live import ScalableBloomFilter
    BLOOM_AVAILABLE = True
except ImportError:
    BLOOM_AVAILABLE = False
    print("[WARNING] pybloom-live未安装，使用set进行去重（内存占用较高）")

import mmap
from datetime import datetime



def process_api_doc(api_doc: Dict[str, Any], timeout: int = 120) -> Optional[Dict[str, Any]]:
    """
    处理单个API文档，获取其约束和参数划分信息
    
    Args:
        api_doc: API文档字典，必须包含 'api_name' 和 'help_msg' 键
        timeout: 单个API处理超时时间（秒）
        
    Returns:
        处理结果字典，包含 api_name, init_code, constraints, param_partitions
        失败时返回 None
    """
    api_name = api_doc.get("api_name", "unknown")
    start_time = time.time()
    try:
        raw_constraints = get_active_param_constraints(api_doc["help_msg"])
        func_json = utils.get_functional_partitions_json(api_doc["help_msg"])
        result = orjson.loads(raw_constraints)
        # 后续串行处理（保持原逻辑）
        # 优化点：添加异常处理，防止 generate_and_repair 失败
        try:
            init_code = utils.generate_initial_code(api_doc['api_name'], str(result))  #generate_and_repair0302
        except Exception as e:
            print(f"[ERROR] [{api_name}] generate_and_repair 失败: {e}")
            return None
        if not init_code: 
            print(f"[ERROR] [{api_name}] generate_and_repair init_code Empty")
            return None
        # 构建输入数据
        input_data = {
            "param": result.get("param", {}),
            "api_interaction": func_json.get("api_interaction", {})
        }
        
        # # 优化点：添加空值检查，避免 pair_wise 处理无效数据
        # if not input_data["param"]:
        #     print(f"[WARNING] [{api_name}] 参数为空，跳过处理")
        #     return None
        
        # 调用 pairwise 接口
        try:
            all_json = pair_wise.pairwise_interface(input_data)
        except Exception as e:
            print(f"[ERROR] [{api_name}] pairwise_interface 失败: {e}")
            return None
        
        # 构建输出结果
        out_json = {
            "api_name": api_doc["api_name"],
            "init_code": init_code,
            "constraints": result.get("constraints", {}),
            "param_partitions": all_json.get("combinations", [])
        }
        
        # 记录处理耗时（调试用）
        elapsed = time.time() - start_time
        if elapsed > 10:  # 慢查询警告
            print(f"[SLOW] [{api_name}] 处理耗时: {elapsed:.2f}s")
        
        return out_json
        
    except TimeoutError:
        print(f"[ERROR] [{api_name}] 整体处理超时（超过{timeout}秒）")
        return None
    except orjson.JSONDecodeError as e:
        print(f"[ERROR] [{api_name}] JSON解析失败: {e}")
        return None
    except KeyError as e:
        print(f"[ERROR] [{api_name}] 缺少必要的键: {e}")
        return None
    except IndexError as e:
        print(f"[ERROR] [{api_name}] 参数列表索引错误: {e}")
        traceback.print_exc()
        return None
    except Exception as e:
        print(f"[ERROR] [{api_name}] 未预期的异常: {type(e).__name__}: {e}")
        traceback.print_exc()
        return None




class BufferedWriter:
    """
    线程安全的批量写入器，减少磁盘I/O次数
    """
    def __init__(self, output_file: str, created_file: str, 
                 buffer_size: int = 50, flush_interval: int = 60):
        self.output_file = output_file
        self.created_file = created_file
        self.buffer_size = buffer_size
        self.flush_interval = flush_interval
        
        self.buffer: list = []
        self.created_cache: Dict[str, bool] = {}
        self.last_flush_time = time.time()
        self.lock = threading.Lock()
        self.written_count = 0
        
        # 确保输出文件存在
        if not os.path.exists(output_file):
            open(output_file, 'w', encoding='utf-8').close()
    
    def write(self, result: Dict[str, Any], api_name: str) -> bool:
        """
        写入单个结果，触发条件时自动刷新
        """
        with self.lock:
            # 避免重复写入检查
            if api_name in self.created_cache:
                return False
            
            self.buffer.append(result)
            self.created_cache[api_name] = True
            
            # 触发刷新条件：缓冲区满或时间间隔到达
            current_time = time.time()
            should_flush = (
                len(self.buffer) >= self.buffer_size or 
                (current_time - self.last_flush_time) >= self.flush_interval
            )
            
            if should_flush:
                self._flush()
            
            return True
    
    def _flush(self) -> None:
        """
        执行实际写入操作，确保数据持久化
        """
        if not self.buffer:
            return
        
        try:
            # 批量写入输出文件
            with open(self.output_file, 'a', encoding='utf-8') as fout:
                if JSON_OPTS:
                    lines = [
                        orjson.dumps(r, option=JSON_OPTS).decode('utf-8') + '\n' 
                        for r in self.buffer
                    ]
                else:
                    lines = [
                        orjson.dumps(r, ensure_ascii=False) + '\n' 
                        for r in self.buffer
                    ]
                fout.writelines(lines)
                fout.flush()
                os.fsync(fout.fileno())  # 强制刷盘
            
            # 原子性更新created文件
            self._atomic_save_created()
            
            self.written_count += len(self.buffer)
            print(f"[INFO] [{datetime.now().strftime('%H:%M:%S')}] "
                  f"批量写入 {len(self.buffer)} 条，累计 {self.written_count}")
            
            self.buffer = []
            self.last_flush_time = time.time()
            
        except Exception as e:
            print(f"[ERROR] 批量写入失败: {e}")
            traceback.print_exc()
    
    def _atomic_save_created(self) -> None:
        """
        原子性保存已处理记录，防止数据损坏
        """
        temp_file = self.created_file + ".tmp"
        try:
            with open(temp_file, 'w', encoding='utf-8') as f:
                if JSON_OPTS:
                    f.write(orjson.dumps(self.created_cache, option=JSON_OPTS).decode('utf-8'))
                else:
                    orjson.dump(self.created_cache, f, ensure_ascii=False, indent=2)
            
            # 原子替换
            os.replace(temp_file, self.created_file)
        except Exception as e:
            print(f"[ERROR] 保存created文件失败: {e}")
            if os.path.exists(temp_file):
                os.remove(temp_file)
    
    def close(self) -> None:
        """
        关闭写入器，刷新剩余数据
        """
        with self.lock:
            self._flush()
            print(f"[INFO] 写入器关闭，总计写入 {self.written_count} 条记录")


def fast_read_jsonl(file_path: str, all_processed: Set[str], 
                   bloom_filter: Optional[Any] = None) -> Iterator[Dict[str, Any]]:
    """
    使用内存映射快速读取JSONL文件，惰性生成待处理API
    """
    if not os.path.exists(file_path):
        print(f"[ERROR] 输入文件不存在: {file_path}")
        return
    
    skipped = 0
    total = 0
    with open(file_path, 'rb') as f:
        # 使用内存映射加速读取
        try:
            with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                for line in iter(mm.readline, b''):
                    total += 1
                    try:
                        # 使用orjson快速解析
                        api_doc = orjson.loads(line)
                        api_name = api_doc.get("api_name")
                        
                        if not api_name:
                            continue
                        
                        # 快速去重检查
                        if bloom_filter and api_name in bloom_filter:
                            skipped += 1
                            continue
                        
                        if api_name in all_processed:
                            skipped += 1
                            continue
                        
                        yield api_doc
                        
                    except (orjson.JSONDecodeError, UnicodeDecodeError) as e:
                        continue
        except (ValueError, OSError):
            # 空文件或无法内存映射时，使用普通读取
            f.seek(0)
            for line in f:
                total += 1
                try:
                    api_doc = orjson.loads(line)
                    api_name = api_doc.get("api_name")
                    if api_name and api_name not in all_processed:
                        if not bloom_filter or api_name not in bloom_filter:
                            yield api_doc
                        else:
                            skipped += 1
                    else:
                        skipped += 1
                except:
                    continue
    
    print(f"[INFO] 文件扫描完成: 总计 {total} 条, 跳过 {skipped} 条, "
          f"待处理 {total - skipped} 条")


def load_created_file(created_file: str) -> Dict[str, bool]:
    """
    安全加载已处理记录文件
    """
    if not os.path.exists(created_file):
        return {}
    
    try:
        with open(created_file, 'rb') as f:
            data = orjson.loads(f.read())
            if isinstance(data, dict):
                return data
            return {}
    except Exception as e:
        print(f"[WARNING] 加载created文件失败: {e}，将创建新文件")
        return {}


def load_output_existing(output_file: str) -> Set[str]:
    """
    从输出文件中加载已存在的API名称
    """
    existing = set()
    if not os.path.exists(output_file):
        return existin
    try:
        with open(output_file, 'rb') as f:
            # 尝试内存映射
            try:
                with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                    for line in iter(mm.readline, b''):
                        try:
                            data = orjson.loads(line)
                            api_name = data.get("api_name")
                            if api_name:
                                existing.add(api_name)
                        except:
                            continue
            except:
                # 回退到普通读取
                f.seek(0)
                for line in f:
                    try:
                        data = orjson.loads(line)
                        api_name = data.get("api_name")
                        if api_name:
                            existing.add(api_name)
                    except:
                        continue
    except Exception as e:
        print(f"[WARNING] 读取输出文件失败: {e}")
    
    return existing


def main():
    # ==================== 配置区域 ====================
    input_file = "/home/zhourongkui/work/2025/DLF/fuzz/srcc/get_help_msg/tf_help_4403.jsonl" #help_4403
    output_file = "/home/zhourongkui/work/2025/DLF/fuzz/srcc/get_partition/tf_4403.jsonl"
    created_file = "/home/zhourongkui/work/2025/DLF/fuzz/srcc/get_partition/tf_4403_created.json"
    
    # 性能调优参数
    BUFFER_SIZE = 50          # 批量写入缓冲区大小
    FLUSH_INTERVAL = 60         # 强制刷新间隔（秒）
    MAX_WORKERS = 5#min(32, (os.cpu_count() or 4) * 4)  # 动态计算线程数
    TASK_TIMEOUT = 180        # 单个任务超时时间（秒）
    # =================================================
    
    print(f"[INFO] 启动处理流程")
    print(f"[INFO] 输入文件: {input_file}")
    print(f"[INFO] 输出文件: {output_file}")
    print(f"[INFO] 记录文件: {created_file}")
    print(f"[INFO] 最大工作线程: {MAX_WORKERS}")
    
    # 1. 加载已处理记录
    print("[INFO] 加载已处理记录...")
    created = load_created_file(created_file)
    output_existing = load_output_existing(output_file)
    all_processed = set(created.keys()) | output_existing
    
    print(f"[INFO] 已处理API数量: {len(all_processed)}")
    
    # 2. 初始化布隆过滤器（如果可用）
    bloom_filter = None
    if BLOOM_AVAILABLE and len(all_processed) > 10000:
        print("[INFO] 初始化布隆过滤器...")
        bloom_filter = ScalableBloomFilter(
            initial_capacity=len(all_processed) * 2,
            error_rate=0.001
        )
        for api_name in all_processed:
            bloom_filter.add(api_name)
    
    # 3. 初始化批量写入器
    writer = BufferedWriter(
        output_file=output_file,
        created_file=created_file,
        buffer_size=BUFFER_SIZE,
        flush_interval=FLUSH_INTERVAL
    )
    
    # 4. 统计变量
    # 统计变量
    processed_count = 0
    failed_count = 0
    skipped_count = 0
    start_time = time.time()
    
    # 创建惰性加载生成器
    api_gen = fast_read_jsonl(input_file, all_processed, bloom_filter)
    
    # 主处理循环 - 修复版本
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # 使用列表存储待处理任务
        pending_futures = {}
        active_tasks = 0
        max_pending = MAX_WORKERS * 2
        
        api_iterator = iter(api_gen)
        
        with tqdm(desc="处理API", unit="api") as pbar:
            while True:
                # 补充任务队列
                while active_tasks < max_pending:
                    try:
                        api_doc = next(api_iterator)
                        future = executor.submit(process_api_doc, api_doc)
                        pending_futures[future] = api_doc
                        active_tasks += 1
                    except StopIteration:
                        break
                
                # 如果没有待处理任务，退出循环
                if not pending_futures:
                    break
                
                # 等待完成的任务 - 修复后的正确用法
                done_futures = []
                
                # 方法1：使用 as_completed 的正确方式（推荐）
                try:
                    # as_completed 返回生成器，需要设置超时
                    for future in as_completed(pending_futures, timeout=5):
                        done_futures.append(future)
                        # 处理完一个就跳出，继续外层循环
                        break
                except TimeoutError:
                    # 没有任务在5秒内完成，继续循环
                    pass
                
                # 方法2：如果方法1不工作，使用更简单的方式
                # 直接检查哪些 future 已完成
                if not done_futures:
                    for future in list(pending_futures.keys()):
                        if future.done():
                            done_futures.append(future)
                
                # 处理已完成的任务
                for future in done_futures:
                    api_doc = pending_futures.pop(future)
                    api_name = api_doc.get("api_name", "unknown")
                    active_tasks -= 1
                    
                    try:
                        result = future.result(timeout=TASK_TIMEOUT)
                        
                        if result is None:
                            failed_count += 1
                        elif "error" in result:
                            print(f"[ERROR] [{api_name}] 处理错误: {result['error']}")
                            failed_count += 1
                        else:
                            # 写入结果
                            success = writer.write(result, api_name)
                            if success:
                                processed_count += 1
                            else:
                                skipped_count += 1
                        
                        pbar.update(1)
                        
                        # 更新进度条
                        elapsed = time.time() - start_time
                        rate = processed_count / elapsed if elapsed > 0 else 0
                        pbar.set_postfix({
                            '成功': processed_count,
                            '失败': failed_count,
                            '速率': f'{rate:.1f}/s'
                        })
                        
                    except TimeoutError:
                        print(f"[ERROR] [{api_name}] 任务执行超时")
                        failed_count += 1
                        pbar.update(1)
                    except Exception as e:
                        print(f"[ERROR] [{api_name}] 获取结果异常: {e}")
                        failed_count += 1
                        pbar.update(1)
    
    # 最终清理
    writer.close()
    
    # 输出统计报告
    total_time = time.time() - start_time
    print(f"\n{'='*50}")
    print(f"处理完成报告:")
    print(f"  总耗时: {total_time:.1f}秒")
    print(f"  成功处理: {processed_count}")
    print(f"  失败: {failed_count}")
    print(f"  重复跳过: {skipped_count}")
    print(f"  平均速率: {processed_count/total_time:.1f} API/秒" if total_time > 0 else "  N/A")
    print(f"{'='*50}")
    
    
    writer.close()

if __name__ == "__main__":
    main()



# oracle_config.py
# LLM差分测试预言机配置文件

import os
from pathlib import Path

class OracleConfig:
    """预言机配置类"""
    
    # LLM API配置
    LLM_API_KEY = "sk-KLhWFi0gK3884TSqAb59Eb6475914dE4Ab8560A83e5aEe47"
    LLM_BASE_URL = "http://192.168.131.248:30000/v1"
    LLM_MODEL = "qwen2.5-72b"
    
    # 执行配置
    MAX_WORKERS = 8  # 最大并发工作线程数
    EXECUTION_TIMEOUT = 20  # 代码执行超时时间（秒）
    LLM_TIMEOUT = 120  # LLM API调用超时时间（秒）
    
    # Fuzz测试配置
    MAX_CONCURRENT_TESTS = 8  # 最大并发测试数
    BATCH_SIZE = 20  # 批处理大小
    RESULT_QUEUE_SIZE = 1000  # 结果队列大小
    SAVE_INTERVAL = 100  # 保存间隔
    
    # 设备配置
    SUPPORTED_DEVICES = ["cpu", "cuda"]
    DEFAULT_DEVICE = "cpu"
    
    # 结果保存配置
    RESULTS_DIR = "differential_results"
    VULNERABILITY_DIR = "vulnerabilities"
    FUZZ_RESULTS_DIR = "fuzz_oracle_results"
    
    # 日志配置
    LOG_LEVEL = "INFO"
    LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # 缓存配置
    ENABLE_CACHE = True
    MAX_CACHE_SIZE = 1000
    CACHE_TTL = 3600  # 缓存生存时间（秒）
    
    @classmethod
    def get_results_dir(cls, base_path: str) -> Path:
        """获取结果目录"""
        return Path(base_path) / cls.RESULTS_DIR
    
    @classmethod
    def get_vulnerability_dir(cls, base_path: str) -> Path:
        """获取漏洞结果目录"""
        return Path(base_path) / cls.VULNERABILITY_DIR
    
    @classmethod
    def get_fuzz_results_dir(cls, base_path: str) -> Path:
        """获取Fuzz结果目录"""
        return Path(base_path) / cls.FUZZ_RESULTS_DIR
    
    @classmethod
    def create_directories(cls, base_path: str):
        """创建必要的目录"""
        dirs = [
            cls.get_results_dir(base_path),
            cls.get_vulnerability_dir(base_path),
            cls.get_fuzz_results_dir(base_path)
        ]
        
        for dir_path in dirs:
            dir_path.mkdir(parents=True, exist_ok=True)
    
    @classmethod
    def get_device_patterns(cls) -> list:
        """获取设备替换模式"""
        return [
            r'DEVICE\s*=\s*["\']cpu["\']',
            r'DEVICE\s*=\s*["\']cuda["\']',
            r'device\s*=\s*["\']cpu["\']',
            r'device\s*=\s*["\']cuda["\']',
            r'torch\.device\(["\']cpu["\']\)',
            r'torch\.device\(["\']cuda["\']\)'
        ]
    
    @classmethod
    def get_analysis_prompt_template(cls) -> str:
        """获取LLM分析提示词模板"""
        return """
你是一个专业的深度学习框架测试专家。请分析以下Python代码在CPU和CUDA设备上执行结果的差异，判断是否存在不一致漏洞。

测试代码：
```python
{test_code}
```

执行结果对比：

CPU执行结果：
- 输出: {cpu_output}
- 错误: {cpu_error}
- 执行时间: {cpu_execution_time:.3f}秒

CUDA执行结果：
- 输出: {cuda_output}
- 错误: {cuda_error}
- 执行时间: {cuda_execution_time:.3f}秒

请分析：
1. 两个结果是否存在实质性差异（不仅仅是执行时间、精度误差等正常差异）？
2. 这种差异是否表明存在设备相关的bug或实现不一致？
3. 差异是否可能影响模型的正确性和可靠性？

请以JSON格式回答：
{{
    "is_vulnerability": true/false,
    "confidence": 0.0-1.0,
    "analysis": "详细分析说明",
    "recommendation": "建议的修复或进一步测试方案"
}}

注意：
- 如果只是执行时间差异，通常不是漏洞
- 如果输出值有显著差异（超出正常浮点精度误差），可能是漏洞
- 如果错误类型不同，需要仔细分析是否影响功能
- 如果输出格式或结构不同，可能是严重漏洞
- 浮点精度差异在1e-6以内通常是正常的
"""

# 环境变量覆盖
if os.getenv("LLM_API_KEY"):
    OracleConfig.LLM_API_KEY = os.getenv("LLM_API_KEY")

if os.getenv("LLM_BASE_URL"):
    OracleConfig.LLM_BASE_URL = os.getenv("LLM_BASE_URL")

if os.getenv("LLM_MODEL"):
    OracleConfig.LLM_MODEL = os.getenv("LLM_MODEL")

if os.getenv("MAX_WORKERS"):
    OracleConfig.MAX_WORKERS = int(os.getenv("MAX_WORKERS"))

if os.getenv("BATCH_SIZE"):
    OracleConfig.BATCH_SIZE = int(os.getenv("BATCH_SIZE")) 
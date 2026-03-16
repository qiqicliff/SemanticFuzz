# global_config.py
import os
from openai import OpenAI
import logging

# 禁用烦人的HTTP日志
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

class GlobalConfig:
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self.lib_name = "torch2"
        self.work_dir = "/home/zhourongkui/work/2025/DLF/fuzz/dlf/tf/result"
        self.log_path = os.path.join(self.work_dir, "log")
        self.tested_api_path = os.path.join(self.work_dir, f"log/{self.lib_name}/tested_apis_{self.lib_name}.txt")
        self.output_dir = os.path.join(self.work_dir,f"mutated_codes_{self.lib_name}")
        self.fuzz_result = os.path.join(self.work_dir, f"result/{self.lib_name}_single")
        
        self.validate_directories()

    def validate_directories(self):
        directories_to_check = [
            os.path.join(self.work_dir, f"log/{self.lib_name}"),
            self.log_path,
            self.output_dir,
            self.fuzz_result,
            os.path.join(self.fuzz_result, "tmp")
        ]
        for path in directories_to_check:
            if not os.path.exists(path):
                os.makedirs(path, exist_ok=True)

global_config = GlobalConfig.get_instance()

# ========== 关键修复：创建带超时的客户端 ==========

# 客户端1：245服务器
client = OpenAI(
    api_key="sk-KLhWFi0gK3884TSqAb59Eb6475914dE4Ab8560A83e5aEe47", 
    base_url="http://192.168.131.245:20003/v1",
    timeout=30,  # 30秒超时
    max_retries=1  # 只重试1次
)

# 客户端2：248服务器（复用，不要每次创建）
client_ = OpenAI(
    api_key="sk-KLhWFi0gK3884TSqAb59Eb6475914dE4Ab8560A83e5aEe47", 
    base_url="http://192.168.131.248:30000/v1",
    timeout=30,  # 30秒超时
    max_retries=1
)

client_1 = OpenAI(
    api_key="sk-PWTs9teYIo9Mj0sa25671cB0Cb6a4a15B46cB6888dF55bE2", 
    base_url="http://192.168.131.248:30000/v1",
    timeout=30,  # 30秒超时
    max_retries=1
)
client_2 = OpenAI(
    api_key="sk-dssFxXqap9BtjX75239e8e256e0f4e23B28608E8E0E10978", 
    base_url="http://192.168.131.248:30000/v1",
    timeout=30,  # 30秒超时
    max_retries=1
)
# global_config.py
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
# def chat_with_timeout(client, messages, model, timeout=60):
#     """顺序执行，取消多线程"""
#     try:
#         response = client.chat.completions.create(
#             model=model,
#             messages=messages,
#             stream=False,
#             timeout=25,
#             max_tokens=1024
#         )
#         result = response.choices[0].message.content
#         return result
#     except Exception as e:
#         print(f"[ERROR] chat失败: {e}")
#         return ""
def chat_with_timeout(client, messages, model, timeout=60):
    """使用线程池实现超时控制"""
    def _call():
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                stream=False,
                timeout=25,
                max_tokens=2048
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"__ERROR__: {e}"
    
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_call)
        try:
            result = future.result(timeout=timeout)
            if result.startswith("__ERROR__"):
                print(f"[ERROR] chat失败: {result}")
                return ""
            return result
        except FutureTimeoutError:
            print(f"[WARNING] chat 超时（{timeout}秒）")
            return ""

def chat(messages, output_format=None):
    return chat_with_timeout(client, messages, "Qwen2.5-Coder-7B-Instruct", timeout=60)

def chat_(messages, output_format=None):
    return chat_with_timeout(client_, messages, "qwen3-coder-next", timeout=60)

def chat_1(messages, output_format=None):
    return chat_with_timeout(client_1, messages, "qwen3-coder-next", timeout=60)

def chat_2(messages, output_format=None):
    return chat_with_timeout(client_2, messages, "qwen3-coder-next", timeout=60)
# def chat(messages, output_format=None, timeout=60):
#     """带超时的chat函数"""
#     import signal
    
#     class TimeoutError(Exception):
#         pass
    
#     def handler(signum, frame):
#         raise TimeoutError("LLM调用超时")
    
#     # 设置信号超时（仅Unix/Linux）
#     signal.signal(signal.SIGALRM, handler)
#     signal.alarm(timeout)
    
#     try:
#         response = client.chat.completions.create(
#             model="Qwen2.5-Coder-7B-Instruct",
#             messages=messages,
#             stream=False,
#             timeout=25  # API调用级别超时
#         )
#         signal.alarm(0)  # 取消超时
#         return response.choices[0].message.content
#     except TimeoutError:
#         print(f"[WARNING] chat 超时（{timeout}秒）")
#         return ""
#     except Exception as e:
#         signal.alarm(0)
#         print(f"[ERROR] chat 失败: {e}")
#         return ""
#     finally:
#         signal.alarm(0)

# def chat_(messages, output_format=None, timeout=60):
#     """带超时的chat_函数"""
#     import signal
    
#     class TimeoutError(Exception):
#         pass
    
#     def handler(signum, frame):
#         raise TimeoutError("LLM调用超时")
    
#     signal.signal(signal.SIGALRM, handler)
#     signal.alarm(timeout)
    
#     try:
#         response = client_.chat.completions.create(
#             model="qwen3-next-80b-a3b-instruct",
#             messages=messages,
#             stream=False,
#             timeout=25
#         )
#         signal.alarm(0)
#         return response.choices[0].message.content
#     except TimeoutError:
#         print(f"[WARNING] chat_ 超时（{timeout}秒）")
#         return ""
#     except Exception as e:
#         signal.alarm(0)
#         print(f"[ERROR] chat_ 失败: {e}")
#         return ""
#     finally:
#         signal.alarm(0)
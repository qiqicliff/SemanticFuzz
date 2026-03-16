import subprocess
import os
import threading
import logging
from global_config import global_config

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 常见错误信息字典
COMMON_BUGS = {
    "bug":"report a bug",
    "crash":"crash",
    "overflow":"overflow"
}

def detect_common_bugs(error_info):
    """检测常见的错误信息"""
    for bug, keyword in COMMON_BUGS.items():
        if keyword in error_info:
            return bug
    return None

def dump_data(content, file_name, mode="w"):
    # 确保文件所在的目录存在
    dir_name = os.path.dirname(file_name)
    if not os.path.exists(dir_name):
        os.makedirs(dir_name)  # 创建所有必需的中间目录
    with open(file_name, mode) as f:
        f.write(content + "\n")  # 写入内容并添加换行符

def execute_script(py_file_path, torch_output_dir, index):
    try:
        # 直接执行Python脚本
        cmd = ["python", py_file_path]
        
        # 使用Popen进行更好的进程生命周期管理
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE,
            preexec_fn=os.setsid  # 创建新的进程组，便于管理子进程
        )
        
        try:
            # 等待进程完成，设置超时时间
            stdout, stderr = process.communicate(timeout=15)
            returncode = process.returncode
            
            # 创建类似subprocess.run返回的对象
            class ProcessResult:
                def __init__(self, returncode, stdout, stderr):
                    self.returncode = returncode
                    self.stdout = stdout
                    self.stderr = stderr
            
            res = ProcessResult(returncode, stdout, stderr)
            
        except subprocess.TimeoutExpired:
            # 超时时强制终止进程及其子进程
            try:
                os.killpg(os.getpgid(process.pid), 9)  # 终止整个进程组
            except (OSError, ProcessLookupError):
                pass  # 进程可能已经结束
            process.kill()  # 确保进程被终止
            process.wait()  # 等待进程完全结束
            raise subprocess.TimeoutExpired(cmd, 30)
        finally:
            # 确保进程被清理
            if process.poll() is None:  # 如果进程仍在运行
                try:
                    os.killpg(os.getpgid(process.pid), 9)
                except (OSError, ProcessLookupError):
                    pass
                process.kill()
                process.wait()
        

    except subprocess.TimeoutExpired:
        error_detail = "Timeout"
        dump_data(f"{os.path.abspath(py_file_path)}{{{error_detail}}}", os.path.join(torch_output_dir, "timeout.txt"), "a")
    except subprocess.CalledProcessError as e:
        error_detail = f"Error: returned {e.returncode}"
        logging.error(f"{error_detail}: {py_file_path}")
        error_info = e.stderr.decode('utf-8', errors='ignore')
        common_bug = detect_common_bugs(error_info)
        if common_bug:
            error_detail += f" ({common_bug})"
        dump_data(f"{os.path.abspath(py_file_path)}{{{error_detail}}}", os.path.join(torch_output_dir, "runerror.txt"), "a")
    except Exception as e:
        dump_data(f"{os.path.abspath(py_file_path)}{{UnexpectedError: {str(e)}}}", os.path.join(torch_output_dir, "unexpected_error.txt"), "a")
    else:
        if res.returncode != 0:
            error_detail = f"Crash: returned {res.returncode}"
            logging.error(f"{error_detail}: {py_file_path}")
            error_info = res.stderr.decode('utf-8', errors='ignore')
            
            # 检测是否为内存不足错误
            if "out of memory" in error_info.lower():
                res.returncode = -1  # 强制修改returncode为-1
                error_detail = f"Crash: returned {res.returncode} (Out of Memory)"
            
            common_bug = detect_common_bugs(error_info)
            if common_bug:
                error_detail += f" ({common_bug})"
            
            dump_data(f"{os.path.abspath(py_file_path)}{{{error_detail}}}", os.path.join(torch_output_dir, "runcrash.txt"), "a")
        else:
            dump_data(f"{os.path.abspath(py_file_path)}{{Success}}", os.path.join(torch_output_dir, "success.txt"), "a")

# 确保logging配置正确
logging.basicConfig(level=logging.INFO)

def fuzz_api(torch_output_dir, py_files, max_threads=5):
    """
    执行API模糊测试，使用线程池控制并发数量
    
    Args:
        torch_output_dir: 输出目录
        py_files: Python文件列表
        max_threads: 最大线程数，默认10
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    def execute_script_wrapper(args):
        """包装函数，用于线程池执行"""
        py_file, torch_output_dir, index = args
        execute_script(py_file, torch_output_dir, index)
    
    # 准备任务参数
    tasks = []
    for index, py_file in enumerate(py_files):
        tasks.append((py_file, torch_output_dir, index))
    
    # 使用线程池执行，控制并发数量
    with ThreadPoolExecutor(max_workers=max_threads) as executor:
        # 提交所有任务
        futures = [executor.submit(execute_script_wrapper, task) for task in tasks]
        
        # 等待所有任务完成
        for future in as_completed(futures):
            try:
                future.result()  # 获取结果，如果有异常会抛出
            except Exception as e:
                logging.error(f"线程执行异常: {e}")
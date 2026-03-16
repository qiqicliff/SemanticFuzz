import ast
import astor
import os, json, asyncio
from logger import logger
from api_call_transformer import ApiCallTransformer
from mutation_utils import mutate_and_save, mutate_and_diff, extract_api_names
from global_config import global_config
import pickle
from mutation_counter import MutationCounter
import threading
import time
from tqdm import tqdm
import subprocess
from queue import Queue
import glob,time
from typing import List
from llm_oracle import AsyncLLMDifferentialOracle
from thread_manager import get_thread_manager, check_resource_before_task, log_resource_status
from adaptive_executor import AdaptiveExecutor
from memory_optimizer import get_memory_optimizer, check_memory_before_task, optimize_memory_periodically
from batch_config import get_batch_config
# 已测试API的记录文件路径
TESTED_API_FILE = global_config.tested_api_path  

# 禁用 httpx 的日志
logging.getLogger("httpx").setLevel(logging.WARNING)
# 禁用 openai 的日志（如果使用openai库）
logging.getLogger("openai").setLevel(logging.WARNING)
# 禁用 urllib3 的日志（requests库底层）
logging.getLogger("urllib3").setLevel(logging.WARNING)
# 禁用 http.client 的日志
logging.getLogger("http.client").setLevel(logging.WARNING)

# 内存缓存
tested_apis_cache = set()

def load_tested_apis():
    """读取已测试API集合"""
    if os.path.exists(TESTED_API_FILE):
        with open(TESTED_API_FILE, 'r', encoding='utf-8') as f:
            return set(line.strip() for line in f if line.strip())
    return set()

def append_tested_apis(api_names):
    """将本批次已测试API追加写入记录文件"""
    with open(TESTED_API_FILE, 'a', encoding='utf-8') as f:
        for api in api_names:
            f.write(f"{api}\n")
async def apiFuzz_diff(api_name: str, code: str, oracle: AsyncLLMDifferentialOracle, semaphore: asyncio.Semaphore):
    """对单个API的代码进行AST变异并直接调用差分模块，不再使用旧测试模块。"""
    parsed_code = ast.parse(code)
    transformer = ApiCallTransformer(api_name)
    _ = transformer.visit(parsed_code)
    # 仅选择在单个设备上收集覆盖率，由oracle控制
    await mutate_and_diff(transformer, parsed_code, api_name, oracle, semaphore)

    # # 记录已测试API
    # save_tested_api(api_name)

def get_py_files_list(root_dir: str):
    """递归获取目录下所有.py文件路径列表"""
    py_files = []
    for base, _, files in os.walk(root_dir):
        for fn in files:
            if not fn.endswith('.py'):
                continue
            file_path = os.path.join(base, fn)
            py_files.append(file_path)
    return py_files

def read_py_files_batch(file_paths: List[str], start_idx: int, batch_size: int):
    """按批次读取Python文件，返回 {api_name: code}"""
    py_files_dict = {}
    end_idx = min(start_idx + batch_size, len(file_paths))
    
    for i in range(start_idx, end_idx):
        file_path = file_paths[i]
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            # 从文件路径中提取API名称
            api_name = os.path.splitext(os.path.basename(file_path))[0]
            py_files_dict[api_name] = content
        except Exception as e:
            logger.warning(f"跳过无法读取的文件: {file_path}, 原因: {e}")
    
    return py_files_dict

def read_py_files_recursive(root_dir: str):
    """递归读取目录下所有.py文件，返回 {api_name: code}。api_name 用文件名不带后缀表示。"""
    py_files_dict = {}
    for base, _, files in os.walk(root_dir):
        for fn in files:
            if not fn.endswith('.py'):
                continue
            file_path = os.path.join(base, fn)
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                api_name = os.path.splitext(fn)[0]
                py_files_dict[api_name] = content
            except Exception as e:
                logger.warning(f"跳过无法读取的文件: {file_path}, 原因: {e}")
    return py_files_dict

# 调用函数并打印结果
async def main_async(items: dict, coverage_device: str = "cpu", max_workers: int = 8):
    lib_name = global_config.lib_name
    os.environ['COVERAGE_FILE'] = os.path.join(global_config.fuzz_result, '.coverage')
    os.makedirs(global_config.fuzz_result, exist_ok=True)
    os.makedirs(os.path.join(global_config.fuzz_result, "tmp"), exist_ok=True)

    # 初始化线程管理器
    thread_manager = get_thread_manager(max_workers)
    thread_manager.start_monitoring()
    
    # 初始化内存优化器
    memory_optimizer = get_memory_optimizer()
    
    # 检查系统资源
    if not check_resource_before_task():
        logger.warning("系统资源不足，建议减少max_workers参数")
        max_workers = min(max_workers, 2)  # 强制减少并发数
    
    # 检查内存使用
    if not check_memory_before_task():
        logger.warning("内存使用超过限制，尝试清理内存...")
        memory_optimizer.aggressive_memory_cleanup()
        
        # 再次检查
        if not check_memory_before_task():
            logger.error("内存清理后仍超过限制，程序退出")
            return
    
    tested_apis_cache = load_tested_apis()
    start = time.time()
    # save_thread = threading.Thread(target=save_tested_apis_periodically, args=(600,))
    # save_thread.daemon = True
    # save_thread.start()

    # coverage_data_queue = Queue()

    # 使用传入的items
    counter = MutationCounter.get_instance()
    counter.reset()

    # 创建差分预言机（只在一个设备上收集覆盖率）
    oracle = AsyncLLMDifferentialOracle(max_workers=max_workers, timeout=60, coverage_on_device=coverage_device)
    semaphore = asyncio.Semaphore(max_workers)
    current_max_workers = max_workers
    
    # 记录初始资源状态
    log_resource_status()
    tested_apis = []
    try:
        # 创建任务列表
        tasks = []
        for api_name, source_code in items.items():
            
            if api_name in tested_apis_cache:
                continue
            code_norm = source_code.replace('```', '').replace('python', '')
            tested_apis.append(api_name)
            # 创建异步任务函数
            async def create_task(api_name=api_name, code=code_norm):
                return await apiFuzz_diff(api_name, code, oracle, semaphore)
            print("-----------",api_name)
            tasks.append(create_task)

        # 使用自适应执行器
        executor = AdaptiveExecutor(
            initial_max_workers=max_workers,
            min_workers=1,
            max_workers=min(max_workers * 2, 8)  # 最大不超过8
        )
        
        # 创建进度回调
        pbar = tqdm(total=len(tasks), desc="Fuzzing Progress")
        
        def progress_callback(completed, total):
            pbar.n = completed
            pbar.refresh()
        
        # 执行任务
        try:
            await executor.execute_tasks(tasks, progress_callback)
        except MemoryError as e:
            logger.error(f"内存不足，停止执行: {e}")
            # 不退出程序，而是等待内存释放
            logger.info("等待内存释放...")
            await asyncio.sleep(30)
        except Exception as e:
            logger.error(f"执行任务时发生异常: {e}")
        
        pbar.close()
        append_tested_apis(tested_apis)
        # 记录最终状态
        status = executor.get_status()
        logger.info(f"执行完成: {status}")
        
        # 优化内存
        optimize_memory_periodically()

        total_mutations = counter.get_count()
        end = time.time()
        logger.info(f"Total mutations generated: {total_mutations}")
        print(f"=============Time: {end - start}=============")

        # save_tested_apis_to_disk()

        # 合并覆盖率（如有）
        # final_coverage_output_dir = global_config.fuzz_result
        # tmp_coverage_dir = os.path.join(final_coverage_output_dir, "tmp")
        # original_cwd = os.getcwd()
        # try:
        #     os.chdir(final_coverage_output_dir)
        #     existing_files = [f for f in os.listdir(tmp_coverage_dir) if f.startswith('.coverage.child_')]
        #     existing_paths = [os.path.join(tmp_coverage_dir, f) for f in existing_files]
        #     if existing_paths:
        #         result = subprocess.run(["coverage", "combine", *existing_paths], capture_output=True, text=True)
        #         if result.returncode != 0:
        #             logger.error(f"Coverage combine failed: {result.stderr}")
        #         else:
        #             logger.info("Coverage combine successful")
        #             report_result = subprocess.run(["coverage", "report"], capture_output=True, text=True)
        #             if report_result.returncode == 0:
        #                 try:
        #                     for line in report_result.stdout.split('\n'):
        #                         if 'TOTAL' in line and '%' in line:
        #                             logger.info(f"Total Coverage: {line.strip()}")
        #                             break
        #                 except Exception:
        #                     pass
        # finally:
        #     os.chdir(original_cwd)
    finally:
        await oracle.close()
        # 停止线程管理器监控
        thread_manager.stop_monitoring()
        # 记录最终资源状态
        log_resource_status()

async def process_batch_files(seed_dir: str, coverage_device: str = "cpu", max_workers: int = 8, batch_size: int = None):
    """分批处理文件的主函数"""
    # 获取配置
    config = get_batch_config()
    if batch_size is None:
        batch_size = config.get_batch_size()
    
    # 获取所有文件路径
    logger.info(f"开始扫描种子目录: {seed_dir}")
    all_files = get_py_files_list(seed_dir)
    total_files = len(all_files)
    logger.info(f"找到 {total_files} 个Python文件")
    
    if total_files == 0:
        logger.warning("没有找到任何Python文件")
        return
    
    # 计算批次数量
    total_batches = (total_files + batch_size - 1) // batch_size
    logger.info(f"将分 {total_batches} 个批次处理，每批次 {batch_size} 个文件")
    
    # 统计信息
    total_processed = 0
    total_mutations = 0
    start_time = time.time()
    
    # 分批处理
    for batch_idx in range(total_batches):
        logger.info(f"开始处理第 {batch_idx + 1}/{total_batches} 批次")
        
        # 读取当前批次文件
        batch_start = batch_idx * batch_size
        items = read_py_files_batch(all_files, batch_start, batch_size)
        
        if not items:
            logger.warning(f"第 {batch_idx + 1} 批次没有有效文件，跳过")
            continue
        
        logger.info(f"第 {batch_idx + 1} 批次加载了 {len(items)} 个文件")
        
        # 处理当前批次
        try:
            await main_async(items, coverage_device, max_workers)
            
            # 更新统计信息
            total_processed += len(items)
            counter = MutationCounter.get_instance()
            batch_mutations = counter.get_count()
            total_mutations += batch_mutations
            
            logger.info(f"第 {batch_idx + 1} 批次完成: 处理了 {len(items)} 个文件, 生成了 {batch_mutations} 个变异")
            
            # 重置计数器为下一批次准备
            counter.reset()
            # append_tested_apis(items.keys())
            # 批次间内存清理
            memory_optimizer = get_memory_optimizer()
            memory_optimizer.optimize_memory()
            
            # 检查内存使用情况
            usage = memory_optimizer.get_memory_usage()
            logger.info(f"当前内存使用: {usage['rss_mb']:.1f}MB")
            
            # 如果内存使用过高，等待一段时间
            if config.should_cleanup_memory(usage['rss_mb']):
                logger.warning("内存使用较高，等待内存释放...")
                await asyncio.sleep(config.get_batch_wait_time())
            
        except Exception as e:
            logger.error(f"第 {batch_idx + 1} 批次处理失败: {e}")
            continue
    
    # 最终统计
    end_time = time.time()
    total_time = end_time - start_time
    
    logger.info(f"所有批次处理完成!")
    logger.info(f"总处理文件数: {total_processed}/{total_files}")
    logger.info(f"总生成变异数: {total_mutations}")
    logger.info(f"总耗时: {total_time:.2f}秒")
    logger.info(f"平均每文件耗时: {total_time/total_processed:.2f}秒" if total_processed > 0 else "无文件处理")

if __name__ == "__main__":
    # 种子目录：递归遍历
    seed_dir = os.environ.get('SEED_DIR', '/home/zhourongkui/work/2025/DLF/fuzz/result/partition_single_2508030')
    print(f"种子目录: {seed_dir}")
    
    # 覆盖率仅收集一个设备（cpu/cuda），默认cpu
    coverage_device = os.environ.get('COVERAGE_DEVICE', 'cuda')
    max_workers = int(os.environ.get('MAX_WORKERS', '5'))
    
    # 获取批次配置
    config = get_batch_config()
    batch_size = config.get_batch_size()
    
    print(f"覆盖率设备: {coverage_device}, 并发数: {max_workers}, 批次大小: {batch_size}")
    print(f"内存限制: {config.max_memory_gb}GB, 清理阈值: {config.memory_cleanup_threshold}GB")
    
    asyncio.run(process_batch_files(seed_dir, coverage_device, max_workers, batch_size))
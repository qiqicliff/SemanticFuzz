import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from global_config import chat_1,chat_2, chat_,chat

RESULT_DIR = "/home/zhourongkui/work/2025/DLF/fuzz/result/tf4403"
os.makedirs(RESULT_DIR, exist_ok=True)
STATUS_FILE = os.path.join(RESULT_DIR, "fuzz_status.json")

def gen_prompt(api_name, init_code, param_partition, api_constraint):
    """优化提示词，要求只输出核心代码片段"""
    dtype_info = {k: v for k, v in param_partition.items() if k != "api_interaction"}
    return f"""基于以下初始代码片段，为{api_name}生成核心测试代码：

{init_code}

要求：
1. 参数类型：{dtype_info}
2. 功能交互：{param_partition.get('api_interaction', '无')}
3. 语法约束：{api_constraint}

强制要求：
1. 只输出可执行的Python代码片段，禁止任何解释、注释、markdown标记
2. 代码必须简洁，只包含核心测试逻辑
3. 确保语法正确，可直接运行
4. 不要输出任何非代码内容"""

def llm_generate_code(api_name, init_code, param_partition, api_constraint):
    """生成代码，无限重试直到成功"""
    prompt = gen_prompt(api_name, init_code, param_partition, api_constraint)
    messages = [{"role": "user", "content": prompt}]
    
    while True:
        try:
            res = chat(messages)
            # 清理可能的markdown标记
            res = res.replace("```python", "").replace("```", "").strip()
            return res
        except Exception as e:
            print(f"\n[ERROR] [{api_name}] 生成失败: {e}，1秒后重试...")
            time.sleep(1)

def save_code(code, api_name, idx):
    """保存代码文件"""
    code_dir = os.path.join(RESULT_DIR, api_name)
    os.makedirs(code_dir, exist_ok=True)
    filepath = os.path.join(code_dir, f"{api_name.replace('.', '_')}_{idx}.py")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(code)
    return filepath

def load_status():
    """加载处理状态"""
    if os.path.exists(STATUS_FILE):
        try:
            with open(STATUS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {}

def save_status(status):
    """保存处理状态"""
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=2)

def print_progress(current, total, api_name, start_time):
    """打印进度条和时间统计"""
    elapsed = time.time() - start_time
    percent = current / total * 100
    bar = "█" * int(percent // 5) + "-" * (20 - int(percent // 5))
    print(f"\r[{api_name}] [{bar}] {current}/{total} ({percent:.1f}%) 耗时: {elapsed:.1f}s", end="", flush=True)

def process_api(partitions, status):
    """处理单个API，带进度条和时间统计"""
    api_name = partitions["api_name"]
    api_constraint = partitions["constraints"]
    init_code = partitions["init_code"]
    total = len(partitions["param_partitions"])
    
    # 获取已处理索引
    processed = set(status.get(api_name, {}).get("generated", []))
    to_generate = [(i, p) for i, p in enumerate(partitions["param_partitions"]) 
                   if i not in processed]
    
    if not to_generate:
        print(f"[{api_name}] 全部完成，跳过")
        return
    
    print(f"\n[{api_name}] 开始生成 {len(to_generate)}/{total} 个代码...")
    api_start = time.time()
    completed = 0
    
    with ThreadPoolExecutor(max_workers=1) as executor:
        futures = {executor.submit(llm_generate_code, api_name, init_code, p, api_constraint): i 
                   for i, p in to_generate}
        
        for future in as_completed(futures):
            idx = futures[future]
            try:
                code = future.result()
                save_code(code, api_name, idx)
                processed.add(idx)
                completed += 1
                
                # 更新状态
                status[api_name] = {"generated": sorted(processed)}
                save_status(status)
                
                # 打印进度
                print_progress(completed, len(to_generate), api_name, api_start)
            except Exception as e:
                print(f"\n[ERROR] [{api_name}] 索引{idx}失败: {e}")
    
    total_time = time.time() - api_start
    print(f"\n[{api_name}] 完成! 生成{completed}个，总耗时: {total_time:.1f}s，平均: {total_time/max(completed,1):.2f}s/个")

def main():
    status = load_status()
    print(f"[INFO] 已加载状态，{len(status)}个API")
    
    # 读取分区数据
    partitions_list = []
    with open("/home/zhourongkui/work/2025/DLF/fuzz/srcc/get_partition/tf_4403.jsonl", 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    partitions_list.append(json.loads(line))
                except:
                    pass
    
    print(f"[INFO] 共{len(partitions_list)}个API，开始处理...")
    main_start = time.time()
    
    # 多线程处理API级别
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(process_api, p, status): p for p in partitions_list}
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                print(f"\n[ERROR] API处理失败: {e}")
    
    total = time.time() - main_start
    print(f"\n[COMPLETE] 全部完成! 总耗时: {total:.1f}s")

if __name__ == "__main__":
    main()
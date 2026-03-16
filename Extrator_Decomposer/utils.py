import itertools
import json
import random
import subprocess
import sys
import ast
from typing import Dict, List, Any, Optional, Tuple

from global_config import chat_,chat_1,chat_2,chat


def tensor_type_permutations(n: int, tensor_types_dict: Dict, default: str = "default") -> List[Tuple]:
    """生成张量类型排列（不同位置不同类型）"""
    result = []
    type_list = list(tensor_types_dict.values())[0] if tensor_types_dict else []
    type_list_with_default = type_list + [default]
    
    for i in range(n):
        for value in type_list:
            n_tuple = [default] * n
            n_tuple[i] = value
            for j in range(n):
                if j != i:
                    n_tuple[j] = random.choice(type_list_with_default)
            result.append(tuple(n_tuple))
    return result


def tensor_type_permutations_same(n: int, tensor_types_dict: Dict, default: str = "default") -> List[Tuple]:
    """生成张量类型排列（两个位置相同类型）"""
    result = []
    for type_list in tensor_types_dict.values():
        positions = list(itertools.combinations(range(n), 2))
        for pos in positions:
            for value in type_list:
                n_tuple = [default] * n
                n_tuple[pos[0]] = value
                n_tuple[pos[1]] = value
                result.append(tuple(n_tuple))
    return result


def get_functional_partitions_json(api_info: str) -> Dict:
    """获取API功能分区JSON"""
    messages = [{
        "role": "user", 
        "content": f"分析以下API的关键语义信息，穷举和其他API可能存在的交互功能的一句话描述，仅输出API交互,输出为json格式，{{api_interaction：[]}}：{api_info}"
    }]
    
    try:
        response = chat_2(messages).replace("```json", "").replace("```", "")
        return json.loads(response)
    except Exception:
        return {"api_interaction": []}


def generate_initial_code(api_name: str, semantic_info: str) -> str:
    
    # 第一次尝试：标准提示
    messages = [
        {"role": "system", "content": "你是一个DL库测试代码生成专家，严格按照三步生成简洁可运行的代码。"},
        {"role": "user", "content": f"""
为API {api_name} 生成初始测试代码，严格按照以下三步结构：
1. import DL库
2. 生成输入数据
3. 调用{api_name}
只输出代码，不需要任何注释和解释，代码中必须显式包含如下完整语义：
{semantic_info}
"""}
    ]
    
    try:
        result = chat_1(messages).replace("```python", "").replace("```", "").strip()
        if result:
            return result
        else:
            print(f"[WARNING] chat_1 返回空值，尝试简化提示")
    except Exception:
        return ""
    
    # # 第二次尝试：简化提示
    # messages = [{"role": "user", "content": f"生成调用 {api_name}的代码,只给出纯代码,不需要任何注释"}]
    
    # try:
    #     result = chat(messages).replace("```python", "").replace("```", "").strip()
    #     return result if result else ""
    # except Exception:
    #     return ""


def check_code(code: str, timeout: int = 10) -> Tuple[bool, Optional[str]]:
    """检查代码语法和运行错误"""
    try:
        ast.parse(code)
    except SyntaxError as e:
        return False, f"SyntaxError: Line {e.lineno}"
    
    try:
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True, text=True, timeout=timeout
        )
        if result.returncode == 0:
            return True, None
        else:
            error = result.stderr.strip().split('\n')[-1] if result.stderr else "Runtime Error"
            return False, error
    except subprocess.TimeoutExpired:
        return False, "Timeout"
    except Exception as e:
        return False, str(e)


def repair_code(code: str, error: str, api_name: str, semantic_info: str) -> str:
    """修复代码"""
    prompt = f"""修复代码错误。只输出修复后的完整代码,不需要任何注释。
API: {api_name}
语义: {semantic_info}
错误: {error}
代码:
{code}
修复后的代码:"""
    
    messages = [
        {"role": "system", "content": "你是一个代码修复专家。"},
        {"role": "user", "content": prompt}
    ]
    print("-R-")
    try:
        return chat_2(messages).replace("```python", "").replace("```", "")
    except Exception:
        return code


def generate_and_repair(api_name: str, semantic_info: str, max_rounds: int = 2) -> str:
    """生成并修复代码"""
    # print(semantic_info)
    # semantic_str = json.dumps(semantic_info, ensure_ascii=False)
    code = generate_initial_code(api_name, semantic_info)
    # print(code)
    for _ in range(max_rounds):
        success, error = check_code(code)
        if success:
            return code
        code = repair_code(code, error, api_name, semantic_info)
    
    return code


def gen_multi_type_case(api_name: str, param_names: List[str], 
                       type_items_dict: Dict, api_constraint: str) -> str:
    """生成多类型测试用例"""
    all_types = []
    for v in type_items_dict.values():
        all_types.extend(v)
    
    chosen_types = all_types[:len(param_names)] if len(all_types) >= len(param_names) else all_types + ["default"] * (len(param_names) - len(all_types))
    param_type_map = {name: t for name, t in zip(param_names, chosen_types)}
    
    prompt = (
        f"你是DL库 API测试专家。\n"
        f"API名称: {api_name}\n"
        f"参数类型分配: {json.dumps(param_type_map, ensure_ascii=False)}\n"
        f"API约束: {api_constraint}\n"
        f"请生成一段最简洁的DL库测试代码，要求：\n"
        f"1. 每个参数类型如上，且类型不同。\n"
        f"2. 只需验证API能否被调用，无需print、注释、函数嵌套。\n"
        f"3. 只输出代码。\n"
    )
    
    messages = [{"role": "user", "content": prompt}]
    
    try:
        res = chat_(messages).strip()
        if res.startswith("```python"):
            res = res[len("```python"):].lstrip()
        if res.endswith("```"):
            res = res[:-3].rstrip()
        return res
    except Exception:
        return ""


def run_code(code: str, timeout: int = 10) -> bool:
    """运行代码并返回是否成功"""
    try:
        exec(code, {})
        return True
    except Exception:
        return False


def get_param_partitions_llm(param_dict: Dict, data_info: Dict, api_doc: Dict) -> Tuple[str, List[Dict]]:
    """
    获取参数分区列表
    
    Returns:
        (init_code, partitions)
    """
    # 提取参数信息
    params = {}
    for k in ['参数']: 
        params.update(param_dict.get(k, {}))
    
    if not params:
        return "", []
    
    # 按类型分组参数
    type2params = {}
    for param, typ in params.items():
        if typ not in type2params:
            type2params[typ] = []
        type2params[typ].append(param)
    
    # 生成类型排列
    type2perms = {}
    for typ, param_names in type2params.items():
        if typ == "others":
            continue
            
        type_items_dict = data_info.get('param_party', {}).get(typ, {})
        if not isinstance(type_items_dict, dict) or not type_items_dict:
            continue
        
        n = len(param_names)
        if n >= 2:
            # 尝试生成多类型用例
            code = gen_multi_type_case(
                api_doc["api_name"], 
                param_names, 
                type_items_dict, 
                param_dict.get("constraints", "")
            )
            
            # 根据运行结果选择排列方式
            perms = (tensor_type_permutations(n, type_items_dict) 
                    if run_code(code) 
                    else tensor_type_permutations_same(n, type_items_dict))
        else:
            perms = tensor_type_permutations(n, type_items_dict)
        
        type2perms[typ] = perms
    
    if not type2perms:
        return "", []
    
    # 生成所有组合
    all_perms = list(itertools.product(*type2perms.values()))
    p_value = data_info.get("value", {})
    
    partitions = []
    for perm_tuple in all_perms:
        partition = {"type": {}, "value": {}}
        
        for (typ, param_names), perm in zip(type2params.items(), perm_tuple):
            for param, type_ in zip(param_names, perm):
                partition["type"][param] = type_
                if typ in p_value:
                    partition["value"][param] = random.choice(p_value[typ])
        
        # 填充未指定参数
        for param in params.keys():
            if param not in partition["type"]:
                partition["type"][param] = "default_value"
        
        partitions.append(partition)
    
    # 生成初始化代码
    init_code = generate_and_repair(api_doc["api_name"], param_dict)
    
    return init_code, partitions
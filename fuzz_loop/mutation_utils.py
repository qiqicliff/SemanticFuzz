import astor
import os,copy,ast,asyncio
from mutation_manager import mutate_data
from logger import logger
import fuzz_api
from mutation_counter import MutationCounter
from global_config import global_config
# import coverage
import openai
from typing import List, Set
from api_call_transformer import ApiCallTransformer, get_full_api_name
from llm_oracle import AsyncLLMDifferentialOracle
lib_name = global_config.lib_name
RESULT_DIR = global_config.fuzz_result

def api_series_code(raw_code, target_api):
    # 提示词
    prompt = f"""
根据实际场景，推荐适合下面代码的pytorch API :{target_api.split('.')[0]}.xxx ({target_api.split('.')[0]}中实际存在且可用的api)，将上述代码中{target_api}的核心输入增加一层由{target_api.split('.')[0]}.xxx处理的逻辑，其他部分逻辑不变。
保持约束语法正确，使得程序能够正常运行，仅返回源码,清除注释，不需要其他任何内容
{raw_code}
"""
    # 初始化OpenAI客户端
    client = openai.OpenAI(
        api_key="sk-KLhWFi0gK3884TSqAb59Eb6475914dE4Ab8560A83e5aEe47",
        base_url="http://192.168.131.248:30000/v1"
    )
    LLM_MODEL = "qwen2.5-72b"  # 模型名称

    # 构造消息
    messages = [{"role": "user", "content": prompt}]
    # 调用模型
    response = client.chat.completions.create(
        model=LLM_MODEL,
        messages=messages,
        stream=False,
        timeout=30,
    )
    # 提取生成的代码
    res = response.choices[0].message.content.strip()
    if res.startswith("```python"):
        res = res[len("```python"):].lstrip()
    if res.endswith("```"):
        res = res[:-3].rstrip()
    return res

def save_transformed_code(transformed_code, filename):
    """保存变异后的代码到文件"""
    # print(transformed_code)
    with open(filename, 'w') as f:
        f.write(transformed_code)

def mutate_and_save(transformer, parsed_code, output_dir):
    transformer.mutate_id = 0
    pyfiles = []
    counter = MutationCounter.get_instance()
    printed_funcs = set()
    for idx, mutation in enumerate(transformer.mutate_list):
        # print("===========", mutation)

        api_name = mutation["api_name"]
        # 跳过所有randn生成类
        if 'randn' in api_name or 'tensor' in api_name or 'print' in api_name : 
            continue
        temp_mutation = copy.deepcopy(mutation)
        ## TODO change transformer_copy.mutate_list
        # transformer_copy = copy.deepcopy(transformer)
        try:
            mutation_list = mutate_data(temp_mutation)
            
            # print("[+] mutation_list ",mutation_list)
            for i, mutation_i in enumerate(mutation_list):
                transformer_copy = copy.deepcopy(transformer)
                tmp_code = copy.deepcopy(parsed_code)
                # print(f"[++] --------{i}-------------{mutation_i}-------- ")
                transformer_copy.mutate_list[idx] = mutation_i
                # logger.debug(f"[+] Successful! Mutating : {transformer_copy.mutate_list[idx]}")
                
                transformer_copy.is_mutate = True
                transformer_copy.mutate_list[idx]['is_mutate'] = True
                transformed_code = transformer_copy.visit(tmp_code)
                
                ########################################################################
                # API序列替换模块
                if api_name not in printed_funcs and "torch" in api_name:
                    new_code = api_series_code(astor.to_source(parsed_code),api_name)
                    # print(new_code)
                    counter.increment() # 有效测试用例计数器加1
                    j = 100 - i  
                    filename = f"{idx+1}_{j}.py"  # 包含api_name以确保文件名唯一
                    i += 1
                    save_transformed_code(new_code, os.path.join(output_dir, filename))
                    pyfiles.append(os.path.join(output_dir, filename))
                    printed_funcs.add(api_name)
                ########################################################################
                
                modified_code = astor.to_source(transformed_code, indent_with=' ' * 4, add_line_information=False)
                counter.increment() # 有效测试用例计数器加1
                filename = f"{idx+1}_{i}.py"  # 包含api_name以确保文件名唯一
                save_transformed_code(modified_code, os.path.join(output_dir, filename))
                pyfiles.append(os.path.join(output_dir, filename))
                del transformer_copy
                del tmp_code      
        except Exception as e:
            logger.error(f"[-] Mutate Filed : {transformer.api_name}: {e}")
            

    # 执行模糊测试
    fuzz_api.fuzz_api(RESULT_DIR, pyfiles)
    

async def mutate_and_diff(transformer: ApiCallTransformer,
                          parsed_code: ast.AST,
                          api_name: str,
                          oracle: AsyncLLMDifferentialOracle,
                          semaphore: asyncio.Semaphore,
                          save_threshold: int = 1) -> int:
    """
    进行AST变异并直接调用差分预言机进行测试，不落盘中间文件。
    仅在触发异常/不一致（confidence>=save_threshold）时由预言机分类保存。
    返回发现的漏洞数量。
    """
    transformer.mutate_id = 0
    counter = MutationCounter.get_instance()
    vulnerabilities_found = 0
    printed_funcs = set()

    for idx, mutation in enumerate(transformer.mutate_list):
        api_name_i = mutation["api_name"]
        if 'randn' in api_name_i or 'tensor' in api_name_i or 'print' in api_name_i or 'manual_seed' in api_name_i or 'linspace' in api_name_i:
            continue
        temp_mutation = copy.deepcopy(mutation)
        try:
            mutation_list = mutate_data(temp_mutation)
            for i, mutation_i in enumerate(mutation_list):
                transformer_copy = copy.deepcopy(transformer)
                tmp_code = copy.deepcopy(parsed_code)
                transformer_copy.mutate_list[idx] = mutation_i
                transformer_copy.is_mutate = True
                transformer_copy.mutate_list[idx]['is_mutate'] = True
                transformed_code = transformer_copy.visit(tmp_code)

                # 生成源码字符串
                modified_code = astor.to_source(transformed_code, indent_with=' ' * 4, add_line_information=False)
                counter.increment()

                # test_id 基于 api_name 与索引
                test_id = f"{api_name}_{idx+1}_{i}"

                async with semaphore:
                    test_result = await oracle.test_code_differential(modified_code, test_id)
                    oracle_result = await oracle.analyze_with_llm(test_result)
                    if int(oracle_result.confidence) >= save_threshold:
                        vulnerabilities_found += 1

                del transformer_copy
                del tmp_code
        except Exception as e:
            logger.error(f"[-] Mutate Failed : {transformer.api_name}: {e}")

    return vulnerabilities_found


def extract_api_names(parsed_code: ast.AST) -> Set[str]:
    """遍历AST提取所有调用的完整API名称集合。"""
    api_names: Set[str] = set()

    class CallVisitor(ast.NodeVisitor):
        def visit_Call(self, node: ast.Call):
            try:
                name = get_full_api_name(node.func)
                if name and name != "Unknown":
                    api_names.add(name)
            except Exception:
                pass
            self.generic_visit(node)

    CallVisitor().visit(parsed_code)
    return api_names

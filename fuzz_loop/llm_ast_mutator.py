import ast
import astor
from typing import List, Dict, Any, Optional
import random
from logger import logger
from openai import OpenAI
import copy

class LLMASTMutator(ast.NodeTransformer):
    def __init__(self, llm_client=None):
        self.llm_client = llm_client
        self.mutation_count = 0
        self.mutation_history = []
        
    def get_llm_suggestion(self, node_type: str, node_code: str) -> str:
        """使用LLM获取变异建议"""
        if not self.llm_client:
            return None
            
        prompt = f"""
        请为以下Python代码的{node_type}节点提供变异建议。
        要求：
        1. 保持代码语义正确性
        2. 增加代码的健壮性和可读性
        3. 可以添加新的功能或优化
        4. 保持代码风格一致
        5. 确保变异后的代码可以直接运行
        
        原始代码：
        {node_code}
        
        请直接返回变异后的代码，不需要解释。
        """
        
        try:
            response = self.llm_client.chat.completions.create(
                model="qwen2.5-72b",
                messages=[
                    {"role": "system", "content": "你是一个Python代码优化专家，专注于代码变异和重构。请确保生成的代码符合Python最佳实践。"},
                    {"role": "user", "content": prompt}
                ],
                stream=False
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"LLM调用失败: {str(e)}")
            return None
            
    def apply_llm_mutation(self, node: ast.AST) -> ast.AST:
        """应用LLM建议的变异"""
        try:
            # 将当前节点转换为代码
            node_code = astor.to_source(node)
            
            # 获取LLM建议
            node_type = node.__class__.__name__
            suggested_code = self.get_llm_suggestion(node_type, node_code)
            
            if suggested_code:
                # 解析建议的代码
                suggested_tree = ast.parse(suggested_code)
                if isinstance(suggested_tree.body[0], type(node)):
                    # 记录变异历史
                    self.mutation_history.append({
                        'type': node_type,
                        'original': node_code,
                        'mutated': suggested_code,
                        'count': self.mutation_count
                    })
                    return suggested_tree.body[0]
        except Exception as e:
            logger.error(f"应用LLM变异失败: {str(e)}")
        return node
        
    def visit(self, node):
        # 记录原始节点信息
        original_node = copy.deepcopy(node)
        
        # 首先尝试使用LLM进行变异
        if random.random() < 0.5:  # 50%的概率使用LLM变异
            mutated_node = self.apply_llm_mutation(node)
            if mutated_node != node:
                return mutated_node
        
        # 如果LLM变异失败或未触发，使用传统变异策略
        if isinstance(node, ast.FunctionDef):
            return self.mutate_function(node)
        elif isinstance(node, ast.If):
            return self.mutate_if_statement(node)
        elif isinstance(node, ast.While):
            return self.mutate_while_loop(node)
        elif isinstance(node, ast.For):
            return self.mutate_for_loop(node)
        elif isinstance(node, ast.Assign):
            return self.mutate_assignment(node)
        elif isinstance(node, ast.Call):
            return self.mutate_function_call(node)
        else:
            return self.generic_visit(node)
            
    def mutate_function(self, node: ast.FunctionDef) -> ast.FunctionDef:
        """对函数定义进行变异"""
        # 1. 添加新的参数
        if random.random() < 0.3:
            new_arg = ast.arg(arg=f"new_param_{self.mutation_count}", annotation=None)
            node.args.args.append(new_arg)
            
        # 2. 添加新的文档字符串
        if not node.body or not isinstance(node.body[0], ast.Expr) or not isinstance(node.body[0].value, ast.Str):
            docstring = ast.Expr(value=ast.Str(s=f"New docstring for {node.name}"))
            node.body.insert(0, docstring)
            
        # 3. 添加新的辅助函数
        if random.random() < 0.2:
            helper_func = ast.FunctionDef(
                name=f"helper_{node.name}_{self.mutation_count}",
                args=ast.arguments(args=[], defaults=[], kwonlyargs=[], kw_defaults=[], posonlyargs=[]),
                body=[ast.Return(value=ast.Num(n=42))],
                decorator_list=[],
                returns=None
            )
            node.body.append(helper_func)
            
        self.mutation_count += 1
        return node
        
    def mutate_if_statement(self, node: ast.If) -> ast.If:
        """对if语句进行变异"""
        # 1. 添加else分支
        if not node.orelse:
            else_body = [
                ast.Expr(value=ast.Call(
                    func=ast.Name(id='print', ctx=ast.Load()),
                    args=[ast.Str(s=f"Else branch {self.mutation_count}")],
                    keywords=[]
                ))
            ]
            node.orelse = else_body
            
        # 2. 添加elif分支
        if random.random() < 0.3:
            elif_condition = ast.Compare(
                left=ast.Name(id='x', ctx=ast.Load()),
                ops=[ast.Lt()],
                comparators=[ast.Num(n=10)]
            )
            elif_body = [
                ast.Expr(value=ast.Call(
                    func=ast.Name(id='print', ctx=ast.Load()),
                    args=[ast.Str(s=f"Elif branch {self.mutation_count}")],
                    keywords=[]
                ))
            ]
            node.orelse.insert(0, ast.If(test=elif_condition, body=elif_body, orelse=[]))
            
        self.mutation_count += 1
        return node
        
    def mutate_while_loop(self, node: ast.While) -> ast.While:
        """对while循环进行变异"""
        # 1. 添加计数器
        if random.random() < 0.3:
            counter_init = ast.Assign(
                targets=[ast.Name(id=f'counter_{self.mutation_count}', ctx=ast.Store())],
                value=ast.Num(n=0)
            )
            counter_increment = ast.AugAssign(
                target=ast.Name(id=f'counter_{self.mutation_count}', ctx=ast.Store()),
                op=ast.Add(),
                value=ast.Num(n=1)
            )
            node.body.insert(0, counter_init)
            node.body.append(counter_increment)
            
        # 2. 添加break条件
        if random.random() < 0.3:
            break_condition = ast.If(
                test=ast.Compare(
                    left=ast.Name(id=f'counter_{self.mutation_count}', ctx=ast.Load()),
                    ops=[ast.GtE()],
                    comparators=[ast.Num(n=100)]
                ),
                body=[ast.Break()],
                orelse=[]
            )
            node.body.append(break_condition)
            
        self.mutation_count += 1
        return node
        
    def mutate_for_loop(self, node: ast.For) -> ast.For:
        """对for循环进行变异"""
        # 1. 添加enumerate
        if random.random() < 0.3:
            node.target = ast.Tuple(
                elts=[node.target, ast.Name(id=f'index_{self.mutation_count}', ctx=ast.Store())],
                ctx=ast.Store()
            )
            node.iter = ast.Call(
                func=ast.Name(id='enumerate', ctx=ast.Load()),
                args=[node.iter],
                keywords=[]
            )
            
        # 2. 添加else分支
        if not node.orelse:
            else_body = [
                ast.Expr(value=ast.Call(
                    func=ast.Name(id='print', ctx=ast.Load()),
                    args=[ast.Str(s=f"Loop completed {self.mutation_count}")],
                    keywords=[]
                ))
            ]
            node.orelse = else_body
            
        self.mutation_count += 1
        return node
        
    def mutate_assignment(self, node: ast.Assign) -> ast.Assign:
        """对赋值语句进行变异"""
        # 1. 添加类型注解
        if random.random() < 0.3:
            for target in node.targets:
                if isinstance(target, ast.Name):
                    target.annotation = ast.Name(id='int', ctx=ast.Load())
                    
        # 2. 添加注释
        if random.random() < 0.3:
            comment = ast.Expr(value=ast.Str(s=f"Assignment {self.mutation_count}"))
            return [comment, node]
            
        self.mutation_count += 1
        return node
        
    def mutate_function_call(self, node: ast.Call) -> ast.Call:
        """对函数调用进行变异"""
        # 1. 添加关键字参数
        if random.random() < 0.3:
            new_keyword = ast.keyword(
                arg=f'param_{self.mutation_count}',
                value=ast.Num(n=42)
            )
            node.keywords.append(new_keyword)
            
        # 2. 添加位置参数
        if random.random() < 0.3:
            new_arg = ast.Num(n=self.mutation_count)
            node.args.append(new_arg)
            
        self.mutation_count += 1
        return node
        
    def get_mutation_history(self) -> List[Dict[str, Any]]:
        """获取变异历史"""
        return self.mutation_history
        
    def reset(self):
        """重置变异器状态"""
        self.mutation_count = 0
        self.mutation_history = []

def create_llm_client(api_key: str, base_url: str) -> OpenAI:
    """创建LLM客户端"""
    return OpenAI(api_key=api_key, base_url=base_url)

def mutate_code(code: str, llm_client=None) -> str:
    """对Python代码进行变异"""
    try:
        # 解析代码
        tree = ast.parse(code)
        
        # 创建变异器
        mutator = LLMASTMutator(llm_client)
        
        # 应用变异
        mutated_tree = mutator.visit(tree)
        
        # 生成变异后的代码
        mutated_code = astor.to_source(mutated_tree)
        
        return mutated_code
    except Exception as e:
        logger.error(f"代码变异失败: {str(e)}")
        return code

# 使用示例
if __name__ == "__main__":
    # 创建LLM客户端
    llm_client = create_llm_client(
        api_key="sk-KLhWFi0gK3884TSqAb59Eb6475914dE4Ab8560A83e5aEe47",
        base_url="http://192.168.131.248:30000/v1"
    )
    
    # 示例代码
    test_code = """
def calculate_sum(a, b):
    result = a + b
    return result

if x > 0:
    print("Positive")
    
for i in range(10):
    print(i)
"""
    
    # 进行变异
    mutated_code = mutate_code(test_code, llm_client)
    print("变异后的代码:")
    print(mutated_code)
    
    # 打印变异历史
    mutator = LLMASTMutator(llm_client)
    print("\n变异历史:")
    for mutation in mutator.get_mutation_history():
        print(f"类型: {mutation['type']}")
        print(f"原始代码:\n{mutation['original']}")
        print(f"变异后代码:\n{mutation['mutated']}")
        print("-" * 50) 
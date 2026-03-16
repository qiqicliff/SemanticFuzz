import ast
import astor
import copy
import psutil
import sys
from logger import logger
from icecream import ic

# 常量定义
MAX_CONSTANT_SIZE = 1000  # 最大常量大小限制
MAX_MEMORY_GB = 10  # 最大内存使用限制（GB）
MAX_MEMORY_BYTES = MAX_MEMORY_GB * 1024 * 1024 * 1024  # 转换为字节

def _is_simple_literal(node):
    if isinstance(node, (ast.Constant, ast.Num, ast.Str, ast.Bytes)):
        return True
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return all(_is_simple_literal(e) for e in node.elts)
    if isinstance(node, ast.Dict):
        return all(_is_simple_literal(k) and _is_simple_literal(v) for k, v in zip(node.keys, node.values))
    return False

def _safe_literal_eval(node):
    try:
        if _is_simple_literal(node):
            return ast.literal_eval(node)
    except Exception:
        return None
    return None

def _check_memory_usage():
    """检查当前内存使用情况，如果超过限制则抛出异常"""
    try:
        process = psutil.Process()
        memory_info = process.memory_info()
        if memory_info.rss > MAX_MEMORY_BYTES:
            raise MemoryError(f"内存使用超过限制: {memory_info.rss / (1024**3):.2f}GB > {MAX_MEMORY_GB}GB")
    except Exception as e:
        logger.warning(f"内存检查失败: {e}")
        # 如果无法检查内存，继续执行但记录警告

def _is_constant_too_large(node):
    """检查常量是否过大，避免处理巨型数据结构"""
    try:
        if isinstance(node, (ast.List, ast.Tuple)):
            return len(node.elts) > MAX_CONSTANT_SIZE
        elif isinstance(node, ast.Dict):
            return len(node.keys) > MAX_CONSTANT_SIZE
        elif isinstance(node, ast.Str):
            return len(node.s) > MAX_CONSTANT_SIZE
        elif isinstance(node, ast.Constant):
            if isinstance(node.value, (list, tuple)):
                return len(node.value) > MAX_CONSTANT_SIZE
            elif isinstance(node.value, dict):
                return len(node.value) > MAX_CONSTANT_SIZE
            elif isinstance(node.value, str):
                return len(node.value) > MAX_CONSTANT_SIZE
        return False
    except Exception:
        # 如果检查过程中出错，认为是大常量，避免处理
        return True

def _safe_ast_operation(func, *args, **kwargs):
    """安全执行AST操作，遇到错误时回退"""
    try:
        _check_memory_usage()
        return func(*args, **kwargs)
    except Exception as e:
        logger.warning(f"AST操作失败，跳过节点: {e}")
        return None

def get_full_api_name(node):
    """
    递归获取完整的 API 名称，包括模块名和方法名。
    """
    if isinstance(node, ast.Attribute):
        # 如果是属性访问，递归获取前缀
        prefix = get_full_api_name(node.value)
        return f"{prefix}.{node.attr}"
    elif isinstance(node, ast.Name):
        # 如果是直接的名称，返回名称
        return node.id
    else:
        # 如果无法识别，返回 "Unknown"
        return "Unknown"

# 创建一个AST节点变换器类
class ApiCallTransformer(ast.NodeTransformer):
    def __init__(self,api_name):
        self.mutate_list = []
        self.mutate_id = 0
        self.is_mutate = False
        self.api_name = api_name

            
    def visit(self, node):
        # 使用安全操作包装，遇到错误时回退
        return _safe_ast_operation(self._visit_impl, node) or node
    
    def _visit_impl(self, node):
        # print("Visiting node:", node.__class__.__name__)
        if isinstance(node, ast.Assign):
            if isinstance(node.value, ast.Call):
                # print("Found Call node")
                tmp_node = ast.Assign(targets=node.targets, value=self.visit_Call(node.value))
                # return self.visit_Call(node.value)  # 注意这里传入的是 node.value
                return tmp_node
            elif isinstance(node.value, (ast.Num, ast.Str, ast.Dict, ast.List, ast.Tuple, ast.Constant)):
                return self.visit_Assign(node)  # 注意这里传入的是 node.value
            else:
                return self.generic_visit(node)
        elif isinstance(node, ast.Expr):
            # ic(ast.dump(node))
            if isinstance(node.value, ast.Call):
                # print("Found Call node")
                tmp_node = ast.Expr(value=self.visit_Call(node.value))
                # return self.visit_Call(node.value)  # 注意这里传入的是 node.value
                return tmp_node
            elif isinstance(node.value, (ast.Num, ast.Str, ast.Dict, ast.List, ast.Constant)):
                return self.visit_Assign(node)  # 注意这里传入的是 node.value
            else:
                return self.generic_visit(node)
        else:
            return self.generic_visit(node)

    def visit_Assign(self, node):
        # 使用安全操作包装
        return _safe_ast_operation(self._visit_Assign_impl, node) or node
    
    def _visit_Assign_impl(self, node):
        # 检查赋值的值是否为基本数值
        if isinstance(node.value, (ast.Num, ast.Str, ast.Dict, ast.List, ast.Tuple, ast.Constant)):
            # 检查常量是否过大，如果过大则跳过处理
            if _is_constant_too_large(node.value):
                logger.warning(f"跳过过大的常量节点: {type(node.value).__name__}")
                return node
                
            api_name = f"assig_{self.api_name}"  # 赋值操作的api_name可以设为"assignment"
            new_targets = []
            for target in node.targets:
                if isinstance(target, ast.Name):
                    # 对于单个变量名，我们直接存储变异信息
                    if not self.is_mutate:
                        # self.is_mutate为False，将变异点信息存起来
                        src_value = None
                        targ_value = None
                        try:
                            if isinstance(node.value, ast.Num):
                                src_value = node.value.n
                                targ_value = node.value.n
                            elif isinstance(node.value, ast.Str):
                                src_value = node.value.s
                                targ_value = node.value.s
                            elif isinstance(node.value, ast.List):
                                src_value = [(_safe_literal_eval(elt) if _safe_literal_eval(elt) is not None else None) for elt in node.value.elts]
                                targ_value = [(_safe_literal_eval(elt) if _safe_literal_eval(elt) is not None else None) for elt in node.value.elts]
                            elif isinstance(node.value, ast.Dict):
                                src_value = {}
                                targ_value = {}
                                for key, value in zip(node.value.keys, node.value.values):
                                    k_v = _safe_literal_eval(key)
                                    v_v = _safe_literal_eval(value)
                                    src_value[k_v] = v_v
                                    targ_value[k_v] = v_v
                            elif isinstance(node.value, ast.Tuple):
                                src_value = tuple((_safe_literal_eval(elt) if _safe_literal_eval(elt) is not None else None) for elt in node.value.elts)
                                targ_value = tuple((_safe_literal_eval(elt) if _safe_literal_eval(elt) is not None else None) for elt in node.value.elts)
                            elif isinstance(node.value, ast.Constant):
                                src_value = node.value.value
                                targ_value = node.value.value

                            mutation_info = {
                                'id': self.mutate_id,
                                'api_name': api_name,
                                'src_index':-1,
                                'src': src_value,
                                'src_kw': target.id,  # 存储变量名
                                'src_type': type(src_value),
                                'targ': targ_value,
                                'targ_type': type(targ_value),
                                'is_mutate': self.is_mutate
                            }
                            self.mutate_list.append(mutation_info)
                            self.mutate_id += 1
                        except Exception as e:
                            logger.warning(f"处理赋值节点时出错，跳过: {e}")
                            continue
                    elif self.is_mutate:
                        # self.is_mutate为True，将变异点参数设置为变异值
                        try:
                            if self.mutate_list[self.mutate_id]['is_mutate']:
                                mutation_info = self.mutate_list[self.mutate_id]
                                if isinstance(node.value, ast.Num):
                                    new_value = ast.Num(n=mutation_info['targ'])
                                elif isinstance(node.value, ast.Str):
                                    new_value = ast.Str(s=mutation_info['targ'])
                                elif isinstance(node.value, ast.List):
                                    new_elts = [ast.Constant(elt) for elt in mutation_info['targ']]
                                    new_value = ast.List(elts=new_elts, ctx=node.value.ctx)
                                elif isinstance(node.value, ast.Dict):
                                    keys = [ast.Constant(key) for key in mutation_info['targ'].keys()]
                                    values = [ast.Constant(value) for value in mutation_info['targ'].values()]
                                    new_value = ast.Dict(keys=keys, values=values, ctx=ast.Load())
                                elif isinstance(node.value, ast.Constant):
                                    new_value = ast.Constant(value=mutation_info['targ'])
                                else:
                                    new_value = node.value
                                node.value = new_value
                                self.mutate_id += 1
                            else:
                                self.mutate_id += 1
                        except Exception as e:
                            logger.warning(f"应用变异时出错，跳过: {e}")
                            self.mutate_id += 1
            return node
        elif isinstance(node.value, ast.Call):  # 检查是否是API调用
            # 如果是API调用，则不修改
            pass
        else:
            # 其他情况，可能是变量赋值或复杂的表达式，这里我们选择不修改
            pass
        return node


    def visit_Call(self, node):
        # 使用安全操作包装
        return _safe_ast_operation(self._visit_Call_impl, node) or node
    
    def _visit_Call_impl(self, node):
        # 获取被调用的函数或方法的完整名称
        api_name = get_full_api_name(node.func)
        # 变异参数
        new_args = []
        for index, arg in enumerate(node.args):
            # print(f"====={index}=====")
            if isinstance(arg, ast.Name):
                # 赋值右边为基本数据类型的变量，会在此被遍历
                # 即使是变量，也加入变异点
                src_value = arg.id
                targ_value = arg.id
                mutation_info = {
                    'id': self.mutate_id,
                    'api_name': api_name,
                    'src_index': index,
                    'src': src_value,
                    'src_kw': arg.id,
                    'src_type': type(src_value),
                    'targ': targ_value,
                    'targ_type': type(targ_value),
                    'is_mutate': self.is_mutate
                }
                self.mutate_list.append(mutation_info)
                self.mutate_id += 1
                # new_args.append(arg)
                new_args.append(arg)
            elif isinstance(arg, ast.Call):
                # 如果参数本身是一个函数调用，递归处理
                # new_arg = self.visit_Call(arg)
                new_arg = self.visit(arg)
                # ic(ast.dump(arg))
                new_args.append(new_arg)
            else:
                # 其他类型的参数，直接变异
                # print(arg, isinstance(arg, ast.Num) and not self.is_mutate)
                if isinstance(arg, (ast.Num, ast.Str,ast.Dict,ast.List, ast.Tuple, ast.Constant)) and not self.is_mutate: # self.is_mutate为False，将变异点信息存起来
                    # 检查常量是否过大，如果过大则跳过处理
                    if _is_constant_too_large(arg):
                        logger.warning(f"跳过过大的参数常量: {type(arg).__name__}")
                        new_args.append(arg)
                        continue
                        
                    # --------------------------------------- mutate ---------------------------------------
                    try:
                        arg_type = ''
                        if isinstance(arg, ast.Num):
                            src_value = arg.n
                            targ_value = arg.n
                        # 对于Str节点，我们可以根据需要进行处理，这里只是简单地复制
                        elif isinstance(arg, ast.Str):
                            # new_arg = ast.Str(s=arg.s)
                            src_value = arg.s
                            targ_value = arg.s
                            # print("[+] 1_Str: ", arg.s)
                        elif isinstance(arg, ast.List) :
                            # src_value = list(ast.unparse(arg)) 
                            # targ_value = list(ast.unparse(arg))
                            src_value = targ_value = [ast.literal_eval(elt) for elt in arg.elts]
                            # print("[+] 1_List: ", list(src_value), type(arg))
                        elif isinstance(arg, ast.Dict):
                            # new_arg = ast.Dict(s=arg.ctx)
                            # new_values = [self.mutate_arg(value) for value in arg.values]
                            src_value = {}
                            targ_value = {}
                            for key, value in zip(arg.keys, arg.values):
                                # 这里假设 key 和 value 都是可以直接评估的表达式
                                # 如果它们是 ast 节点，您可能需要进一步处理它们
                                src_value[ast.literal_eval(key)] = ast.literal_eval(value)
                                targ_value[ast.literal_eval(key)] = ast.literal_eval(value)
                            # arg_type = type(arg)
                            # print("[+] 1_Dict: ", src_value, type(src_value))
                        elif isinstance(arg, ast.Tuple):
                            src_value = tuple(ast.literal_eval(elt)  if isinstance(elt, (ast.Constant, ast.Num, ast.Str)) else elt for elt in arg.elts)
                            targ_value = tuple(ast.literal_eval(elt)  for elt in arg.elts)
                        # 对于Constant节点，我们增加其值
                        elif isinstance(arg, ast.Constant):
                            # new_arg = ast.Constant(value=arg.value)
                            src_value = arg.value
                            targ_value = arg.value
                        else:
                            src_value = None
                            targ_value = None
                        # --------------------------------------- mutate ---------------------------------------    
                        # if not arg_type:
                        #     arg_type = type(src_value)
                        mutation_info = {
                            'id': self.mutate_id,
                            'api_name': api_name,
                            'src_index':index,
                            'src': src_value,
                            'src_kw': '',
                            'src_type': type(src_value),
                            'targ': targ_value,
                            'targ_type': type(targ_value),
                            'is_mutate': self.is_mutate
                        }
                        self.mutate_list.append(mutation_info)
                        self.mutate_id += 1
                    except Exception as e:
                        logger.warning(f"处理参数时出错，跳过: {e}")
                        new_args.append(arg)
                        continue
                    
                    
                elif isinstance(arg, (ast.Num, ast.Str,ast.Dict,ast.List, ast.Tuple, ast.Constant)) and self.is_mutate and self.mutate_list[self.mutate_id]['is_mutate']: #self.is_mutate 为True且self.mutate_list['is_mutate']为True,将该变异点参数设置为变异值
                    # new_arg = ast.Num(self.mutate_list[self.mutate_id]['targ'])
                    # 根据mutate_list中记录的变异值进行赋值
                    # --------------------------------------- fuzhi ---------------------------------------
                    try:
                        if isinstance(arg, ast.Num):
                            new_arg = ast.Num(n=self.mutate_list[self.mutate_id]['targ'])
                        elif isinstance(arg, ast.Str):
                            new_arg = ast.Str(s=self.mutate_list[self.mutate_id]['targ'])
                            # print("[+] Str: ", self.mutate_list[self.mutate_id]['targ'])
                        elif isinstance(arg, ast.List):
                            # new_arg = ast.List(self.mutate_list[self.mutate_id]['targ'])
                            new_elts = [ast.Constant(elt) for elt in self.mutate_list[self.mutate_id]['targ']]  # 使用 arg.elts
                            new_arg = ast.List(elts=new_elts, ctx=arg.ctx) 
                            # print("[+] 2_List: ", new_elts)
                        elif isinstance(arg, ast.Dict):
                            keys = [ast.Constant(key) for key in self.mutate_list[self.mutate_id]['targ'].keys()]
                            values = [ast.Constant(value) for value in self.mutate_list[self.mutate_id]['targ'].values()]
                            
                            new_arg = ast.Dict(keys=keys, values=values, ctx=ast.Load())
                            # print("[+] 2_Dict: ", new_arg, self.mutate_list[self.mutate_id]['targ'])
                        elif isinstance(arg, ast.Tuple):
                            new_elts = [ast.Constant(elt) for elt in self.mutate_list[self.mutate_id]['targ']]
                            new_arg = ast.Tuple(elts=new_elts, ctx=arg.ctx)
                        elif isinstance(arg, ast.Constant):
                            new_arg = ast.Constant(value=self.mutate_list[self.mutate_id]['targ'])
                        else:
                            new_arg = arg
                        # --------------------------------------- fuzhi ---------------------------------------    
                            
                        # ic('[+] AM: ', self.mutate_list[self.mutate_id]['targ'])
                        self.mutate_id += 1
                    except Exception as e:
                        logger.warning(f"应用参数变异时出错，跳过: {e}")
                        new_arg = arg
                        self.mutate_id += 1
                elif isinstance(arg, (ast.Num, ast.Str,ast.Dict,ast.List, ast.Tuple, ast.Constant)) and self.is_mutate and not self.mutate_list[self.mutate_id]['is_mutate'] :
                    new_arg = arg
                    self.mutate_id += 1  ## 即使不变异，但是
                else:
                    new_arg = arg
                if self.is_mutate:
                    new_args.append(new_arg)
                else :
                    new_args.append(arg)

        # 变异关键字参数
        new_keywords = []
        for kw in node.keywords:
            if isinstance(kw.value, ast.Call):
                # 递归处理API调用
                # ic("[---KW_api---]")
                new_value = self.visit_Call(kw.value)
                new_kw = ast.keyword(arg=kw.arg, value=new_value)
                # if self.is_mutate:
                #     new_keywords.append(new_kw)
                # else:
                #     new_keywords.append(kw)
            elif isinstance(kw.value, (ast.Num, ast.Str, ast.Dict, ast.List, ast.Tuple, ast.Constant)) and not self.is_mutate:  # self.is_mutate为False，将变异点信息存起来
                # 检查常量是否过大，如果过大则跳过处理
                if _is_constant_too_large(kw.value):
                    logger.warning(f"跳过过大的关键字参数常量: {type(kw.value).__name__}")
                    new_keywords.append(kw)
                    continue
                    
                # --------------------------------------- mutate ---------------------------------------      
                try:
                    # 变异数值类型的关键字参数
                    if isinstance(kw.value, ast.Num):
                        src_value = kw.value.n
                        targ_value = kw.value.n  # 根据需要进行变异
                    elif isinstance(kw.value, ast.Str):
                        src_value = kw.value.s
                        targ_value = kw.value.s  # 字符串变异可以根据需要进行修改
                    elif isinstance(kw.value, ast.List):
                        src_value = [ast.literal_eval(elt) for elt in kw.value.elts]
                        targ_value = [ast.literal_eval(elt) for elt in kw.value.elts]  # 根据需要进行变异
                    elif isinstance(kw.value, ast.Dict):
                        src_value = {}
                        targ_value = {}
                        for key, value in zip(kw.value.keys, kw.value.values):
                            src_value[ast.literal_eval(key)] = ast.literal_eval(value)
                            targ_value[ast.literal_eval(key)] = ast.literal_eval(value)  # 根据需要进行变异
                    elif isinstance(kw.value, ast.Tuple):
                        src_value = tuple(ast.literal_eval(elt) for elt in kw.value.elts)
                        targ_value = tuple(ast.literal_eval(elt) for elt in kw.value.elts)
                    elif isinstance(kw.value, ast.Constant):
                        src_value = kw.value.value
                        targ_value = kw.value.value
                    else:
                        src_value = None
                        targ_value = None
                    # --------------------------------------- mutate ---------------------------------------        
                    mutation_info = {
                        'id': self.mutate_id,
                        'api_name': api_name,
                        'src_index':-1,
                        'src': src_value,
                        'src_kw': kw.arg,
                        'src_type': type(src_value),
                        'targ': targ_value,
                        'targ_type': type(targ_value),
                        'is_mutate': self.is_mutate
                    }
                    self.mutate_list.append(mutation_info)
                    self.mutate_id += 1
                except Exception as e:
                    logger.warning(f"处理关键字参数时出错，跳过: {e}")
                    new_keywords.append(kw)
                    continue
            elif isinstance(kw.value, (ast.Num, ast.Str, ast.Dict, ast.List, ast.Tuple, ast.Constant)) and self.is_mutate and self.mutate_list[self.mutate_id]['is_mutate']:  # self.is_mutate 为True且self.mutate_list['is_mutate']为True,将该变异点参数设置为变异值
                # --------------------------------------- fuzhi ---------------------------------------'
                try:
                    # 根据mutate_list中记录的变异值进行赋值
                    if isinstance(kw.value, ast.Num):
                        new_value = ast.Num(n=self.mutate_list[self.mutate_id]['targ'])
                    elif isinstance(kw.value, ast.Str):
                        new_value = ast.Str(s=self.mutate_list[self.mutate_id]['targ'])
                    elif isinstance(kw.value, ast.List):
                        new_elts = [ast.Constant(elt) for elt in self.mutate_list[self.mutate_id]['targ']]
                        new_value = ast.List(elts=new_elts, ctx=kw.value.ctx)
                    elif isinstance(kw.value, ast.Dict):
                        keys = [ast.Constant(key) for key in self.mutate_list[self.mutate_id]['targ'].keys()]
                        values = [ast.Constant(value) for value in self.mutate_list[self.mutate_id]['targ'].values()]
                        new_value = ast.Dict(keys=keys, values=values, ctx=ast.Load())
                    elif isinstance(kw.value, ast.Tuple):
                        new_elts = [ast.Constant(elt) for elt in self.mutate_list[self.mutate_id]['targ']]
                        new_value = ast.Tuple(elts=new_elts, ctx=kw.value.ctx)
                    elif isinstance(kw.value, ast.Constant):
                        new_value = ast.Constant(value=self.mutate_list[self.mutate_id]['targ'])
                    else:
                        new_value = kw.value
                    # --------------------------------------- fuzhi ---------------------------------------  
                    new_kw = ast.keyword(arg=kw.arg, value=new_value)
                    # ic('[+] KWAM: ', self.mutate_list[self.mutate_id]['src_kw'], self.mutate_list[self.mutate_id]['targ'])
                    self.mutate_id += 1
                except Exception as e:
                    logger.warning(f"应用关键字参数变异时出错，跳过: {e}")
                    new_kw = kw
                    self.mutate_id += 1
            elif isinstance(kw.value, (ast.Num, ast.Str, ast.Dict, ast.List, ast.Tuple, ast.Constant)) and self.is_mutate and not self.mutate_list[self.mutate_id]['is_mutate']:
                new_kw = kw
                self.mutate_id += 1
            else:
                new_kw = kw
            if self.is_mutate:
                new_keywords.append(new_kw)
            else:
                new_keywords.append(kw)

        # 回写变异后的参数到node
        if self.is_mutate:
            node.args = new_args
            node.keywords = new_keywords

        # 继续处理其他节点
        return node
from mutation_algorithms import (
    mutate_int,
    mutate_float,
    mutate_str,
    mutate_list,
    mutate_dict,
    mutate_tuple
)
import copy
from logger import logger

def get_mutation_algorithm(src_type, targ_type):
    """根据数据类型返回对应的变异算法"""
    if "int" in src_type :
        return mutate_int
    elif "float" in src_type:
        return mutate_float
    elif "str" in src_type:
        return mutate_str
    elif "list" in src_type:
        return mutate_list
    elif "dict" in src_type:
        return mutate_dict
    elif "tuple" in src_type:
        return mutate_tuple
    elif "NoneType" in src_type:
        raise ValueError("src_type is NoneType")
    else:
        raise ValueError("Unsupported data type for mutation")

# def mutate_data(mutation_point):
#     """根据变异点数据进行变异"""
#     src = mutation_point['src']
#     src_type = str(mutation_point['src_type'])
#     targ_type = str(mutation_point['targ_type'])
    
#     # 获取对应的变异算法
#     mutation_algorithm = get_mutation_algorithm(src_type, targ_type)
    
#     # 进行变异
#     targs = mutation_algorithm(src, src)
#     mutation_points = []
#     # 更新变异点数据
#     for v in targs: # targs是目标值变异完成后的列表
#         mutation_point_i = copy.deepcopy(mutation_point)
#         mutation_point_i['targ'] = v
#         mutation_point_i['is_mutate'] = True
#         mutation_points.append(mutation_point_i)
#     return mutation_points

def mutate_data(mutation_point):
    """根据变异点数据进行变异
        这里包含参数的名称、
    
    """
    
    try:
        src = mutation_point.get('src')
        src_type = str(mutation_point.get('src_type'))
        targ_type = str(mutation_point.get('targ_type'))
        
        # 如果缺少必要参数则返回空列表
        # if not all([src, src_type, targ_type]):
        #     logger.warning("Missing required mutation parameters")
        #     return []
            
        # 获取对应的变异算法
        mutation_algorithm = get_mutation_algorithm(src_type, targ_type)
        
        # 进行变异
        targs = mutation_algorithm(src, src)
        mutation_points = []
        for v in targs:# targs是目标值变异完成后的列表
            mutation_point_i = copy.deepcopy(mutation_point)
            mutation_point_i['targ'] = v
            # if "str" in src_type :
            #     mutation_point_i['targ'] = f';touch {mutation_point_i["api_name"].strip()}_Q{mutation_point_i["src"].strip()}.txt'
            mutation_point_i['is_mutate'] = True
            mutation_points.append(mutation_point_i)
            
        return mutation_points
        
    except Exception as e:
        logger.error(f"Error in mutate_data: {str(e)}")
        return []
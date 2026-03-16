import random

def mutate_int(src, targ):
    """变异整数类型的数据"""
    return [2**63-1, 2**31-1, 0, -36028797018963968]

def mutate_float(src, targ):
    """变异浮点类型的数据"""
    return [7.89645e+16,-1.0,-7.89645e+16]

def mutate_str(src, targ):
    """变异字符串类型的数据"""
    # return [';touch zz.txt']
    return []

def mutate_list(src, targ):
    """变异列表类型的数据"""
    return  [[2**63-1]*len(src),[0]*len(src)]

def mutate_dict(src, targ):
    """变异字典类型的数据"""
    return [targ]

def mutate_tuple(src, targ):
    """变异字典类型的数据"""
    # return [targ]
    if isinstance(src, tuple):
        return [tuple(targ if isinstance(x, int) else mutate_tuple(x, targ) for x in src)]
    else:
        raise ValueError("src must be a tuple")


# 可以根据需要添加更多的变异算法
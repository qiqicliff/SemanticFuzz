import json
from allpairspy import AllPairs

def pairwise_interface(input_data):
    # 创建副本，避免修改原始数据
    param_mapping = input_data['param'].copy()
    
    # 确保 api_interaction 是列表类型
    api_interaction = input_data.get("api_interaction", [])
    if not isinstance(api_interaction, list):
        api_interaction = [api_interaction] if api_interaction else []
    param_mapping['api_interaction'] = api_interaction
    
    # 确保所有值都是列表类型，并过滤掉空列表
    filtered_mapping = {}
    for name, vals in param_mapping.items():
        # 转换为列表类型
        if not isinstance(vals, list):
            if vals is not None:
                vals = [vals]
            else:
                continue  # 跳过 None 值
        # 只保留非空列表
        if len(vals) > 0:
            filtered_mapping[name] = vals
    param_mapping = filtered_mapping
    
    # 如果过滤后没有参数，返回空组合
    if not param_mapping:
        return {"combinations": [{}]}
    
    combine_params = {name: vals for name, vals in param_mapping.items() if len(vals) > 1 }
    # 只处理有值的参数，避免IndexError
    fixed_params = {name: vals[0] for name, vals in param_mapping.items() if name not in combine_params and len(vals) > 0}
    
    if not combine_params:
        return {"combinations": [fixed_params]}
    
    # 处理只有一个参数的情况
    if len(combine_params) == 1:
        name = list(combine_params.keys())[0]
        values = list(combine_params.values())[0]
        # 直接生成所有取值组合
        combinations = [fixed_params | {name: val} for val in values]
    else:
        # 正常的多参数pairwise组合
        names, values = list(combine_params.keys()), list(combine_params.values())
        combinations = [fixed_params | dict(zip(names, pairs)) for pairs in AllPairs(values)]
    
    return {"combinations": combinations}

if __name__ == "__main__":
    # 使用
    input_data = {'param': {'indices': ['Tensor:int16'], 'updates': ['Tensor:'], 'shape': ['Tensor:int16'], 'name': ['others:None']}, 'api_interaction': ['indices的最后一个维度必须满足indices.shape','indices的最后一个维度必须满足indices.shape22222222']}

    result = pairwise_interface(input_data)
    print(result)
    print(len((result)["combinations"]))
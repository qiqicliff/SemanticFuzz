import json
from openai import OpenAI
import global_config

def get_active_param_constraints(api_doc, messages=None):
    if messages is None:
        messages = []
    # print(api_doc[:50])
    prompt = f"""你是一个API参数空间分析专家。请严格按照以下文档API定义分类参数，并给参数归类：

API文档：
{api_doc}

请输出JSON格式，示例：
{{
  "param": {{
    "batch1": ["Tensor:"],
    "batch2": ["Tensor:"],
    "input": ["Tensor:double","Tensor:complex"],
    "alpha": ["float:float32","int:int32"],
    "beta":["float:float32","int:int32"]
  }}
  "constraints": "输入张量必须为二维，形状为(M, K)。批量张量必须为三维，形状分别为(N, M, P)和(N, P, K)。输入张量的第0维与第一个批量张量的第1维相等，输入张量的第1维与第二个批量张量的第2维相等。两个批量张量的第0维（N）必须一致。"
}}

注意：
1. 从文档中提取每种参数所有可能的具体取值（如数据类型、数值范围、特定字符串等），而不仅仅是类型名称
2. 对于有明确取值范围的参数，列出所有可能的取值或取值范围
3. 对于数据类型参数，列出支持的大类型和具体数据类型，形式为 [大类:具体类],如无详细具体类型，标注为[大类:]
4. out这类默认值为None的参数直接分类为others，并标注可能的取值
5. 严格按照示例中的json格式输出，无内容的字段为空字符串
6. 不要自己编造文档中未明确说明的参数和取值
"""
    messages.append({"role": "user", "content": prompt})

    # client = OpenAI(
    #     api_key="sk-KLhWFi0gK3884TSqAb59Eb6475914dE4Ab8560A83e5aEe47",
    #     base_url="http://192.168.131.248:30000/v1"
    # )

    try:
        res = global_config.chat_(messages, output_format="json")
        
        # 关键修复：检查空值
        if not res or not res.strip():
            print(f"[WARNING] chat_ 返回空值，使用默认约束")
            return '{"param":{},"constraints":{}}'
        
        # 清理 markdown 格式
        if res.startswith("```json"):
            res = res[len("```json"):].lstrip()
        if res.endswith("```"):
            res = res[:-3].rstrip()
        res = res.replace("`", "")
        
        # 再次检查清理后是否为空
        if not res.strip():
            return '{"param":{},"constraints":{}}'
        
        return res
        
    except Exception as e:
        print(f"[ERROR] get_active_param_constraints 异常: {e}")
        return '{"param":{},"constraints":{}}'


# 用法示例
if __name__ == "__main__":
    api_doc = "API: torch.as_strided_scatter(input, src, size, stride, storage_offset=None)\n  Function: Scatters elements from `src` into `input` using the specified `size`, `stride`, and `storage_offset`.\n  Parameter:\n      input: Tensor to which the elements will be scattered.\n      src: Tensor containing the elements to be scattered.\n      size: Tuple of integers representing the desired size of the output tensor.\n      stride: Tuple of integers representing the strides for each dimension.\n      storage_offset: Optional, integer representing the starting position in the storage.\n  Input constraints:\n      Dimensions: The `size` and `stride` must be compatible with the dimensions of `input` and `src`.\n      Type: `input` and `src` must have the same data type.\n      Stability: `storage_offset` must be a non-negative integer if provided."

    result = get_active_param_constraints(api_doc)
    print(result)
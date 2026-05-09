"""
Day 2 段 5 配套实验：Tool 渲染的 4 种形状对比

配套笔记：learning/notes/03-source/day2-tools/tool-schema-rendering-mental-model.md

跑法：
  python learning/scripts/tool_schema_trace.py

目的：
  写一个简单的 Tool 子类，亲眼对比 3 个渲染方法 + 1 个外部函数的输出形态：
    ① to_code_prompt()         → CodeAgent system prompt 里的 Python def 块
    ② to_tool_calling_prompt() → ToolCallingAgent system prompt 里的文字描述
    ③ get_tool_json_schema()   → HTTP 请求体 tools 字段的 OpenAI JSON
                                 ⚠️ 不在 Tool 类上，是 models.py 的独立函数
    ④ to_dict()                → 序列化字典（save / push_to_hub 用）

  亲眼看到 3 种形态后，"为什么 Tool 类需要这么多 to_xxx 方法" 就一目了然。

调试建议：
  - 重点观察 ① 和 ② 的差异 —— 同一份数据，"假装的 Python" vs "纯文字描述"
  - 重点观察 ②+③ 的配对 —— ToolCallingAgent 实际**两个**渲染产出来自不同位置
  - 在 to_code_prompt 里设断点，单步看 args_signature / tool_doc 一步步拼起来
"""

import sys
import json

# Windows 默认控制台是 GBK，强制 UTF-8 才能正常打印中文 + emoji
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from smolagents import Tool
from smolagents.models import get_tool_json_schema  # ⚠️ 注意：从 models 导入，不在 Tool 类上


# ============================================================
# 准备一个简单的 Tool 子类
# ----- 故意让它有：必填参数 + 可选参数（nullable） + 描述
#       这样能展示渲染方法对各种字段的处理
# ============================================================
class WeatherTool(Tool):
    name = "get_temperature"
    description = "Get current temperature in Celsius for a given city. Returns the temperature as a number."
    inputs = {
        "city": {
            "type": "string",
            "description": "City name in English (e.g. 'Beijing', 'Tokyo').",
        },
        "unit": {
            "type": "string",
            "description": "Temperature unit: 'C' for Celsius, 'F' for Fahrenheit.",
            "nullable": True,  # 可选参数 —— 看 ③ JSON schema 里 'required' 列表会怎么处理
        },
    }
    output_type = "number"

    def forward(self, city: str, unit: str = "C") -> float:
        # 假数据，不联网（让脚本可重复跑）
        fake_data = {"Beijing": 25.0, "Tokyo": 30.0, "Paris": 18.0}
        temp = fake_data.get(city, 20.0)
        if unit == "F":
            temp = temp * 9 / 5 + 32
        return temp


# ============================================================
# Demo 1: ① to_code_prompt() —— CodeAgent 看到的形态
# ============================================================
def demo_1_code_prompt(tool):
    print("\n" + "=" * 60)
    print("Demo 1: to_code_prompt() —— 给 CodeAgent 的 \"假装 Python def\"")
    print("=" * 60)
    print("[消费者] code_agent.yaml 模板（{{ tool.to_code_prompt() }}）")
    print("[输出形态] 一个看起来像 Python 函数定义的字符串")
    print("[原因] CodeAgent 让 LLM 写 Python 代码，所以让 LLM 看 Python 语法最自然")
    print("-" * 60)
    print(tool.to_code_prompt())


# ============================================================
# Demo 2: ② to_tool_calling_prompt() —— ToolCallingAgent system prompt 里的文字
# ============================================================
def demo_2_tool_calling_prompt(tool):
    print("\n" + "=" * 60)
    print("Demo 2: to_tool_calling_prompt() —— 给 ToolCallingAgent 的文字描述")
    print("=" * 60)
    print("[消费者] toolcalling_agent.yaml 模板（{{ tool.to_tool_calling_prompt() }}）")
    print("[输出形态] 一行 f-string 拼出来的纯文本")
    print("[原因] 让 LLM 用自然语言理解 \"我手上有哪些工具、能做啥\"")
    print("[⚠️ 易混淆] 这不是 HTTP tools 字段！HTTP tools 字段是 Demo 3 的产出")
    print("-" * 60)
    print(tool.to_tool_calling_prompt())


# ============================================================
# Demo 3: ⭐ ③ get_tool_json_schema() —— HTTP tools 字段的 JSON
# ----- 这是新手最容易误解的一个 —— 它不在 Tool 类上！
# ============================================================
def demo_3_json_schema(tool):
    print("\n" + "=" * 60)
    print("Demo 3: ⭐ get_tool_json_schema(tool) —— HTTP body 的 tools 字段 JSON")
    print("=" * 60)
    print("[消费者] models.py:540 —— completion_kwargs[\"tools\"] = [...]")
    print("[输出形态] OpenAI function calling 标准 JSON")
    print("[原因] LLM provider（OpenAI/Anthropic 等）要求这种结构识别工具")
    print("[⚠️ 关键事实] 这是 models.py 里的**独立函数**，不在 Tool 类上！")
    print("            原因：关注点分离 —— 它依赖外部协议，属于模型调用层")
    print("-" * 60)
    schema = get_tool_json_schema(tool)
    print(json.dumps(schema, indent=2, ensure_ascii=False))


# ============================================================
# Demo 4: ④ to_dict() —— 持久化字典（save / push_to_hub 用）
# ============================================================
def demo_4_to_dict(tool):
    print("\n" + "=" * 60)
    print("Demo 4: to_dict() —— 给磁盘 / HF Hub 的序列化字典")
    print("=" * 60)
    print("[消费者] save() / push_to_hub()")
    print("[输出形态] {\"name\": ..., \"code\": <完整源码字符串>, \"requirements\": [...]}")
    print("[原因] 让 Tool 能落盘 / 上传 / 远程加载，重新构造出同一个类")
    print("[第一遍学习] 知道存在 + 大致结构即可，不深究内部实现")
    print("-" * 60)
    try:
        d = tool.to_dict()
        # to_dict 输出字典，code 字段往往是大段源码，单独打印更清晰
        print(f"name:         {d['name']}")
        print(f"requirements: {d['requirements']}")
        print(f"code (前 30 行):")
        print("-" * 40)
        for line in d["code"].splitlines()[:30]:
            print(f"    {line}")
        if len(d["code"].splitlines()) > 30:
            print(f"    ... ({len(d['code'].splitlines())} 行总共)")
    except Exception as e:
        print(f"⚠️ to_dict() 抛错（在某些 Tool 子类上是预期的）：")
        print(f"    {type(e).__name__}: {e}")


# ============================================================
# Demo 5: 4 种形态并排对比 —— 浓缩版总览
# ============================================================
def demo_5_side_by_side(tool):
    print("\n" + "=" * 60)
    print("Demo 5: 4 种形态浓缩对比（同一份数据，4 种翻译）")
    print("=" * 60)

    code = tool.to_code_prompt()
    text = tool.to_tool_calling_prompt()
    schema = get_tool_json_schema(tool)
    print(f"""
源数据（Tool 实例的 4 个类属性）：
    name        = {tool.name!r}
    description = {tool.description!r}
    inputs      = {{...}} （2 个字段：city、unit）
    output_type = {tool.output_type!r}

────────────────────────────────────────────────────
① to_code_prompt() 输出（{len(code)} 字符）:
    "def get_temperature(city: string, unit: string) -> number:"
    + 多行 docstring（Args / Returns）

② to_tool_calling_prompt() 输出（{len(text)} 字符）:
    "{text[:80]}..."（一行文字）

③ get_tool_json_schema() 输出（dict，序列化后 {len(json.dumps(schema))} 字符）:
    {{"type": "function", "function": {{"name": "get_temperature",
      "description": "...", "parameters": {{"type": "object",
      "properties": {{...}}, "required": ["city"]}}}}}}
      ↑ 注意：unit 因为 nullable=True 没进 required 列表

④ to_dict() 输出: {{"name": ..., "code": <Python 源码>, "requirements": [...]}}
────────────────────────────────────────────────────
""")


# ============================================================
# Demo 6: 对比关键差异 —— LLM 看到的 unit 字段
# ----- 这是最有教学价值的对比：同一个 nullable 字段，
#       3 种渲染如何处理它
# ============================================================
def demo_6_nullable_handling(tool):
    print("\n" + "=" * 60)
    print("Demo 6: ⭐ nullable 字段在 3 种渲染里的体现")
    print("=" * 60)

    code = tool.to_code_prompt()
    text = tool.to_tool_calling_prompt()
    schema = get_tool_json_schema(tool)

    print("源数据：inputs['unit'] 标了 nullable=True\n")

    print("① to_code_prompt（CodeAgent）：")
    print(f"   仅在 docstring 里说 \"Temperature unit: ...\"")
    print(f"   {'→ 没有显式 nullable 标记，靠自然语言描述传达' if 'unit' in code else '???'}\n")

    print("② to_tool_calling_prompt（ToolCallingAgent system prompt）：")
    print(f"   把整个 inputs dict 直接 str() 进去")
    print(f"   → 'nullable': True 会作为字典字面量出现在文字里")
    print(f"   片段：{text}\n")

    print("③ get_tool_json_schema（HTTP tools 字段）：")
    unit_field = schema["function"]["parameters"]["properties"]["unit"]
    required = schema["function"]["parameters"]["required"]
    print(f"   properties.unit = {json.dumps(unit_field)}")
    print(f"   required = {required}")
    print(f"   → unit 因为 nullable=True，**不在 required 列表里**")
    print(f"   → LLM 看到 required: ['city'] 就知道 unit 是可选参数")

    print("\n💡 关键认知：")
    print("   - LLM 在 CodeAgent 模式下靠 docstring 自然语言理解可选参数")
    print("   - LLM 在 ToolCallingAgent 模式下靠 OpenAI 标准的 'required' 列表理解")
    print("   - **同一份数据，针对不同的消费方式以不同语法呈现** ← 这就是 4 路径的本质")


if __name__ == "__main__":
    tool = WeatherTool()

    print(f"实例化成功：{tool}")
    print(f"已通过 validate_arguments 校验（出厂质检通过）")

    demo_1_code_prompt(tool)
    demo_2_tool_calling_prompt(tool)
    demo_3_json_schema(tool)
    demo_4_to_dict(tool)
    demo_5_side_by_side(tool)
    demo_6_nullable_handling(tool)

    print("\n" + "=" * 60)
    print("✅ 全部 demo 跑完。")
    print()
    print("回顾 mental model：")
    print("  - Tool 实例是一份数据，需要被翻译成 4 种形状给 4 类客户看")
    print("  - 3 个 to_xxx 方法在 Tool 类上 + 1 个 get_tool_json_schema 在 models.py")
    print("  - 关注点分离：依赖外部协议的方法不放进核心类")
    print()
    print("下一步建议：")
    print("  - 在 tools.py:258 的 to_code_prompt 设断点，单步看 args_signature 拼装")
    print("  - 在 models.py:288 的 get_tool_json_schema 设断点，看 nullable → required 转换")
    print("=" * 60)

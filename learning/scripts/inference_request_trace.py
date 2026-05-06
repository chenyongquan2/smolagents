"""
Day 3 段 4 配套实验：抓真实 HTTP body 验证 _prepare_completion_kwargs 全流程

配套笔记：
  - learning/notes/03-source/model-generate-mental-model.md  (5 步流水线)
  - learning/notes/03-source/model-generate-params-explained.md  (7 参数详解)
  - learning/notes/03-source/model-stop-sequences.md  (stop 字段去向)
  - learning/notes/03-source/python-sentinel-pattern.md  (REMOVE_PARAMETER)

跑法：
  C:/workspace/smolagents/.venv/Scripts/python.exe learning/scripts/inference_request_trace.py

目的（兑现 Day 3 验收标准 ②）：
  亲眼看到 6 种典型场景下 agent 框架发往 LLM API 服务器的 HTTP body 长啥样：
    ① 最简 messages → body 基础结构
    ② 加 tools 列表 → body["tools"] 字段被 get_tool_json_schema 渲染
    ③ 加 stop_sequences → body["stop"] 字段写入位置
    ④ 三层优先级合并实战（self.kwargs 压舱石覆盖 caller kwargs）
    ⑤ REMOVE_PARAMETER 哨兵主动删字段
    ⑥ get_clean_message_list 的 role 转换 + 连续同 role 合并

  跑完之后再看任何 [model-generate-mental-model.md] 里的 5 步流水线就完全打通。

设计：
  - 写一个 TraceModel(Model) 裸子类，generate 不真实发 HTTP，
    直接返回 _prepare_completion_kwargs 的 dict 给打印
  - 这样脚本不依赖 HF token / 网络，永远能跑，又能看到真实 body 结构

调试建议：
  - 在 src/smolagents/models.py:502 _prepare_completion_kwargs 设断点，
    单步走 5 个步骤，对照 demo 4 的预期输出
  - 在 models.py:546 (self.kwargs 覆盖循环) 设条件断点 kwarg_name=="temperature"
  - 在 models.py:540 (tools 字段渲染) 看 get_tool_json_schema 的返回结构
"""

import sys
import json

# Windows 控制台默认 GBK，强制 UTF-8（CLAUDE.md 强制要求）
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from smolagents import tool
from smolagents.models import (
    Model,
    ChatMessage,
    MessageRole,
    ChatMessageToolCall,
    ChatMessageToolCallFunction,
    REMOVE_PARAMETER,
)


# ========================================================================
#  TraceModel：裸 Model 子类，不发请求，直接返回拼好的 body 给打印
# ========================================================================

class TraceModel(Model):
    """
    继承 Model 基类，不继承 ApiModel（避免创建 HTTP 客户端 / token 依赖）。
    覆盖 generate：不发请求，直接返回 _prepare_completion_kwargs 拼出的 dict。

    这样可以"亲眼看到"每次调用对应的真实 HTTP body 长啥样，不需要任何网络。
    """

    def __init__(self, model_id="Qwen/Qwen2.5-72B-Instruct", **kwargs):
        # 走父类 Model.__init__，把 model_id + 任何 self.kwargs 存好
        super().__init__(model_id=model_id, **kwargs)

    def generate(self, messages, stop_sequences=None, response_format=None,
                 tools_to_call_from=None, **kwargs):
        """不真实调 LLM API 服务器，只返回拼好的 body dict 给 caller 打印"""
        body = self._prepare_completion_kwargs(
            messages=messages,
            stop_sequences=stop_sequences,
            response_format=response_format,
            tools_to_call_from=tools_to_call_from,
            **kwargs,
        )
        return body  # ← 不是 ChatMessage，是 body dict（仅用于本实验）


# ========================================================================
#  辅助打印
# ========================================================================

def banner(title: str):
    line = "═" * 72
    print(f"\n{line}\n  {title}\n{line}")


def print_body(body: dict, label: str = "HTTP body"):
    """美化打印 body dict"""
    print(f"\n📦 {label}:")
    print(json.dumps(body, indent=2, ensure_ascii=False, default=str))


# ========================================================================
#  Demo 1: 最简 messages → body 基础结构
# ========================================================================

def demo_1_minimal():
    banner("Demo 1: 最简 messages → body 基础结构")

    print("""
目的：看一次最简单的 agent 调用产出的 body 长啥样
输入：1 条 system + 1 条 user，没 tools / 没 stop / 没 self.kwargs
预期：body 只有 messages 字段，连续 role 没合并需求
""")

    model = TraceModel()  # self.kwargs = {} 空
    messages = [
        ChatMessage(role=MessageRole.SYSTEM, content="你是个 helpful assistant"),
        ChatMessage(role=MessageRole.USER, content="北京天气如何？"),
    ]

    body = model.generate(messages)

    print_body(body)
    print("""
🔍 字段来源标注：
  body["messages"]  ← 来自步骤 ① get_clean_message_list (deepcopy + role 验证)
  （没有 stop / tools / response_format —— caller 没传，self.kwargs 也空）
""")


# ========================================================================
#  Demo 2: 加 tools → body["tools"] 字段渲染（Day 2 → Day 3 闭环）
# ========================================================================

def demo_2_with_tools():
    banner("Demo 2: 加 tools → body[\"tools\"] 字段被渲染")

    print("""
目的：看 ToolCallingAgent 风格的请求：tools_to_call_from 怎么变成 body["tools"]
预期：body["tools"] 是 list，每个元素是 OpenAI function calling JSON 格式
      由 _prepare_completion_kwargs 步骤 ② 调 get_tool_json_schema(tool) 渲染
      body["tool_choice"] 默认 "required"
""")

    @tool
    def get_weather(city: str) -> str:
        """查询某城市当前天气

        Args:
            city: 城市名（中文或英文）
        """
        return f"{city} 当前 22°C 晴"

    @tool
    def calculate(expression: str) -> str:
        """计算数学表达式

        Args:
            expression: 数学表达式字符串如 '1+2*3'
        """
        return str(eval(expression))

    model = TraceModel()
    messages = [
        ChatMessage(role=MessageRole.USER, content="北京天气 + 1+2 等于多少？"),
    ]

    body = model.generate(messages, tools_to_call_from=[get_weather, calculate])

    print_body(body)
    print("""
🔍 字段来源标注：
  body["messages"]      ← 步骤 ①
  body["tools"]         ← 步骤 ② 调用 get_tool_json_schema(tool) for each tool
                          ⭐ Day 2 段5 闭环：HTTP tools 字段不在 Tool 类上渲染
                             由 [models.py:288 get_tool_json_schema] 函数渲染
  body["tool_choice"]   ← 步骤 ② 默认 "required"（强制 LLM 必须调一个 tool）
""")


# ========================================================================
#  Demo 3: stop_sequences → body["stop"] 字段位置
# ========================================================================

def demo_3_stop_sequences():
    banner("Demo 3: stop_sequences → body[\"stop\"] 字段（注意改名！）")

    print("""
目的：验证 smolagents 内部 stop_sequences → 协议字段 stop 的改名
预期：传入 stop_sequences=["<end_code>"]，body 里出现 "stop": ["<end_code>"]
""")

    model = TraceModel()
    messages = [ChatMessage(role=MessageRole.USER, content="写一段 Python")]

    body = model.generate(messages, stop_sequences=["<end_code>", "<end_plan>"])

    print_body(body)
    print("""
🔍 字段来源标注：
  body["stop"]  ← 步骤 ② 改名！smolagents 内部叫 stop_sequences，
                  发出去前在 [models.py:534] 改成 OpenAI 协议字段名 stop
                  ⚠️ self.supports_stop_parameter 默认 True（普通模型）
                  如果是 o3-mini 等 reasoning 模型，这个字段会被静默跳过
""")


# ========================================================================
#  Demo 4: ⭐⭐ 三层优先级合并实战（self.kwargs 压舱石）
# ========================================================================

def demo_4_priority_merge():
    banner("Demo 4: ⭐⭐ 三层优先级合并 - self.kwargs 压舱石覆盖 caller kwargs")

    print("""
目的：⭐ 验证 [model-generate-mental-model.md §4] 的"三层优先级"理论
配置：
  - 实例化时 self.kwargs = {"temperature": 0.0, "max_tokens": 1024}  ← 最高优先级
  - 调用时    caller kwargs = {"temperature": 0.7, "top_p": 0.95}    ← 中间优先级
预期：
  - temperature 应该是 0.0 (self.kwargs 胜出)
  - top_p 应该是 0.95 (只在 caller kwargs 里)
  - max_tokens 应该是 1024 (只在 self.kwargs 里)
""")

    # 实例化时塞两个默认参数
    model = TraceModel(temperature=0.0, max_tokens=1024)
    print(f"实例化后 self.kwargs = {model.kwargs}")

    messages = [ChatMessage(role=MessageRole.USER, content="hi")]

    # 调用时再传两个 kwargs
    print("\n调用：generate(messages, temperature=0.7, top_p=0.95)\n")
    body = model.generate(messages, temperature=0.7, top_p=0.95)

    print_body(body)

    print(f"""
🔍 优先级实证：
  body["temperature"] = {body.get("temperature")}   ← 应该是 0.0 ✓ (self.kwargs 覆盖了 caller 0.7)
  body["max_tokens"]  = {body.get("max_tokens")}    ← 应该是 1024 ✓ (只在 self.kwargs 里)
  body["top_p"]       = {body.get("top_p")}         ← 应该是 0.95 ✓ (只在 caller kwargs 里)

  ⭐ self.kwargs 是"压舱石"，最后一步盖死所有同名参数
  ⭐ 这印证 [model-generate-mental-model.md §4] 的"用户配置优先级最高"哲学
""")


# ========================================================================
#  Demo 5: ⭐⭐ REMOVE_PARAMETER 哨兵主动删字段
# ========================================================================

def demo_5_remove_parameter():
    banner("Demo 5: ⭐⭐ REMOVE_PARAMETER 哨兵 - self.kwargs 主动删字段")

    print("""
目的：验证 [python-sentinel-pattern.md] 讲的哨兵机制
场景：用户用 reasoning 模型，知道它不接受 stop 字段
配置：
  - self.kwargs = {"stop": REMOVE_PARAMETER}   ← 哨兵
  - caller 仍然传 stop_sequences=["<end_code>"]
预期：
  - body 里**根本没有** stop 字段（不是 None，是不存在）
  - 即使 caller 传了 stop_sequences，也被哨兵在步骤 ④ pop 掉
""")

    # self.kwargs 里塞哨兵
    model = TraceModel(stop=REMOVE_PARAMETER)
    print(f"实例化后 self.kwargs = {model.kwargs}")

    messages = [ChatMessage(role=MessageRole.USER, content="写代码")]

    print("\n调用：generate(messages, stop_sequences=['<end_code>'])\n")
    body = model.generate(messages, stop_sequences=["<end_code>"])

    print_body(body)

    print(f"""
🔍 哨兵实证：
  "stop" in body = {"stop" in body}   ← 应该是 False ✓ (字段被 pop 了)

  ⭐ caller 努力传 stop_sequences=["<end_code>"]
     → 步骤 ② 写入 body["stop"] = ["<end_code>"]
     → 步骤 ④ self.kwargs 遍历到 stop=REMOVE_PARAMETER → completion_kwargs.pop("stop")
     → body 里彻底没有 stop 字段（不是 "stop": null）

  ⭐ 这就是哨兵设计的精髓 —— 区分"传 None"和"字段不存在"
  详见 [python-sentinel-pattern.md] §3 经典三场景
""")


# ========================================================================
#  Demo 6: ⭐ get_clean_message_list 的 role 转换 + 连续同 role 合并
# ========================================================================

def demo_6_message_cleaning():
    banner("Demo 6: ⭐ get_clean_message_list - role 转换 + 连续合并")

    print("""
目的：验证 [model-generate-mental-model.md §5] 的 5 件清洗
场景：模拟一段 agent 内部 memory 翻译来的 messages，故意制造 2 种问题：
  ① TOOL_CALL / TOOL_RESPONSE 这 2 个非标准 role 需要降维
  ② 连续 2 条 ASSISTANT 消息需要合并（OpenAI 协议禁止）

预期：
  - role 转换：TOOL_CALL → assistant, TOOL_RESPONSE → user
  - 连续合并：2 条 ASSISTANT 内容合并成 1 条 assistant
""")

    model = TraceModel()

    # 故意构造一个"乱"的 messages 列表
    messages = [
        ChatMessage(
            role=MessageRole.SYSTEM,
            content=[{"type": "text", "text": "你是个 agent"}],
        ),
        ChatMessage(
            role=MessageRole.USER,
            content=[{"type": "text", "text": "查天气"}],
        ),
        # 一条 ASSISTANT 思考
        ChatMessage(
            role=MessageRole.ASSISTANT,
            content=[{"type": "text", "text": "Thought: 我要调 get_weather"}],
        ),
        # 紧接着一条 TOOL_CALL —— 会被 role_conversions 转成 assistant
        # 然后和上面的 ASSISTANT 连续 → 应该合并！
        ChatMessage(
            role=MessageRole.TOOL_CALL,
            content=[{"type": "text", "text": "Calling: get_weather('Beijing')"}],
        ),
        # TOOL_RESPONSE —— 会被转成 user
        ChatMessage(
            role=MessageRole.TOOL_RESPONSE,
            content=[{"type": "text", "text": "Observation: 22°C 晴"}],
        ),
    ]

    print(f"输入 messages 数量：{len(messages)} 条")
    print(f"原始 role 序列：{[m.role.value for m in messages]}")

    body = model.generate(messages)

    print(f"\n清洗后 messages 数量：{len(body['messages'])} 条")
    print(f"清洗后 role 序列：{[m['role'] for m in body['messages']]}")

    print_body(body)

    print(f"""
🔍 清洗实证：
  原始 5 条 → 清洗后 {len(body['messages'])} 条

  规律：
    [SYSTEM, USER, ASSISTANT, TOOL_CALL, TOOL_RESPONSE]
                              ↓ 步骤 ①.c role 转换 (tool_role_conversions)
    [system, user, assistant, assistant,  user]
                              ↓ 步骤 ①.e 连续合并 (OpenAI 协议要求 role 交替)
    [system, user, assistant, ──merged──, user]   ← 中间 2 条 assistant 合并成 1 条

  ⭐ 这就是 [model-generate-mental-model.md §5] 讲的:
     "OpenAI 协议没有 TOOL_CALL/TOOL_RESPONSE，smolagents 内部 5 role 在喂 LLM 时降维成 3 个"
     "连续两条 assistant 会被 OpenAI 拒绝，必须合并"

  ⭐⭐ Week 1 chat-message-roles 闭环：role 是 LLM 行为的方向盘，
     5 → 3 降维的根因在 [chat-template-explained.md §9] —— chat template 不认非标准 role
""")


# ========================================================================
#  主入口
# ========================================================================

def main():
    print("""
╔══════════════════════════════════════════════════════════════════════════╗
║                                                                          ║
║   Day 3 段 4 实验：抓真实 HTTP body                                        ║
║   兑现 LEARNING_PLAN.md Day 3 验收标准 ②：                                 ║
║   "亲眼看到一次真实请求的 JSON body，并指出每个字段来自 memory 哪个 step"     ║
║                                                                          ║
║   思路：用 TraceModel(Model) 子类拦截 _prepare_completion_kwargs 输出，    ║
║   不真实发请求，但能看到 body 完整结构。                                    ║
║                                                                          ║
╚══════════════════════════════════════════════════════════════════════════╝
""")

    demo_1_minimal()
    demo_2_with_tools()
    demo_3_stop_sequences()
    demo_4_priority_merge()
    demo_5_remove_parameter()
    demo_6_message_cleaning()

    banner("✅ 全部 6 个 demo 跑完")
    print("""
回到 [model-generate-mental-model.md §3 5 步流水线]，对照本脚本输出：
  ① 清洗 messages (调 get_clean_message_list)        → demo 6 验证
  ② 写 specific 参数 (stop / response_format / tools) → demo 2/3 验证
  ③ caller kwargs (中间优先级)                        → demo 4 验证
  ④ self.kwargs (最高优先级 + REMOVE_PARAMETER 哨兵)   → demo 4/5 验证
  ⑤ 返回 body dict                                    → 全部 demo 都看到了

所有理论都已经在源码侧 + 实验侧双向验证。

⭐ Day 3 验收标准 ② 完成 ✅
""")


if __name__ == "__main__":
    main()

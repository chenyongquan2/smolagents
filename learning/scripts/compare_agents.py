"""
对比 ToolCallingAgent 和 CodeAgent 的差异。

设计思路：
- 同一个任务、同一个模型、同一个工具
- 任务故意需要"多次工具调用 + 简单计算"
  → ToolCallingAgent 会跑 4 步以上（每次只能调一个工具，再单独算）
  → CodeAgent 通常 1 步搞定（一段 Python 包含 3 次调用 + 计算）

跑法：
  python compare_agents.py
"""

from dotenv import find_dotenv, load_dotenv

from smolagents import CodeAgent, InferenceClientModel, ToolCallingAgent, tool


load_dotenv(find_dotenv())

# ============================================================
# 假装这是一个真实的天气 API（不联网，让对比可重复）
# ============================================================
@tool
def get_temperature(city: str) -> float:
    """
    Get current temperature in Celsius for a city.

    Args:
        city: City name (English).
    """
    fake_data = {
        "Beijing": 25.0,
        "Tokyo": 30.0,
        "Singapore": 28.0,
        "Paris": 18.0,
        "London": 15.0,
    }
    return fake_data.get(city, 20.0)


# ============================================================
# 任务：故意设计成多步 + 计算
# 期望 LLM 做：
#   1. 调 3 次 get_temperature
#   2. 找最大值
#   3. 乘以 1.8 + 32（摄氏转华氏）
# ============================================================
TASK = (
    "Find the temperature of Beijing, Tokyo, and Singapore. "
    "Among them, take the highest temperature, "
    "convert it to Fahrenheit (F = C * 1.8 + 32), and return the Fahrenheit value."
)

model = InferenceClientModel()  # 默认用 HF Inference + .env 里的 HF_TOKEN

# ============================================================
# 对照组 A：ToolCallingAgent（JSON 工具调用）
# ============================================================
print("\n" + "=" * 70)
print("【ToolCallingAgent】LLM 输出 JSON 风格的工具调用")
print("=" * 70)
tool_calling_agent = ToolCallingAgent(
    tools=[get_temperature],
    model=model,
    verbosity_level=2,  # 详细输出每步
)
result_a = tool_calling_agent.run(TASK)
steps_a = len(tool_calling_agent.memory.steps)

# ============================================================
# 对照组 B：CodeAgent（Python 代码作为动作）
# ============================================================
print("\n" + "=" * 70)
print("【CodeAgent】LLM 输出 Python 代码作为动作")
print("=" * 70)
code_agent = CodeAgent(
    tools=[get_temperature],
    model=model,
    verbosity_level=2,
    stream_outputs=True,
)
result_b = code_agent.run(TASK)
steps_b = len(code_agent.memory.steps)

# ============================================================
# 对比总结
# ============================================================
print("\n\n" + "=" * 70)
print("📊 对比结果（正确答案应该是 30°C → 86°F）")
print("=" * 70)
print(f"ToolCallingAgent: 答案={result_a}, 总步数={steps_a}")
print(f"CodeAgent:        答案={result_b}, 总步数={steps_b}")
print("=" * 70)
print(
    "\n💡 通常你会观察到：\n"
    "  - ToolCallingAgent 至少 4 步（3 次查询 + 1 次 final_answer）\n"
    "  - CodeAgent 通常 1-2 步（一段代码同时完成查询、求 max、换算）\n"
    "  - 两个 agent 答案应该一致（都是 86），但 LLM 调用次数差好几倍\n"
)

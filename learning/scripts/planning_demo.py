"""
观察 PlanningStep 周期性重规划机制。

要验证的 3 件事：
1. 开启 planning_interval 后，memory.steps 里会出现 PlanningStep
2. 重 plan 的位置符合公式：step 1, 1+N, 1+2N, ...（N = planning_interval）
3. PlanningStep.to_messages(summary_mode=True) 返回空列表 → 这就是
   "重 plan 时旧 plan 被隐藏"的机制实现侧

跑法：
  python planning_demo.py
"""

from dotenv import find_dotenv, load_dotenv

from smolagents import InferenceClientModel, Tool, ToolCallingAgent
from smolagents.memory import ActionStep, MemoryStep, PlanningStep, TaskStep

load_dotenv(find_dotenv())


# ============================================================
# 假天气工具（不联网，让对比可重复）
# ============================================================
class GetTemperatureTool(Tool):
    name = "get_temperature"
    description = "Get current temperature in Celsius for a city."
    inputs = {"city": {"type": "string", "description": "City name in English."}}
    output_type = "number"

    def forward(self, city: str) -> float:
        fake_data = {
            "Beijing": 25.0,
            "Tokyo": 30.0,
            "Singapore": 28.0,
            "Paris": 18.0,
            "London": 15.0,
        }
        return fake_data.get(city, 20.0)


# ============================================================
# 任务：故意设计成多步，让 planning_interval=2 能触发多次重 plan
# 期望约 4-5 个 ActionStep（3 次查询 + max + 换算）
# ============================================================
TASK = (
    "Find the temperature of Beijing, Tokyo, and Singapore. "
    "Among them, take the highest temperature, "
    "convert it to Fahrenheit (F = C * 1.8 + 32), and return the Fahrenheit value."
)

model = InferenceClientModel(model_id="Qwen/Qwen2.5-72B-Instruct")

# ============================================================
# ⭐ 关键开关：planning_interval=2
# 公式：step_number == 1 or (step_number - 1) % 2 == 0
# 触发位置：step 1, 3, 5, 7, ...
# ============================================================
PLANNING_INTERVAL = 2

agent = ToolCallingAgent(
    tools=[GetTemperatureTool()],
    model=model,
    planning_interval=PLANNING_INTERVAL,
    verbosity_level=1,
    max_steps=8,
)


# ============================================================
# 🐞 Day 1 单步调试 · 断点 C：CallbackRegistry MRO walk
# 注册到基类 MemoryStep，观察"基类注册 = 监听全部子类"
# 在 src/smolagents/memory.py:314（for cls in __mro__）打断点跑
# ============================================================
def my_cb_old(step):
    """老式签名（1 参）—— inspect.signature 走 cb(memory_step) 分支"""
    print(f"📞 OLD-style fired for: {type(step).__name__}")


def my_cb_new(step, **kwargs):
    """新式签名（多参）—— inspect.signature 走 cb(memory_step, **kwargs) 分支"""
    agent_obj = kwargs.get("agent")
    print(
        f"📞 NEW-style fired for: {type(step).__name__}, "
        f"agent class: {type(agent_obj).__name__}"
    )


# ⭐ 关键：注册到基类 MemoryStep，所有 Step 子类完成时都会触发
agent.step_callbacks.register(MemoryStep, my_cb_old)
agent.step_callbacks.register(MemoryStep, my_cb_new)


print("\n" + "=" * 70)
print(f"🚀 Run ToolCallingAgent with planning_interval={PLANNING_INTERVAL}")
print("=" * 70)
result = agent.run(TASK)


# ============================================================
# 第 1 件事：遍历 memory.steps，看 step 类型分布
# ============================================================
print("\n" + "=" * 70)
print(f"🔍 memory.steps 总数: {len(agent.memory.steps)}")
print("=" * 70)

for i, step in enumerate(agent.memory.steps):
    cls = type(step).__name__
    header = f"[{i}] {cls}"

    if isinstance(step, TaskStep):
        print(f"\n--- {header} ---")
        task_preview = step.task[:80]
        print(f"  task: {task_preview}...")

    elif isinstance(step, PlanningStep):
        print(f"\n--- {header} ⭐ ---")
        plan_preview = step.plan[:400].replace("\n", "\n         ")
        print(f"  plan:\n         {plan_preview}")
        if len(step.plan) > 400:
            print(f"         ... (truncated, full len = {len(step.plan)})")

    elif isinstance(step, ActionStep):
        print(f"\n--- {header} (step_number={step.step_number}) ---")
        if step.tool_calls:
            for tc in step.tool_calls:
                print(f"  tool_call: {tc.name}({tc.arguments})")
        if step.observations:
            obs = str(step.observations)[:120].replace("\n", " ")
            print(f"  observations: {obs}")
        if step.is_final_answer:
            print(f"  ⭐ is_final_answer = True, action_output = {step.action_output}")


# ============================================================
# 第 2 件事：验证重 plan 触发位置符合公式
# ============================================================
print("\n" + "=" * 70)
print("🧪 验证重 plan 触发位置")
print("=" * 70)

planning_indices = [
    i for i, s in enumerate(agent.memory.steps) if isinstance(s, PlanningStep)
]
# 找每个 PlanningStep 后面的第一个 ActionStep 的 step_number
trigger_step_numbers = []
for pi in planning_indices:
    for j in range(pi + 1, len(agent.memory.steps)):
        s = agent.memory.steps[j]
        if isinstance(s, ActionStep):
            trigger_step_numbers.append(s.step_number)
            break

print(f"  PlanningStep 出现位置（memory.steps 索引）: {planning_indices}")
print(f"  对应紧随的 ActionStep.step_number: {trigger_step_numbers}")
print(
    f"  公式预测（planning_interval={PLANNING_INTERVAL}）触发的 step_number: "
    f"1, {1 + PLANNING_INTERVAL}, {1 + 2 * PLANNING_INTERVAL}, ..."
)


# ============================================================
# 第 3 件事：验证 summary_mode 隐藏旧 plan 的机制
# ============================================================
print("\n" + "=" * 70)
print("🧪 验证：PlanningStep.to_messages(summary_mode=True) 返回空")
print("=" * 70)

planning_steps = [s for s in agent.memory.steps if isinstance(s, PlanningStep)]
if planning_steps:
    p = planning_steps[0]
    msgs_normal = p.to_messages(summary_mode=False)
    msgs_summary = p.to_messages(summary_mode=True)
    print(f"  第 1 个 PlanningStep 的 to_messages 输出:")
    print(f"    summary_mode=False → {len(msgs_normal)} 条消息  (正常状态)")
    print(f"    summary_mode=True  → {len(msgs_summary)} 条消息  ⭐ 隐身！")
    print(
        "\n  💡 含义：当第二次 plan 触发时，框架调用 write_memory_to_messages("
        "summary_mode=True)"
    )
    print("     此时所有历史 PlanningStep 都返回 []，新 plan 看不到旧 plan 文本。")
    print("     这就是 [memory.py:174-176] 那 3 行 if 判断的运行时效果。")
else:
    print("  ⚠️ 没找到 PlanningStep（可能 max_steps 太小或任务太简单，建议调大 max_steps）")


# ============================================================
# 第 4 件事：对比第 1 个 vs 第 2 个 plan 文本（如果有的话）
# ============================================================
if len(planning_steps) >= 2:
    print("\n" + "=" * 70)
    print("🔬 对比 Initial Plan vs Updated Plan（看 LLM 怎么调整方向）")
    print("=" * 70)
    p1, p2 = planning_steps[0], planning_steps[1]
    print(f"\n  📋 Initial Plan (前 250 字):")
    print(f"     {p1.plan[:250].replace(chr(10), chr(10) + '     ')}")
    print(f"\n  📋 Updated Plan (前 250 字):")
    print(f"     {p2.plan[:250].replace(chr(10), chr(10) + '     ')}")
    print(
        "\n  💡 注意 Updated 通常以 'I still need to solve...' 开头（见 agents.py:737），"
        "且基于 observations 推断剩余动作。"
    )


print("\n" + "=" * 70)
print(f"✅ 最终答案: {result}")
print("=" * 70)

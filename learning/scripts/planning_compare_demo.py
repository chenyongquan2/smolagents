"""
🐞 实验：planning_interval 开 vs 不开的对比

跑同一个任务两次：
  ① planning_interval=None（不规划，默认）
  ② planning_interval=3（每 3 步规划一次）

对比维度：
  - 实际 step 数（ActionStep 数 / PlanningStep 数）
  - 总 token 消耗（input + output）
  - 是否撞 max_steps
  - 最终答案质量

任务：刻意选一个"多步推理 + 容易走偏" 的任务，让规划的价值更容易显现
"""

import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())

from smolagents import CodeAgent, InferenceClientModel
from smolagents.memory import ActionStep, PlanningStep


# ─────────────────────────────────────────────────────────────────────
# 任务设计：故意选一个 "多步骤推理 + 容易跑偏" 的任务
# - 50-100 之间的素数（一步搞定不太行 —— 要遍历 + 整理）
# - 计算总和、平均值、分组（多步推理）
# - 答案唯一可验证（避免 LLM 主观发挥）
# ─────────────────────────────────────────────────────────────────────
TASK = (
    "找出 50 到 100 之间所有的素数，按从小到大列出。"
    "然后分别计算它们的总和与平均值（平均值保留 2 位小数）。"
    "最后判断'素数总数'是奇数还是偶数。"
)


def run_experiment(planning_interval, label):
    """跑一次实验，返回 RunResult + 统计信息"""
    print(f"\n{'=' * 60}")
    print(f"实验 {label}: planning_interval = {planning_interval}")
    print(f"{'=' * 60}")

    agent = CodeAgent(
        tools=[],
        model=InferenceClientModel(),
        max_steps=8,
        planning_interval=planning_interval,
        stream_outputs=False,
        return_full_result=True,
    )

    result = agent.run(TASK)

    # 统计 step 数
    n_action_steps = sum(1 for s in agent.memory.steps if isinstance(s, ActionStep))
    n_planning_steps = sum(1 for s in agent.memory.steps if isinstance(s, PlanningStep))

    # 取 token usage（可能为 None）
    if result.token_usage:
        in_tokens = result.token_usage.input_tokens
        out_tokens = result.token_usage.output_tokens
    else:
        in_tokens = out_tokens = 0

    print(f"\n--- 统计 ---")
    print(f"  ActionStep 数:    {n_action_steps}")
    print(f"  PlanningStep 数:  {n_planning_steps}")
    print(f"  Input tokens:     {in_tokens}")
    print(f"  Output tokens:    {out_tokens}")
    print(f"  总 tokens:        {in_tokens + out_tokens}")
    print(f"  state:            {result.state}")
    print(f"\n--- 最终答案 ---")
    print(f"  {result.output}")

    # 打印 PlanningStep 内容（如果有）
    plans = [s for s in agent.memory.steps if isinstance(s, PlanningStep)]
    if plans:
        print(f"\n--- 规划内容（前 300 字）---")
        for i, p in enumerate(plans, 1):
            print(f"\n  ▸ Plan {i}:")
            plan_text = p.plan[:300] if p.plan else "(空)"
            print(f"    {plan_text}...")

    return {
        "label": label,
        "action_steps": n_action_steps,
        "planning_steps": n_planning_steps,
        "input_tokens": in_tokens,
        "output_tokens": out_tokens,
        "total_tokens": in_tokens + out_tokens,
        "state": result.state,
        "output": result.output,
    }


# ─────────────────────────────────────────────────────────────────────
# 跑两次对比
# ─────────────────────────────────────────────────────────────────────
print(f"任务: {TASK}\n")

result_a = run_experiment(None, "A · 不规划")
result_b = run_experiment(3, "B · 规划 (interval=3)")

# ─────────────────────────────────────────────────────────────────────
# 对比汇总
# ─────────────────────────────────────────────────────────────────────
print(f"\n\n{'=' * 60}")
print(f"📊 对比汇总")
print(f"{'=' * 60}\n")

print(f"{'指标':<22} {'A · 不规划':<22} {'B · 规划 (interval=3)':<22}")
print(f"{'-' * 66}")
print(f"{'ActionStep 数':<22} {result_a['action_steps']:<22} {result_b['action_steps']:<22}")
print(f"{'PlanningStep 数':<22} {result_a['planning_steps']:<22} {result_b['planning_steps']:<22}")
print(f"{'Input tokens':<22} {result_a['input_tokens']:<22} {result_b['input_tokens']:<22}")
print(f"{'Output tokens':<22} {result_a['output_tokens']:<22} {result_b['output_tokens']:<22}")
print(f"{'总 tokens':<22} {result_a['total_tokens']:<22} {result_b['total_tokens']:<22}")

if result_a["total_tokens"] > 0:
    pct = (
        (result_b["total_tokens"] - result_a["total_tokens"])
        / result_a["total_tokens"]
        * 100
    )
    print(f"{'token 差异':<22} {'(基线)':<22} {f'{pct:+.1f}%':<22}")

print(f"{'state':<22} {result_a['state']:<22} {result_b['state']:<22}")

print(f"\n{'=' * 60}")
print(f"💡 关键观察清单（对照检查）")
print(f"{'=' * 60}\n")
print(f"""
□ PlanningStep 数：A 应该 = 0；B 应该 ≥ 1（取决于 ActionStep 数）
   - B 触发时机：step_number = 1, 4, 7, ...

□ Token 消耗：B 比 A 高 30-50% 是正常的
   - 多了规划的 LLM 调用
   - 实测增幅: {pct:+.1f}% (如果显示 {pct:+.1f}% < 0，说明任务太简单 / 规划反而省了 token)

□ ActionStep 数：
   - 如果 B < A → 规划帮 LLM 不走弯路
   - 如果 B = A → 任务对规划不敏感
   - 如果 B > A → 规划增加了开销但没帮上忙

□ state = "max_steps_error"：
   - 不规划版撞上限的概率更高（任务复杂时）

□ 答案质量：可肉眼对比两次输出是否一致 / 哪个更准
""")

# ─────────────────────────────────────────────────────────────────────
# 进阶：要看完整 PlanningStep 时，单步调试 ②（B）即可
# 在 [agents.py:550] 设断点，看 _generate_planning_step 的工作过程
# ─────────────────────────────────────────────────────────────────────
print(f"{'=' * 60}")
print(f"🐞 单步调试规划过程")
print(f"{'=' * 60}\n")
print("""
想亲眼看规划是怎么发生的：

1. 在 [agents.py:550] 设断点（while 循环里的 if planning_interval is not None 处）
2. 改本脚本只跑 B（注释掉 result_a = ... 那行）
3. F5 启动调试
4. 第一次命中 ([:550]) 时：step_number=1，正好触发首次规划
5. F11 step into self._generate_planning_step(...) 看规划怎么调 LLM
6. 跑回上层 → F10 看 yield 出 PlanningStep
7. 继续 F5 → 看 step_number=4 时第二次规划触发
""")

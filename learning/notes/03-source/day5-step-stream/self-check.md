---
created: 2026-05-14
status: active
tags: [smolagents, agents, step-stream, self-check, day5]
---

# Day 5 自查手册：14 道题 + 详细答案 + 笔记溯源

> 💡 **使用方式**（同 Day 3 / Day 4 self-check）：
> - 盖住答案，**心里答完整版**（不是"知道大概意思"）
> - 揭开答案对照，**完全答对**才算过
> - 答错 / 模糊 → 点笔记溯源精读对应段落
> - 学习节奏自由 —— 一次答完 / 拆成 3 天 / 卡壳就翻笔记都行

**覆盖范围**：5 篇 Day 5 笔记（00 / 01 / 02 / 03 / 04）+ 概念笔记 [tools-are-python-callables](../../02-concepts/tools-are-python-callables.md)。

**题目分布**：
- ★ 事实记忆（行号 / 类名 / 字段名）
- ★★ 概念应用（讲清机制）
- ★★★ 设计意图（为什么这样设计）
- ★★★★ 跨层闭环 / 实战应用 / "看会"层

---

## Q1（★ 事实）：`_step_stream` 在源码哪里？基类 / 子类各几行？

<details>
<summary>👀 看答案</summary>

| 类 | agents.py 行号 | 实现状态 | 行数 |
|---|---|---|---|
| `MultiStepAgent._step_stream` | [772](../../../../src/smolagents/agents.py#L772) | 软约束 `raise NotImplementedError` | ~10 |
| `ToolCallingAgent._step_stream` | [1276](../../../../src/smolagents/agents.py#L1276) | 完整实现 | ~84 |
| `CodeAgent._step_stream` | [1639](../../../../src/smolagents/agents.py#L1639) | 完整实现 | ~127 |

**溯源**：[00 §2](00-step-stream-role-overview.md#2-谁在调用--谁在被调用)

</details>

---

## Q2（★★ 概念）：默写 `_step_stream` 的 5 个固定动作

<details>
<summary>👀 看答案</summary>

```
① read messages    write_memory_to_messages() → input_messages
                   memory_step.model_input_messages = input_messages
② call LLM         model.generate(input, stop=..., [tools=...])
                   yield ChatMessageStreamDelta × N (if stream)
                   memory_step.model_output / output_message / token_usage
③ parse output     ⭐ 分歧点 1：从 LLM 输出抠"动作"
④ execute action   ⭐ 分歧点 2：真的把动作跑一遍
                   yield ToolCall (前置预告) + yield ToolOutput (后置反馈)
⑤ write back + yield   memory_step.tool_calls / observations / action_output
                       yield ActionOutput(output, is_final_answer)
```

**溯源**：[00 §3 ⭐⭐ 5 个固定动作](00-step-stream-role-overview.md#3--5-个固定动作共同骨架)

</details>

---

## Q3（★★ 概念）：动作 ③ 在两子类怎么解析？

<details>
<summary>👀 看答案</summary>

**ToolCallingAgent** ([agents.py:1327-1334](../../../../src/smolagents/agents.py#L1327))：
- 优先：直接读 `chat_message.tool_calls`（HTTP `tool_calls` 字段，服务器已解析）
- fallback：`model.parse_tool_calls(chat_message)` 文本 regex 抠
- 后处理：`parse_json_if_needed(arguments)` 转 dict

**CodeAgent** ([agents.py:1703-1714](../../../../src/smolagents/agents.py#L1703)) "3 把刀"：
- 刀①：`parse_code_blobs` regex `<code>(.*?)</code>`
- 刀②：fallback markdown ```` ```python(.*?)``` ````
- 刀③：`ast.parse(text)` 试整段裸代码
- 后处理：`fix_final_answer_code` 修补 `final_answer = X` 误用

**溯源**：[03 §4 ⭐ 分歧点 1](03-impl-diff-deep-dive.md#4--差异维度-2解析路径动作-)

</details>

---

## Q4（★★ 概念）：动作 ④ 在两子类怎么执行？

<details>
<summary>👀 看答案</summary>

| | ToolCallingAgent | CodeAgent |
|---|---|---|
| 入口 | `process_tool_calls(...)` (1361-1442) | `python_executor(code_action)` (1727) |
| 执行什么 | N 个 tool call | 1 段 Python 代码 |
| 并行 | `ThreadPoolExecutor` + `copy_context()` 隔离 contextvars | 沙箱内部串行 |
| 真调 tool 那一行 | `tool(**args, sanitize_inputs_outputs=True)` | 沙箱内 `tool(args)` |
| 嵌套深度 | 5 层 | 3 层 |

**两边最终都调 `Tool.__call__ → Tool.forward(**args)`**（呼应 [tools-are-python-callables.md](../../02-concepts/tools-are-python-callables.md)）—— 工具本身没差异。

**溯源**：[03 §5 ⭐ 分歧点 2](03-impl-diff-deep-dive.md#5--差异维度-3执行机制动作-)

</details>

---

## Q5（★★★ 设计意图）：为什么 `process_tool_calls` 设计成"先 yield 全部 ToolCall，再执行 + yield ToolOutput"两阶段，不直接合并成"边执行边 yield 完整事件"？

<details>
<summary>👀 看答案</summary>

**前置意图 vs 后置反馈是两条独立信号**，分两阶段才能让 UI 在 latency 期间显示 "loading…" 占位符：

```
[4a] yield ToolCall("web_search")    ← UI 收到 → 显示 "正在搜索 Paris..." 转圈
[4b] 真执行（可能数秒）              ← UI 持续转圈
[4c] yield ToolOutput("12°C")        ← UI 收到 → 渲染结果
```

如果合并成一次 yield：用户在 4b 期间（可能数秒）**完全不知道发生了什么** —— Web UI 看起来卡死。

这是流式 UI 通用设计（ChatGPT / Claude UI 都先显示 "🔍 Searching..." 占位符再渲染结果），呼应 Day 4 ③'''' [event-design-philosophy](../day4-agents/03e-stream-event-design-philosophy.md) §"ToolCall vs ToolOutput 前置意图 vs 后置反馈"。

**溯源**：[01 §番外 5 两阶段 yield 设计意图](01-toolcalling-walkthrough.md)

</details>

---

## Q6（★★★ 设计意图）：CodeAgent 为什么"老板对讲机只响 2 下"（缺少 ToolOutput）？

<details>
<summary>👀 看答案</summary>

CodeAgent 整段代码是 **1 次沙箱执行**，没有"调多个独立工具的 latency 期间" → **没有"前置 / 后置反馈"两段需求** → 不需要 ToolOutput 事件。

老板对讲机 yield 顺序：
- ToolCallingAgent（每步 N=1 个 tool）：`ToolCall + ToolOutput + ActionOutput` = **3** 下
- CodeAgent：`ToolCall(合成) + ActionOutput` = **2** 下

UI 影响：
- ToolCallingAgent UI 能显示"⏳ 正在搜索 → ✓ 12°C"两阶段
- CodeAgent UI 只能显示"⏳ 正在执行代码 → ✓ 86.0"（不知道沙箱里跑到哪一行）

**溯源**：[03 §7 事件流](03-impl-diff-deep-dive.md#7-差异维度-5事件流yield-几下对讲机)

</details>

---

## Q7（★★★ 设计意图）：两种 agent 的 `memory_step.tool_calls` 字段都被写，但有什么本质差异？

<details>
<summary>👀 看答案</summary>

| | ToolCallingAgent | CodeAgent |
|---|---|---|
| `memory_step.tool_calls` 内容 | LLM 真实返回的 ToolCall list | **合成的** `[ToolCall("python_interpreter", code_action, ...)]` |
| 来源 | `chat_message.tool_calls`（LLM 决定）| 框架捏的（CodeAgent.\_step\_stream 第 3 幕末手动包）|

**为什么 CodeAgent 也要写**：让 ToolCallingAgent 和 CodeAgent 的 **log / replay / monitor 接口统一** —— 不管哪种 agent 跑完，外部观察者都能用同样的 ToolCall API 看历史。这是 Day 1 ⭐ 已揭示的"持久化统一接口"设计精髓。

**注意区分两个不同语境**（[00 §11 给学习者的 3 条提醒](00-step-stream-role-overview.md#11-给-day-5-学习者的-3-条提醒)）：
- `memory_step.tool_calls`（持久化记录，Day 1 字段）
- `chat_message.tool_calls`（一次 LLM 响应里的临时字段，Day 3 协议字段）

**溯源**：[02 第 3 幕 ⭐ 合成 ToolCall](02-codeagent-walkthrough.md) + [03 §9 memory_step 字段差异](03-impl-diff-deep-dive.md#9-差异维度-7memory_step-字段谁写)

</details>

---

## Q8（★★★ 设计意图）：CodeAgent 第 2 幕"手动补 closing tag"为什么只在 `if not self._use_structured_outputs_internally:` 才需要？

<details>
<summary>👀 看答案</summary>

两种模式下 `output_text` 形态完全不同：

| 模式 | output_text 长什么样 | `</code>` stop 触发吗 | 需要补 closing tag 吗 |
|---|---|---|---|
| 非 structured | 自由文本 + `<code>代码</code>` | ✅ 触发 → 服务器**截掉** `</code>` | ✅ 需要补 |
| structured | 严格 JSON `{"thoughts": "...", "code": "..."}` | ❌ 不触发（JSON 里没 `</code>`）| ❌ 不需要 |

**非 structured 模式**：OpenAI 协议默认"检测到 stop 时停 + **不输出 stop 字符串本身**"（Day 3 [stop-sequences §7 被动检测](../day3-models/model-stop-sequences.md)）→ closing tag 被截 → 框架手动补回让 memory 里语法完整。

**structured 模式**：JSON 自然终止在 `}`，**根本不含 `</code>` 字符串作结构标记** → stop 永不触发 → 不需要补。

**溯源**：[02 第 2 幕"新手疑问"](02-codeagent-walkthrough.md)

</details>

---

## Q9（★★★ 设计意图）：function calling 协议和 structured output 协议有什么区别？都跟 JSON 有关，为什么两个？

<details>
<summary>👀 看答案</summary>

**目的完全不同**：

| | function calling | structured output |
|---|---|---|
| 目的 | 让 LLM "请求调用外部函数" | 让 LLM "按固定结构吐数据" |
| 隐喻 | 🍽️ 点菜模式 | 📋 答题卡模式 |
| 协议加什么 | 请求加 `tools` 字段 + 响应**新增** `tool_calls` 字段 | 请求加 `response_format` 字段 + **约束** `content` 必须是合法 JSON 字符串 |
| LLM 决定权 | 决定调不调、调哪个（可不调） | 强制必须按 schema 输出 |

**smolagents 3 条路径**：

| | function calling | structured output |
|---|---|---|
| ToolCallingAgent | ✅ 传 tools | ❌ |
| CodeAgent 默认 | ❌ | ❌ |
| CodeAgent structured | ❌ | ✅ 传 response_format |

注意 **CodeAgent 两条路径都不用 function calling** —— 故意放弃，让 LLM 用代码（Turing complete）表达决策。

**溯源**：[02 §专题：控制 LLM 输出的 3 条路径](02-codeagent-walkthrough.md)

</details>

---

## Q10（★★★ 设计意图）：CodeAgent 通常 1 步搞定，ToolCallingAgent 通常 4 步 —— 这是 ToolCallingAgent 的根本性能短板还是模型选择？

<details>
<summary>👀 看答案</summary>

**两者都是**。需要拆解 3 个独立维度：

| 维度 | parallel 能优化吗 | CodeAgent 一步搞定吗 |
|---|---|---|
| 维度 1：协议批量能力 | ✅（N 次 → 1 次） | ✅ |
| 维度 2：链式依赖 / 条件分支 | ❌ 救不了（JSON 不能引用运行时返回值）| ✅（代码里 if-else / 引用变量）|
| 维度 3：真正的探索式任务 | ❌ | ❌（CodeAgent 也救不了）|

**对 ToolCallingAgent**：
- 即使 LLM 支持 parallel function calling（如 GPT-4），**也至少 2 次 LLM 调用**（一次调多个工具 + 一次看结果做计算 / 决策）
- 因为 JSON `tool_calls` 无法表达"max(返回值1, 返回值2)"这种依赖运行时返回值的表达式

**对 CodeAgent**：
- 把"计算 + 决策 + 控制流"塞进 Python 沙箱 → LLM 只决策"怎么做"一次
- **LLM 当代码生成器**，沙箱当解释器（vs ToolCalling 把 LLM 当控制器）

实测（compare_agents.py + Qwen2.5）：ToolCalling 4 步 / CodeAgent 1 步。换 GPT-4 parallel 可能变 2 步 / 1 步。

**溯源**：[03 §10 ⭐⭐ 为什么 parallel 救不了根本成本](03-impl-diff-deep-dive.md#-为什么-parallel-救不了-toolcallingagent-的根本成本) + [03 §10 ⭐ 扩展认知](03-impl-diff-deep-dive.md#-扩展认知3-个维度决定-llm-调用次数)

</details>

---

## Q11（★★★ 设计意图）：两种 agent 调用的工具有本质区别吗？

<details>
<summary>👀 看答案</summary>

**没有本质区别 —— 都是 Python callable**。两种 agent 的差异**不在工具本质，在"谁解析参数 + 谁触发调用"**：

```
            ┌─── Tool.__call__(**args) ───┐
            │       ↓                      │
            │   Tool.forward(**args)      │
            └──────────────────────────────┘
                  ▲                ▲
                  │                │
      ToolCalling framework     CodeAgent 沙箱里
      4b 幕 execute_tool_call   Python 代码 get_temperature("Paris")
      (framework 解析 JSON 后)  (沙箱解析代码后)
```

**任何来源的工具**（本地函数 / MCP / Gradio / HF Hub / managed_agent / LangChain）都被规范成 Tool 实例 = Python callable。这是 Day 2 [tool-class-role-overview](../day2-tools/tool-class-role-overview.md) 强调的"统一抽象"设计胜利。

**溯源**：[02-concepts/tools-are-python-callables.md](../../02-concepts/tools-are-python-callables.md)

</details>

---

## Q12（★★★★ 跨层闭环）：默写 ToolCallingAgent + Qwen2.5（不 parallel）跑"查 3 城市最高温转华氏"的 4 步精确剧本（含每步 memory.steps 累积）

<details>
<summary>👀 看答案</summary>

```
Step 1（LLM 第 1 次）：
  ├─ write_memory_to_messages() → [SYS, USER]
  ├─ model.generate(...) → tool_calls=[get_temperature("Beijing")]
  ├─ 调 → 25.0
  └─ memory.steps.append → [SystemPrompt, TaskStep, ActionStep1]

Step 2（LLM 第 2 次）：
  ├─ write_memory_to_messages() → [SYS, USER, ASSISTANT(act1), USER(obs1=25°C)]
  ├─ LLM 看到 25°C → tool_calls=[get_temperature("Tokyo")]
  └─ memory.steps.append → [..., ActionStep2]

Step 3（LLM 第 3 次）：
  ├─ messages 含 [..., act1, obs1, act2, obs2]
  ├─ LLM 看到 [25, 30] → tool_calls=[get_temperature("Singapore")]
  └─ ActionStep3

Step 4（LLM 第 4 次）：
  ├─ messages 含 [..., act1/obs1/act2/obs2/act3/obs3]
  ├─ LLM 看到 [25, 30, 28] → 心算 max + 转华氏 → tool_calls=[final_answer(86.0)]
  └─ is_final_answer=True → 退出
```

**核心机理**（呼应 Day 4 ⑤）：**每次调一个 → 写 step → 把所有历史打包重发 → LLM 决定下一个**。

**溯源**：[03 §10 维度 1 精确剧本](03-impl-diff-deep-dive.md#-扩展认知3-个维度决定-llm-调用次数) + [Day 4 ⑤ write-memory-to-messages-deep-dive](../day4-agents/05-write-memory-to-messages-deep-dive.md)

</details>

---

## Q13（★★★★ 实战应用）：给你 5 种任务，分别选 ToolCallingAgent 还是 CodeAgent？

任务列表：
- A. 客户咨询助手，每个用户问题独立调一个 KB 查询工具
- B. 数据分析：拉取 10 个城市天气 → 计算平均 → 排序 → 输出 top 3
- C. 文件处理：读 csv → 统计每列均值 / 标准差 → 生成报告
- D. 网络爬虫 agent：根据用户搜索词查多个网站 → 比较 → 推荐
- E. 数学解题：根据题目类型选择不同求解策略 → 调用计算工具

<details>
<summary>👀 看答案</summary>

| 任务 | 选择 | 理由 |
|---|---|---|
| A. 客户咨询（每问独立调）| **ToolCallingAgent** | 单工具调用模式，无计算 / 控制流，简单白名单更安全 |
| B. 数据分析（10 城市 + 计算）| **CodeAgent** | 多工具 + 算数 / 排序 / 选择 —— ToolCalling 至少 11+ 步 vs CodeAgent 1 步 |
| C. 文件处理（统计）| **CodeAgent** | 算数 + 字符串 + 数据结构，pandas/numpy import 白名单（需 `additional_authorized_imports`）|
| D. 爬虫比较（链式依赖）| **CodeAgent** | 比较多源结果是典型链式 + 条件分支，parallel 救不了 ToolCalling |
| E. 数学解题（条件分支选策略）| **CodeAgent** | 经典 if-else 决策点 —— "如果题目是 X 类型就调 A 否则调 B" |

**通用规律**：除非任务**确实只是"每次独立调一个工具就完事"**，否则 CodeAgent 都更省钱、更稳健。

**溯源**：[03 §12 实战选型决策树](03-impl-diff-deep-dive.md#12-实战选型决策树)

</details>

---

## Q14（★★★★ "看会"层）：如果你要给 smolagents 加一个 **`HybridAgent`** —— LLM 既能用 function calling 调工具又能写代码，怎么改？

<details>
<summary>👀 看答案</summary>

**思路**：继承 `MultiStepAgent`，重写 `_step_stream`，混合两边的动作 ③ ④。

**关键决策**：

1. **system_prompt 教 LLM**：可以同时输出 tool_calls 或 `<code>...</code>`，两个选项任选
2. **请求 body**：`tools=...` + 不传 `response_format`（让 LLM 自由用 function calling 或代码）
3. **动作 ③ parse output**：先看 `chat_message.tool_calls` 非空 → 走 ToolCalling 路径；否则 `parse_code_blobs` 抠代码 → 走 CodeAgent 路径
4. **动作 ④ execute action**：根据 ③ 分支执行 —— `process_tool_calls` 或 `python_executor`
5. **memory_step 字段**：写 `tool_calls` + 可选写 `code_action`

**会遇到的坑**：

- LLM 偏好不稳定（可能某步调 tool 某步写代码，难调试）
- system_prompt 设计复杂（既要教 JSON 又要教代码格式）
- 错误处理类型增多（两边的异常都可能出）

**值得做吗**：实际不太值得 —— smolagents 团队把两条路径分开正是因为**统一抽象很难做好**。CodeAgent 已经能调工具（Layer 1），HybridAgent 的"额外价值"小于复杂度成本。

**这个题考的是**：

- 看懂 Day 5 Template Method 设计（子类必填 _step_stream，基类外循环不变）
- 看懂 5 步骨架的 ③ ④ 是真正的"风格分歧点"
- 能用现有概念组合出新方案（即使方案不一定值得做）

**溯源**：[00 mental model](00-step-stream-role-overview.md) + [03 §11 能力边界](03-impl-diff-deep-dive.md#11-差异维度-9能力边界llm-能做什么--不能做什么)

</details>

---

## 自检评分

- ✅ **12-14 题答对** = Day 5 完全掌握，可以推 Day 6
- ⚠️ **9-11 题答对** = 复习溯源笔记里的关键章节再来一遍
- 🆘 **< 9 题答对** = 重读 00 mental model + 01 / 02 演出版（重点剧本里的变化点）

---

## 已知"待实证"点（不影响通过自检，但记得有）

[questions.md "Day 5 待实证"](../../questions.md) 3 条：
- 🔬 第 2 幕 `arguments` 字段类型
- 🔬 第 4d 幕 `memory_step.tool_calls` 写回时机
- 🔬 state 储物柜跨步骤闭环

这 3 个是 01 笔记里的源码推演，**调试环境已通但未单点验证**。Day 6 / Week 3 实战时如果发现实际值不符，回来修笔记。

---

## 关联阅读

- 上游：本笔记溯源的 5 篇 Day 5 笔记
- 下游 Day 6 [local_python_executor.py](../../../../src/smolagents/local_python_executor.py) — 沙箱深度（CodeAgent 第 4 幕的内部）
- 下游 Day 7 综合 —— 调用链全图 + Week 2 总结

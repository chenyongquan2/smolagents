# smolagents 学习计划

> 目标：通过阅读和动手改造 smolagents 源码，入门 AI agent 开发。
> 周期：约 4 周（每天 1-2 小时）
> 前置：能读写基础 Python（函数、类、装饰器）。
>
> **配套笔记**：[notes/](notes/) 目录（含索引、写作规范、所有学习笔记）
> **环境/调试**：[notes/01-setup/](notes/01-setup/)

---

## 第 1 周：搞懂"什么是 agent"（概念 + 跑通）

**目标**：能用一句话解释清楚 agent 和普通 LLM 调用的区别。

- **Day 1-2 概念**
  - 读 [docs/source/zh/conceptual_guides/intro_agents.md](../docs/source/zh/conceptual_guides/intro_agents.md)
  - 读 [docs/source/zh/conceptual_guides/react.md](../docs/source/zh/conceptual_guides/react.md)（ReAct："思考-行动"循环）
- **Day 3 安装跑通**
  - 跑通 README 那个豹子的例子
  - 必开 `stream_outputs=True`，亲眼看 agent 一步步思考
- **Day 4-5 跟 Guided Tour**
  - [docs/source/zh/guided_tour.md](../docs/source/zh/guided_tour.md)，每个例子都自己敲一遍

**本周产出**：能说清 `CodeAgent`（Python 代码作为动作）和 `ToolCallingAgent`（JSON 作为动作）的区别。

---

## 第 2 周：读核心源码（最重要的一周）

**本周终极目标**：能默画出这张调用链 ——
`User 输入 task → memory 加 task → model 生成 → 解析代码 → 执行 → 结果回 memory → 再生成…直到 final_answer`

每个箭头都能指出对应**哪个文件、哪个函数、哪一行**。

### 6 天阅读路线（从小到大、从外到内）

| 天 | 文件（行数） | 重点范围 | 当日学习目标 |
|---|---|---|---|
| **Day 1** | [memory.py](../src/smolagents/memory.py) (316) | 全文 | 理解 agent 记忆数据结构 + `to_messages()` 翻译机制 |
| **Day 2** | [tools.py](../src/smolagents/tools.py) (1422) | 仅 Tool 基类（约前 400 行） | 理解 Python 函数 → LLM tool schema 的转换 |
| **Day 3** | [models.py](../src/smolagents/models.py) (2102) | 仅 `Model` 基类 + `InferenceClientModel`（约 600 行） | 理解 LLM 请求体的拼装过程 |
| **Day 4** | [agents.py](../src/smolagents/agents.py) (1814) **上半** | `MultiStepAgent.__init__` + `run()` | 理解外层 ReAct 循环的控制流 |
| **Day 5** | [agents.py](../src/smolagents/agents.py) **下半** ⭐ | `_step_stream()` + 两个子类实现 | 理解一步内部完整发生了什么 —— 仓库的"心脏" |
| **Day 6** | [local_python_executor.py](../src/smolagents/local_python_executor.py) (1768) | 浏览即可 | 高层理解 Python 代码安全执行流程 |
| **Day 7** | — | 综合产出 | 串成调用链图 + 写 Week 2 总结 |

### 每日验收标准（学完应能）

**Day 1 · memory.py**
- 默画 7 个 Step 类的关系（`MemoryStep` 基类 → 6 个子类）
- 解释 `ActionStep.to_messages()` 如何把一轮"思考-行动-观察"拆成 3-4 条 ChatMessage
- 看到 `agent.memory.steps[2]` 的内容，能预测下一次 `model.generate()` 收到的 messages

**Day 2 · tools.py**
- 解释 `Tool.__init_subclass__` 在 import 阶段做了什么校验
- 区分 `forward()`（业务逻辑） vs `__call__()`（框架包装）
- trace 一个 tool 函数 → JSON schema → HTTP 请求体 `tools` 字段的完整路径

**Day 3 · models.py**
- 说清 `Model.generate()` 的入参 / 返回结构
- 亲眼看到一次真实请求的 JSON body，并指出每个字段来自 memory 的哪个 step

**Day 4 · agents.py 上半**
- 默写 `run()` 的伪代码（while 循环 + max_steps + callback + error 捕获）
- 解释 `agent.run()` 的 `stream=True` 区别
- 在 `run()` 设断点跟一个完整 task

**Day 5 · agents.py 下半 ⭐**
- 默写 `_step_stream()` 的伪代码（write_memory_to_messages → model.generate → 解析输出 → 执行 → 写回 memory → yield）
- 对比 CodeAgent vs ToolCallingAgent 在"解析输出"和"执行动作"两环节的代码差异
- 拿 [compare_agents.py](scripts/compare_agents.py) 单步走，每个分歧点都知道源码位置

**Day 6 · local_python_executor.py**
- 说出大致流程：字符串 → AST 解析 → 白名单检查 → 受控执行
- 解释为什么 CodeAgent 不会让 LLM 删你硬盘

**Day 7 · 综合**
- 在本文件写出 Week 2 总结（参考 Week 1 格式：核心洞察 + 踩坑 + 笔记产出）
- 给 Week 3 选定具体题目

### 学习目标的 3 个层次（每天自检）

| 层次 | 问题 | 通过标准 |
|---|---|---|
| 1. 看懂 | "这段代码做了什么？" | 一句话概括函数功能 |
| 2. 看透 | "为什么这样写？" | 想到一个替代设计并说出 trade-off |
| 3. 看会 | "让我改/扩展，能动手吗？" | 心里能写出修改方案 |

Day 1-3 至少层次 2；Day 4-5（核心）必须层次 3；Day 6 层次 1 即可。

### 学习方法 & 避坑

- **不要纯看代码** —— 边读边在源码加 `print` 或断点，跑 [compare_agents.py](scripts/compare_agents.py) 设断点是最佳姿势
- Day 2-3 **故意只读一部分**：tools.py 后半全是各种第三方集成（HF Hub、MCP、Gradio），models.py 后半是各种供应商封装（OpenAI、LiteLLM、Bedrock），第一遍跳过，需要时再回查
- Day 5 是难点高峰：`_step_stream()` 是生成器（yield），如果 Python 生成器不熟，单独花时间补一下

---

## 第 3 周：动手做（写自己的 agent）

光读不写没用。挑 **2 个**任务做：

1. **写一个自定义 Tool**：参考 [docs/source/zh/tutorials/tools.md](../docs/source/zh/tutorials/tools.md)。比如"查天气"或"读本地文件"工具
2. **挑一个 example 改造**：
   - 简单：[examples/text_to_sql.py](../examples/text_to_sql.py)
   - 中等：[examples/rag.py](../examples/rag.py)
   - 进阶：[examples/multiple_tools.py](../examples/multiple_tools.py)
3. 读 [docs/source/zh/tutorials/building_good_agents.md](../docs/source/zh/tutorials/building_good_agents.md) — 实战经验

**本周产出**：一个属于自己的、能解决具体问题的小 agent。

---

## 第 4 周：进阶 + 看更大世界

1. **多 Agent 协作**：[docs/source/zh/examples/multiagents.md](../docs/source/zh/examples/multiagents.md)
2. **MCP 协议**：[src/smolagents/mcp_client.py](../src/smolagents/mcp_client.py) — Claude/Cursor 都在用的 agent-工具标准协议
3. **安全沙箱**：[docs/source/zh/tutorials/secure_code_execution.md](../docs/source/zh/tutorials/secure_code_execution.md)
4. **横向对比**：翻翻 LangGraph、AutoGen、CrewAI 的 README，对比设计差异

---

## 学习原则

- 不要追求一次读懂所有代码。第一遍只抓主干，细节第二遍再说。
- 每天必须跑代码。看十页文档不如改一行代码跑一次。
- 准备一个 LLM API key：HuggingFace Inference 免费额度先用；要稳定就用 OpenAI / Anthropic / DeepSeek。

---

## 进度记录

> 每天/每节学完，在这里写一两句话：今天看了什么、卡在哪、有什么疑问。

- [x] **Week 1 Day 1-2**：概念阅读 — intro_agents + ReAct，已产出 [what-is-agent.md](notes/02-concepts/what-is-agent.md)
- [x] **Week 1 Day 3**：跑通豹子 demo — [my_first_agent.py](scripts/my_first_agent.py)，配套 3 篇环境笔记（运行/调试/代理）
- [x] **Week 1 Day 4-5**：Guided Tour — 30 分钟扫读 + Tool 子类实操；写了 [compare_agents.py](scripts/compare_agents.py)（实测 ToolCallingAgent 5 步 vs CodeAgent 2 步，答案都是 86°F）
- **Week 2**（按天打勾）：
  - [x] **Day 1**：[memory.py](../src/smolagents/memory.py) ✅ 全部 316 行读完 —— 详见下方 [Week 2 Day 1 学习总结](#week-2--day-1-学习总结2026-05-02--2026-05-03)（10 篇笔记 + 1 个实验）
  - [x] **Day 2**：[tools.py](../src/smolagents/tools.py) 基类（Python 函数 → tool schema） ✅ —— 详见下方 [Week 2 Day 2 学习总结](#week-2-day-2-学习总结2026-05-04--2026-05-05)（8 篇笔记 + 3 个实验脚本 + 教学宪法升级）
  - [x] **Day 3**：[models.py](../src/smolagents/models.py) 基类 + InferenceClientModel（请求体拼装） ✅ —— 详见下方 [Week 2 Day 3 学习总结](#week-2-day-3-学习总结2026-05-05--2026-05-06)（11 篇笔记 + 1 个实验脚本 + 4 角色术语统一 + LLM/服务器分层心智模型）
  - [x] **Day 4**：[agents.py](../src/smolagents/agents.py) 上半（`MultiStepAgent.run()` 外循环）✅ —— 12 篇笔记 in `day4-agents/` + stream 概念笔记 + abc 实证脚本 + 03-source/ 子目录化重构
  - [x] **Day 5**：[agents.py](../src/smolagents/agents.py) 下半 ⭐（`_step_stream()` 心脏）✅ —— 5 篇 Day 5 笔记 ([00 骨架](notes/03-source/day5-step-stream/00-step-stream-role-overview.md) / [01 ToolCallingAgent 演出版](notes/03-source/day5-step-stream/01-toolcalling-walkthrough.md) / [02 CodeAgent 演出版](notes/03-source/day5-step-stream/02-codeagent-walkthrough.md) / [03 9 维度差异对比](notes/03-source/day5-step-stream/03-impl-diff-deep-dive.md) / [04 调试操作手册](notes/03-source/day5-step-stream/04-debugging-walkthrough.md) / [self-check 14 题](notes/03-source/day5-step-stream/self-check.md)) + 概念笔记 [tools-are-python-callables](notes/02-concepts/tools-are-python-callables.md) + proxy-issue 增加 SOCKS5 配置子节。**笔记体系决策**：删 line-by-line 笔记，统一演出版（剧本 + 设计意图 + FAQ + 闭环），单子类单篇全覆盖。Day 5 验收三项全过：① 默写 5 步骨架 ② 对比两子类差异 ③ compare_agents.py 调试可走通
  - [ ] Day 6：[local_python_executor.py](../src/smolagents/local_python_executor.py)（浏览）
  - [ ] Day 7：综合 —— 调用链图 + Week 2 总结
- [ ] **Week 3**：自定义 Tool + 改造一个 example
- [ ] **Week 4**：多 agent / MCP / 沙箱 / 横向对比

---

## Week 1 学习总结（2026-04-26 ~ 2026-05-02）

> 一句话定调：**用 1 周时间不仅完成"看懂 agent"的入门目标，还实质上预习了 Week 2 的核心机制（ReAct 循环、协议层、工具创建底层），为读源码打下了远超预期的认知基础。**

### 7 条最值得记住的核心洞察

1. **Agent ≠ 调一次 LLM，而是 ReAct 循环**：思考 → 行动 → 观察，反复直到 `final_answer`
2. **CodeAgent vs ToolCallingAgent 的本质 = 动作格式**（Python 代码 vs JSON tool_calls），分水岭在请求体里有没有 `tools` 字段
3. **LLM 是无状态的**，"进度感"完全来自每幕重发的 messages 历史 —— `write_memory_to_messages()` 把 `memory.steps` 翻译成 messages 重新喂回
4. **Chat Completion 协议名字暴露本质**：LLM 永远在做"补全"，messages 数组只是把对话当未完成的剧本让它补完 assistant 的下一句
5. **Model 类对应的是"调用渠道"，不是"模型"**。同一个 Llama-3.3 可以走 5 种调用方式，选哪个看部署条件
6. **`@tool` 内部就是动态构造 Tool 子类**，区别只在能不能带 `__init__` 参数和实例状态（`@tool` 是 staticmethod，挂不住资源）
7. **Prompt caching 缓存的是 KV 不是输出**。因 causal attention，前缀 KV 不依赖后续 token，所以能跨幕复用 —— agent 是最大受益者

### 实战踩坑收获

- **Thinking 模型 + ToolCallingAgent → 400**：thinking 模型常不支持 OpenAI `tools` 字段，换 `Qwen2.5-72B-Instruct` 解决
- **`len(memory.steps)` 包含 TaskStep**：5 = 1 TaskStep + 4 ActionStep；真正反映 ReAct 轮数的是 ActionStep 数量
- **`__init__` 只跑一次（实例化时），forward 跑 N 次**（每次 LLM 调用） —— 这是 Tool 子类能预加载重型资源的根本原因

### 笔记产出（5 篇核心 + 1 篇 deferred）

- [02-concepts/what-is-agent.md](notes/02-concepts/what-is-agent.md) — Agent 概念 + ReAct
- ⭐ [02-concepts/codeagent-vs-toolcallingagent.md](notes/02-concepts/codeagent-vs-toolcallingagent.md) — 8 节，含完整执行剧本 + ReAct 机制 + prompt caching 原理
- [02-concepts/model-and-protocols-overview.md](notes/02-concepts/model-and-protocols-overview.md) — 7 节，含 Chat Completion 名字溯源 + Model 子类选型决策树
- [02-concepts/tool-creation-decorator-vs-subclass.md](notes/02-concepts/tool-creation-decorator-vs-subclass.md) — 8 节，含 `__init__` vs `forward` 区分
- [05-advanced/llm-protocols-deep-dive.md](notes/05-advanced/llm-protocols-deep-dive.md) — `deferred`，协议家族深入对比，时机到了再读

### 已超出原计划

| 原计划要求 | 实际达到 |
|---|---|
| 能讲清两种 agent 的区别 | 不仅讲清，还能画每幕 messages 演进、step 计数机制、prompt caching 原理 |
| 跟 Guided Tour | 30 分钟扫读 + Tool 子类实操（含金量 ≥ 逐例敲）|
| —（计划没要求） | 协议层完整认知（Chat Completion 来历、Model 子类选型）|
| —（计划没要求） | 工具机制底层（`@tool` = 动态子类、staticmethod 限制）|

### Week 2 入场提示

按计划顺序读源码：`memory.py → tools.py → models.py → agents.py → local_python_executor.py`。

**预期感受**：会有大量"哦原来如此"的瞬间 —— Week 1 已经把"为什么"想清楚了，Week 2 只剩"怎么写"待补全。**关键方法**：边读边在源码加 `print`/断点，跑 `compare_agents.py` 设断点是最好的源码阅读姿势。

---

## Week 2 Day 1 学习总结（2026-05-02 ~ 2026-05-03）

> **一句话定调**：用 Day 1 一天时间读完 [memory.py](../src/smolagents/memory.py) 全部 316 行，并借机补齐 3 篇 Python 中级语法预习（`@dataclass` / 迭代协议 / `yield`），通过 [planning_demo.py](scripts/planning_demo.py) 实证验证 PlanningStep 重规划机制 —— 为 Day 2-7 读 1400+ 行源码扫清基础障碍。

### 7 条最值得记住的源码侧核心洞察

1. **多态契约**：每个 Step 子类必须实现 `to_messages()`，是 Week 1 "messages 重发机制"的实现侧。基类用 `raise NotImplementedError` 强制约束（不用 `abc.ABC` 是因为和 `@dataclass` 元类冲突）
2. **Plan 是 hint 不是 state**：未执行的 plan 项不被框架追踪，靠 LLM 从 observation 自行推理 —— 实验里 Updated Plan 4 步 vs Initial 6 步证实
3. **Role 是 LLM 行为的方向盘**：伪造 user 消息（"Now proceed"）制造 role 切换，让 LLM 不卡在 plan 模式 —— role 标记不是 metadata，是 chat template 里的特殊 token
4. **Prompt 工程是双向控制**：YAML 模板规定结构（Updated Plan 4 段子标题严格来自 [toolcalling_agent.yaml:184-188](../src/smolagents/prompts/toolcalling_agent.yaml:184)）+ stop_sequences (`<end_plan>`) 强制截断 LLM 跑题
5. **`summary_mode` 隐藏"想法"保留"事实"**：PlanningStep 全隐身（`return []`）、ActionStep 只藏 `model_output`（其他 4 分支照常输出），让重 plan 永远基于 observation 而非旧想法
6. **持久化通道 vs 事件通道**：memory.steps 走持久化（喂 LLM + replay）、FinalAnswerStep 走 generator yield 事件（不存）。两条通道独立设计，是 smolagents 核心哲学
7. **MRO walk + Observer 模式**：CallbackRegistry 一行 `for cls in __mro__` 让"基类注册 = 监听所有子类"。这是 smolagents 主要扩展点，Django signals / PyTorch hooks / HF callbacks 都是同一模式

### 3 条 Python 基础认知（意外之得）

8. **Python 没有"字段声明"语法**：实例属性是 `self.x = ...` 赋值时凭空冒出来的；`@dataclass` 是**代码生成器**（自动写 `__init__` 里的 `self.x = x` 赋值）
9. **Iterable ≠ Iterator**：list 是 iterable 不是 iterator（`next([1,2,3])` 报错）；generator 是少数自身就是 iterator 的对象（`iter(g) is g`）
10. **`yield` = 可暂停的 `return`**：函数遇到 yield 暂停吐值，下次被 next 时从暂停处继续 —— 让 smolagents 长 ReAct 循环能被实时消费

### 实战踩坑收获

- **planning_demo.py 三个核心预测全验证 + 4 个彩蛋**：触发位置符合 `step_number=1, 1+N, 1+2N` 公式；`summary_mode=True` 让 PlanningStep 返回空消息；Updated Plan 自动剔除已完成步骤；`<end_plan>` 是 prompt 协议 + stop_sequences 双保险
- **修正自己的错误**："CodeAgent 的 tool_calls 通常 None" 是错的 —— CodeAgent 也填 tool_calls，但是合成的 `ToolCall(name="python_interpreter", arguments=<code>)`（让两种 agent 的 replay/log 机制统一）
- **prompt 模板"填空机"实证**：Updated Plan 里的 "Facts that we have learned" 4 段结构**严格来自 YAML 模板硬规定**，不是 LLM 自由发挥 —— LLM 在 prompt 工程里其实是填空机
- **`is_final_answer=True` 的 ActionStep 仍会被 to_messages 翻译**（在 multi-agent / 跨 run 记忆 / 同 agent 复用 3 种场景）。`is_final_answer` 只用来让 while 循环退出

### 笔记产出（10 篇 + 1 实验）

**Python 预习系列（3 篇）**：
- [python-class-and-dataclass.md](notes/03-source/python-prep/python-class-and-dataclass.md) — `@dataclass` / `self` / 抽象方法 / "Python 没有字段声明"
- [python-iterables-iterators.md](notes/03-source/python-prep/python-iterables-iterators.md) — 迭代协议、`iter()` / `next()` 关系、自定义类怎么实现
- [python-generators-yield.md](notes/03-source/python-prep/python-generators-yield.md) — `yield` 暂停-恢复模型、`Generator[X]` 注解

**memory.py 源码系列（6 篇）**：
- [memory-data-structures.md](notes/03-source/day1-memory/memory-data-structures.md) — 鸟瞰 + Step 家族 4 个简单类
- [planning-mechanics.md](notes/03-source/day1-memory/planning-mechanics.md) — PlanningStep 全机制 + 4 个遗留问题已解答
- ⭐ [action-step-anatomy.md](notes/03-source/day1-memory/action-step-anatomy.md) — ActionStep 13 字段 + 5 分支 to_messages
- ⭐ [final-answer-step.md](notes/03-source/day1-memory/final-answer-step.md) — 事件 vs 记录 + Day 1 全图谱
- [agent-memory-container.md](notes/03-source/day1-memory/agent-memory-container.md) — AgentMemory 5 方法 + reset 设计
- [callback-registry.md](notes/03-source/day1-memory/callback-registry.md) — Observer 模式 + MRO walk

**通用概念（1 篇）**：
- [chat-message-roles.md](notes/02-concepts/chat-message-roles.md) — role 标记的 LLM 训练原理

**实验脚本（1 个）**：
- [planning_demo.py](scripts/planning_demo.py) — 周期性重规划实证

### 已超出原计划

| 原计划要求（Day 1 当日学习目标） | 实际达到 |
|---|---|
| 默画 7 个 Step 类的关系 | ✅ 不仅默画，还实证 FinalAnswerStep 不在 list 类型注解的设计意图 |
| 解释 ActionStep.to_messages 的 3-4 条 ChatMessage | ✅ 更精确：**0-5 条**（按字段填充情况），并看清 summary_mode "隐藏想法保留事实"的设计精髓 |
| 看 memory.steps[2] 能预测下次 messages | ✅ 通过 planning_demo.py 实证验证 |
| —（计划没要求）| Python 中级语法补齐 3 篇预习（class / iter / yield）|
| —（计划没要求）| PlanningStep 重规划完整机制 + 实证实验 |
| —（计划没要求）| Chat message role 的 LLM 训练原理 |
| —（计划没要求）| AgentMemory + CallbackRegistry 完整覆盖（原计划 Day 6 才会触及）|
| —（计划没要求）| YAML prompt 模板 + `<end_plan>` stop_sequences 协议层认知 |

### 🐞 Day 1 单步调试夯实（2026-05-04）

为补"读懂代码"和"看到运行时画面"之间的差距，做了 3 个精准断点的单步调试：

| 断点 | 文件:行号 | 验证机制 |
|---|---|---|
| A | [memory.py:92](../src/smolagents/memory.py:92) | `ActionStep.to_messages()` 5 分支逐条 append messages |
| B | [agents.py:768](../src/smolagents/agents.py:768) | `write_memory_to_messages()` 每次 ReAct 全量重发 messages |
| C | [memory.py:314](../src/smolagents/memory.py:314) | `CallbackRegistry` 的 MRO walk（基类注册 = 监听全部子类）|

调试代码（注册基类 callback 的 `my_cb_old` / `my_cb_new`）保留在 [planning_demo.py](scripts/planning_demo.py) 里作为以后参考，带 `🐞 Day 1 单步调试` 标识，方便随时回查或 revert。

**收益**：Day 1 完成度从"80% 读懂代码 + 实证一次"升级到"100% 读懂 + 实证 + 单步走过关键路径"。为 Day 4-5 的 1800 行 agents.py 攒下了**"在源码里设断点 + `justMyCode: false` + 多次命中跳到目标类型"** 的调试肌肉记忆 —— 那时再读 `_step_stream` 这种核心硬菜，光读不调试容易迷路。

### Day 2 入场提示

按计划读 [tools.py](../src/smolagents/tools.py) 的 Tool 基类（约前 400 行）。核心要看：
- `Tool.__init_subclass__` 的导入时校验（涉及 Python 元类机制，[user_profile memory](#) 已标记待解释）
- `forward()` vs `__call__()` 框架包装层
- tool → JSON schema 的字段映射

**预期感受**：Day 1 的 Python 预习已经把语法障碍清得很干净（`@dataclass` / type hints / `Any` / 迭代协议都熟悉了）。Day 2 主要新概念：`__init_subclass__`（元类相关，比 `@dataclass` 更深一层）+ schema 生成机制。可能会再产出 1 篇 Python 预习笔记。

**关键方法继续不变**：边读边在源码加 `print`/断点，跑 [compare_agents.py](scripts/compare_agents.py) 是最好的源码阅读姿势。

---

## Week 2 Day 2 学习总结（2026-05-04 ~ 2026-05-05）

> **一句话定调**：用 Day 2 两天时间不仅读完 [tools.py](../src/smolagents/tools.py) Tool 基类核心 ~230 行，**还在过程中固化了"讲解宪法"** —— 任何学习 part 必须先 mental model 后实现。这条宪法将贯穿整个 Week 2 余下时间和 Week 3-4。最终产出 8 篇新笔记 + 3 个实验脚本 + 1 份仓库级 CLAUDE.md。

### 9 条最值得记住的源码侧核心洞察

1. **Tool 类 = 一个零件，一生中接受 2 次质检**：出厂质检（实例化时 `validate_arguments` 查 schema 形状）+ 上岗质检（每次 `__call__` 时清洗参数）。**每件事尽可能放在能做它的最早时机**。
2. **`__init_subclass__` 不直接校验，只装挂钩**：`Tool.__init_subclass__` → `validate_after_init(cls)` → wrap 子类 `__init__`。**用户怎么写都绕不过校验** —— 这是 wrap 模式比"基类 `__init__` 校验"更强的根本原因（后者子类可能忘调 `super().__init__()`）。
3. ⭐ **`validate_arguments` 第 ⑥ 项 = 双源真相对账**：用 `inspect.signature` 反射读 forward 形参，跟 inputs 字典 key 比对。前 5 项都通过也堵不住"用户 inputs 写 city 但 forward 写 location"这种不一致 —— 第 ⑥ 项专治此症。类比 TypeScript 的 `.d.ts` 必须和 `.ts` 实现保持同步。
4. **`__call__` ≠ `forward` 的设计意图 = 横切关注点分离**：`__call__` 是框架包装层（lazy setup / dict→kwargs / 输入清洗 / 输出清洗），`forward` 是用户业务层。用户写 forward 不用关心框架杂事；框架想加新功能不用改用户代码。
5. ⭐⭐ **同一份数据，4 种渲染形状**：CodeAgent prompt 看到"假装的 Python def" / ToolCallingAgent prompt 看到"一行文字描述" / HTTP `tools` 字段看到"OpenAI 标准 JSON" / 磁盘看到"序列化字典"。**LLM 模式不同需要不同呈现** —— 这就是 Tool 真正的核心价值。
6. ⚠️ **HTTP `tools` 字段不是 `to_tool_calling_prompt` 渲染的**！它由独立函数 [models.py:288 `get_tool_json_schema`](../src/smolagents/models.py#L288) 渲染，**不在 Tool 类上**。原因是关注点分离 —— 它依赖外部协议（OpenAI/Anthropic），属于模型调用层。**这个误解很常见**（Day 2 中段我自己写的笔记都搞错过，后来读源码才发现并修正）。
7. **`nullable` = JSON Schema 标准的"可选参数"标记**：标了的字段不在 OpenAI `required` 列表里，LLM 知道可以不传。`required` 数组（结构化信号）比 description 自然语言对 LLM 更可靠。validate_arguments 第 ⑥ 项还会校验 inputs nullable 和 forward `| None` 注解的双源一致性。
8. **`@tool` 装饰器源码完全验证 Week 1 三个结论**：`class SimpleTool(Tool):` 写在函数内（动态子类）、`forward = staticmethod(wrapped_function)`（挂不住实例资源）、最后 `return SimpleTool()`（返回实例不是类）。**Week 1 → Week 2 闭环完成**。
9. **Tool schema 全是类属性而不是 `__init__` 参数**：4 个理由 —— schema 是固有性质应共享 / 省内存 / `__init_subclass__` 在子类定义时能查 / 错误更早暴露。

### 3 条 Python 基础认知（意外之得）

10. **`__init_subclass__` ≠ `__init__` ≠ `__new__`**：钩子触发于子类**定义时**（不是实例化时）。Python 3.6 PEP 487 引入，比 metaclass 轻量；smolagents 用它"装挂钩 wrap 子类 `__init__`"。
11. **`abc.ABC` 硬约束 vs `raise NotImplementedError` 软约束**：前者实例化时崩、后者调用时崩。BaseTool 用前者（框架必经入口）、Tool.forward 用后者（给 wrapper 子类留绕过的口子）。**同一个文件混用两种是有意的**。
12. **类属性 vs 实例属性**：Python 没有"字段声明"语法，**写在 class 体里赋值就是类属性，写在 `__init__` 里 `self.x` 就是实例属性**。`obj.x` 取值时先查实例 → 再查类（向类回退），所以类属性"看起来像"实例属性。Tool 的 4 个 schema 字段全是类属性，唯一的实例属性是 `is_initialized`。

### 实战踩坑收获

- **Day 2 中段写的 `tool-validation-three-layers.md` 违宪**（直接 line-by-line，没先讲 mental model），用户反馈"难以理解"。后来 5 步处理：① 写 mental-model 笔记 → ② 抢救独家细节合并 → ③ 删除违宪笔记 → ④ 改索引 → ⑤ 把"违宪 SOP"写进宪法记忆。**这次踩坑直接让宪法升级到"宇宙级规则"**。
- **role-overview 笔记里关于 `to_tool_calling_prompt → OpenAI tools 字段` 的说法是错的**。读段 5 源码时发现 + 修正。**反映的不只是事实错误，是当时没想清楚 ToolCallingAgent 实际有 2 个渲染产出（prompt 文字 + HTTP JSON）来自不同位置**。修正动作 =顺手做的最有价值的副产物。
- **Windows 控制台 GBK 编码**会让 demo 脚本里的 emoji + 中文乱码 / UnicodeEncodeError。**所有 demo 脚本顶部必加 `sys.stdout.reconfigure(encoding="utf-8")`** —— 这条已固化到 [CLAUDE.md](../CLAUDE.md) 仓库级指令里。

### 笔记产出（8 篇 + 3 实验）

**Python 预习系列（3 篇新增）**：
- [python-init-subclass.md](notes/03-source/python-prep/python-init-subclass.md) — `__init_subclass__` 钩子机制（vs `__init__` / metaclass / `super` 链式传递）
- [python-abc-abstract-base-class.md](notes/03-source/python-prep/python-abc-abstract-base-class.md) — `abc.ABC` + `@abstractmethod` 硬约束 vs 软约束
- [python-class-vs-instance-attributes.md](notes/03-source/python-prep/python-class-vs-instance-attributes.md) — 类属性 vs 实例属性，回答"Tool 的 name 到底是哪种"

**Day 2 tools.py 系列（5 篇新增，宪法 3 层结构）**：
- ⭐ [tool-class-role-overview.md](notes/03-source/day2-tools/tool-class-role-overview.md) — Tool 类整体角色（3 客户 + 4 类属性 + 4 生命周期组）
- ⭐ [tool-lifecycle-checks-mental-model.md](notes/03-source/day2-tools/tool-lifecycle-checks-mental-model.md) — 出厂/上岗两次质检（含实现细节速查）
- ⭐ [tool-schema-rendering-mental-model.md](notes/03-source/day2-tools/tool-schema-rendering-mental-model.md) — 一份数据 4 种渲染形状（含修正之前误解）
- [tool-input-nullable.md](notes/03-source/day2-tools/tool-input-nullable.md) — JSON Schema nullable 含义 + 双源真相对账
- [tool-decorator-implementation.md](notes/03-source/day2-tools/tool-decorator-implementation.md) — `@tool` 装饰器源码验证 Week 1 三个结论 + 2 个延伸洞察

**实验脚本（3 个）**：
- [init_subclass_demo.py](scripts/init_subclass_demo.py) — 6 个独立 demo 验证 `__init_subclass__` 各种行为（含 smolagents wrap 模式仿写）
- [abc_demo.py](scripts/abc_demo.py) — 6 个 demo 对比硬约束 vs 软约束（含 BaseTool / Tool.forward 双写法的反证实验）
- [tool_schema_trace.py](scripts/tool_schema_trace.py) — 6 个 demo 看 1 个 Tool 实例如何被渲染成 4 种形态（最有价值的是 Demo 6 同一个 nullable 字段的 3 种处理对比）

**仓库级产出（1 个）**：
- [CLAUDE.md](../CLAUDE.md) — 仓库级 Claude Code 指令（personal-study 分支约定 / learning 目录布局 / 笔记 3 层结构 / 编码 fix 强制要求 / 教学宪法 pointer）

### 已超出原计划

| 原计划要求（Day 2 当日学习目标） | 实际达到 |
|---|---|
| 解释 `Tool.__init_subclass__` 在 import 阶段做的校验 | ✅ **修正措辞** —— 实际只 wrap、不直接校验，真校验在实例化时 |
| 区分 `forward()` vs `__call__()` | ✅ 不仅区分，还讲清楚 4 件横切关注点分离 + 反证"如果 forward 也用 @abstractmethod 会怎样" |
| trace tool → JSON schema → HTTP body 的完整路径 | ✅ 写了 [tool_schema_trace.py](scripts/tool_schema_trace.py) 亲眼对比 4 种渲染形态 + 6 个 demo |
| —（计划没要求）| 把 Python 中级语法补齐 3 篇预习（init-subclass / abc / class-vs-instance-attr）|
| —（计划没要求）| **固化教学宪法**：先 mental model 后实现，写进 user 记忆 + CLAUDE.md，**适用所有未来学习 part** |
| —（计划没要求）| 创建 [CLAUDE.md](../CLAUDE.md)（仓库级 + 跨设备同步） + 升级笔记 3 层结构（role-overview / mental-model / 实现细节） |
| —（计划没要求）| 修正 role-overview 关于 OpenAI tools 字段的错误描述（读段 5 源码时发现）|
| —（计划没要求）| 验证并落地 Week 1 → Week 2 闭环（`@tool` 装饰器源码彩蛋）|

### Day 3 入场提示

按计划读 [models.py](../src/smolagents/models.py) Model 基类 + InferenceClientModel（约 600 行）。核心要看：
- Model 基类的角色（"调用渠道"概念，Week 1 [model-and-protocols-overview.md](notes/02-concepts/model-and-protocols-overview.md) 已铺垫过）
- `Model.generate()` 入参 / 返回结构
- 一次真实请求的 JSON body 拼装过程，每个字段来源
- ⭐ 已经在 Day 2 段 5 见过的 [models.py:288 `get_tool_json_schema`](../src/smolagents/models.py#L288) + [models.py:540 tools 字段拼装](../src/smolagents/models.py#L540) 的上下文

**预期产出**：
- 1 篇 `model-class-role-overview.md`（必须，按宪法）
- 1 篇 `model-generate-mental-model.md`（请求体拼装的 mental model）
- 可能 1-2 篇实现细节笔记
- 可能 1 个实验脚本（抓一次真实请求体，对照源码每个字段来源）

**关键方法继续不变**：先 mental model 再实现 + 边读边在源码加 `print`/断点 + 跑现有 demo 脚本设断点（[my_first_agent.py](scripts/my_first_agent.py) / [compare_agents.py](scripts/compare_agents.py) / 今天的 [tool_schema_trace.py](scripts/tool_schema_trace.py)）。

---

## Week 2 Day 3 学习总结（2026-05-05 ~ 2026-05-06）

> **一句话定调**：用 Day 3 两天时间不仅读完 [models.py](../src/smolagents/models.py) Model 基类 + InferenceClientModel 子类（约 600 行），**还借机建立"4 角色术语统一" + "LLM vs LLM API 服务器分层"两套通用心智模型**，为整个 Week 2 余下时间和 Week 3-4 读 agents.py / 接其他 provider 都打下硬底子。最终产出 11 篇笔记 + 1 个实验脚本。

### 9 条最值得记住的源码侧核心洞察

1. **Model 基类 = "调用渠道" 抽象 + 不发请求**：基类只管"拼 body + 接口契约"，差异（HTTP / 本地推理 / 云 SDK）全在子类。`generate` 是 `raise NotImplementedError` 软约束，**子类必须实现**
2. **`_prepare_completion_kwargs` 5 步流水线**：① 清洗 messages → ② 写 specific 参数 → ③ caller kwargs → ④ self.kwargs 压舱石 → ⑤ 返回。**最早写入的优先级最低**（"用户意图最高 vs 框架默认最低"）
3. ⭐ **`self.kwargs` = 压舱石**：实例化时存的默认参数**最高优先级**，最后一步覆盖一切。配合哨兵 `REMOVE_PARAMETER` 还能**主动删字段**（区分"传 None"和"字段不存在"）
4. ⭐⭐ **Day 2 → Day 3 闭环回收**：HTTP `tools` 字段就在 [models.py:540](../src/smolagents/models.py#L540) `_prepare_completion_kwargs` 步骤 ② 调 [`get_tool_json_schema`](../src/smolagents/models.py#L288) 渲染。Day 2 [tool-schema-rendering-mental-model.md](notes/03-source/day2-tools/tool-schema-rendering-mental-model.md) 的预言完全验证
5. **3 层继承的边界**：Model（拼 body）→ ApiModel（走网络共享：client + rate_limit + retry）→ InferenceClientModel（HF 特定）。**走不走网络是清晰分界线**，本地模型直接继承 Model 跳过 ApiModel
6. **InferenceClientModel.generate 五件事**：① pre-check 协议兼容 → ② 拼 body（含 `convert_images_to_image_urls=True` HF 固定决策）→ ③ 节流 → ④ retry 包裹下真发请求 → ⑤ 解析 + ⭐ stop fallback strip + 包 ChatMessage
7. ⭐ **stop_sequences 的双保险真正含义** = LLM 模型 + LLM API 服务器**两个不同主体协同**，不是"用户保险 + 框架保险"。**stop 是被动检测，prompt 才是主动控制** —— 服务器不能强迫模型输出 stop 字符串，模型必须被 prompt 教过才会输出
8. **三种停止机制（EOS / stop / max_tokens）互补**：EOS = 句号（语义完成）；stop = 逗号（中间暂停）；max_tokens = 物理上限。Agent 协议要求停的位置 EOS **永远不会触发** —— 因为模型按对话语义认为"还没说完"
9. **协议碎片化是 smolagents 写多个子类的根本原因**：每家 provider 协议字段名（OpenAI `stop` vs Anthropic `stop_sequences`）/ 支持范围（reasoning 模型禁 stop）/ 限制都不一样，必须**逐家手工适配** + 维护 `supports_stop_parameter` 白名单

### 4 条通用心智模型（最大的"超出原计划" 收获）

10. ⭐⭐ **LLM 模型 vs LLM API 服务器是两层**（[llm-vs-api-server-architecture.md](notes/02-concepts/llm-vs-api-server-architecture.md)）：模型是无状态纯函数（吃 token 吐概率向量），LLM API 服务器是 HTTP 服务程序（解析 / 调度 / 控制）。**所有协议字段（stop / temperature / tools / max_tokens / response_format / tool_choice）都是给服务器看的，模型完全不知道**
11. ⭐⭐ **服务器内部 8 步流水线**（[llm-api-server-internals.md](notes/02-concepts/llm-api-server-internals.md)）：HTTP 解析 → 队列 → chat_template → tokenize → ⭐ 生成循环（反复调模型 N 次）→ detokenize → 包响应 → HTTP 序列化。**生成 100 token 的回答 = 调模型 100 次**（自回归）；KV cache 让 O(N²) 降 O(N)
12. ⭐ **Chat template 是 messages → token 序列的翻译机制**（[chat-template-explained.md](notes/02-concepts/chat-template-explained.md)）：Qwen / Llama-2 / Llama-3 / Mistral 4 种格式完全不同；特殊 token (`<|im_start|>` 等) 是模型识别 role 边界的根基；**5 → 3 role 降维的真实根因 = chat template 不认非标准 role**（Week 1 chat-message-roles 闭环）
13. ⭐⭐ **4 角色术语约定固化**（用户 / agent 框架 / LLM API 服务器 / LLM 模型）：覆盖整个 Day 3 笔记体系（包括对老笔记的术语审计），消除"调用方 / 客户端 / 应用层 / API / 服务器" 混用的歧义。**这是后续读 agents.py 的硬基础** —— 看到任何协议字段都能立刻定位"给哪一层"

### 实战踩坑收获

- **术语混乱导致用户困惑**：Day 3 中段我多次用"调用方/客户端/应用层"互换 → 用户两次反馈"不够清晰" → 倒逼我建立 4 角色权威术语表 + 审计 5 篇旧笔记。**这次踩坑直接产出 [llm-vs-api-server-architecture.md §2 术语约定]**，从此所有 smolagents 笔记必须用这套术语
- **InferenceClientModel.generate 的 `response_format` 注释 bug**：[models.py:1570](../src/smolagents/models.py#L1570) `response_format` 被注释掉但 pre-check 还在 → 看起来是 bug 或半成品。已记入遗留问题，留作 Week 3-4 实战时验证
- **"被动检测 vs 主动控制" 是初学者最大盲区**：用户问"既然服务器知道 stop，为什么不直接让模型输出？" → 倒逼我深挖 prompt（主动）+ stop（被动）的强依赖关系。最终产出 [model-stop-sequences.md §7 ⭐⭐ 关键澄清]
- **"模型是逐 token 调用 N 次" 是另一个盲区**：不是"调一次拿整个回答"。理解这点后 KV cache / 流式响应 / token 计费 / stop 即时生效全打通

### 笔记产出（11 篇 + 1 实验）

**Day 3 主线（按教学宪法 3 层结构）**：
- ⭐ ① [model-class-role-overview.md](notes/03-source/day3-models/model-class-role-overview.md) — Model 类整体角色（3 客户 + 5 实例属性 + 方法分组 + 为什么基类不发请求）
- ⭐ ② [model-generate-mental-model.md](notes/03-source/day3-models/model-generate-mental-model.md) — `_prepare_completion_kwargs` 5 步流水线 + 三层优先级 + Day 2 闭环回收
- ⭐ ③ [inference-client-model-impl.md](notes/03-source/day3-models/inference-client-model-impl.md) — InferenceClientModel 落地：3 层继承 + ApiModel 三件武器 + generate 五件事

**延伸笔记（对话驱动产出）**：
- [python-args-kwargs.md](notes/03-source/python-prep/python-args-kwargs.md) — `*args` vs `**kwargs`：tuple/dict 区别、为什么 Model 用 `**kwargs`
- [python-sentinel-pattern.md](notes/03-source/python-prep/python-sentinel-pattern.md) — Python 哨兵模式：当 None 不够用时（含 `REMOVE_PARAMETER` 设计意图）
- ⭐ [model-stop-sequences.md](notes/03-source/day3-models/model-stop-sequences.md) — 11 节深度（stop 是谁给谁 / EOS-stop-max_tokens 互补 / 双保险 / **§7 被动检测 vs 主动控制** / 兼容性 + 知识来源 + 协议碎片化）
- [model-generate-params-explained.md](notes/03-source/day3-models/model-generate-params-explained.md) — `_prepare_completion_kwargs` 7 参数详解 + OpenAI 协议字段映射
- [model-rate-limit-and-retry.md](notes/03-source/day3-models/model-rate-limit-and-retry.md) — 节流 vs 重试：调 LLM API 服务器的双层保险

**02-concepts 概念笔记（建立通用心智模型）**：
- ⭐⭐ [llm-vs-api-server-architecture.md](notes/02-concepts/llm-vs-api-server-architecture.md) — LLM 模型 vs LLM API 服务器分层 + **§2 术语约定 4 角色**
- ⭐⭐ [llm-api-server-internals.md](notes/02-concepts/llm-api-server-internals.md) — 服务器内部 8 步流水线 + KV cache + 流式 vs 非流式
- ⭐ [chat-template-explained.md](notes/02-concepts/chat-template-explained.md) — Chat template 翻译机制 + 4 模型格式对比 + 5→3 role 降维根因

**实验脚本（1 个）**：
- 🐞 [inference_request_trace.py](scripts/inference_request_trace.py) — 6 个 demo 用 `TraceModel(Model)` 拦截 `_prepare_completion_kwargs` 输出，亲眼看 body 结构 + 字段来源标注（兑现验收标准 ②）

### 已超出原计划

| 原计划要求（Day 3 当日学习目标） | 实际达到 |
|---|---|
| 说清 `Model.generate()` 入参 / 返回结构 | ✅ 不仅说清，还专门写 [model-generate-params-explained.md] 7 参数详解 + 速查表 |
| 亲眼看到一次真实请求的 JSON body | ✅ [inference_request_trace.py](scripts/inference_request_trace.py) 6 个 demo 全部亲眼验证 |
| —（计划没要求）| **建立 4 角色术语统一**（用户 / agent 框架 / LLM API 服务器 / LLM 模型），审计 5 篇旧笔记，从此所有笔记必须用这套术语 |
| —（计划没要求）| **3 篇 02-concepts 通用心智模型**（架构分层 / 服务器内部 / chat template）—— 远超 models.py 范畴，覆盖整个 LLM 生态认知 |
| —（计划没要求）| 揭示 stop 是"被动检测"，prompt 才是"主动控制"（initiator 最易盲区）|
| —（计划没要求）| 揭示 5→3 role 降维的真实根因 = chat template 不认非标准 role（Week 1 → Day 3 完整闭环）|
| —（计划没要求）| 揭示"模型是逐 token 调用 N 次"（KV cache / 流式响应 / token 计费的认知基础）|

### Day 4 入场提示

按计划读 [agents.py](../src/smolagents/agents.py) **上半**：`MultiStepAgent.__init__` + `run()`（约 800 行）。核心要看：
- 外层 ReAct 循环的控制流（while + max_steps + callback + error 捕获）
- `agent.run()` 的 `stream=True` 区别
- `write_memory_to_messages()` —— Day 1 / Day 3 已多次提到的"翻译器"
- 在 `run()` 设断点跟一个完整 task

**预期产出**：
- 1 篇 `multi-step-agent-role-overview.md`（必须，按宪法）
- 1 篇 `agent-run-mental-model.md`（外循环控制流 mental model）
- 可能 1-2 篇实现细节笔记

**关键方法继续不变**：先 mental model 再实现 + 单步调试 [my_first_agent.py](scripts/my_first_agent.py) 跟 `run()` 完整跑一遍 + 用 Day 3 笔记 4 角色术语描述发生的事。

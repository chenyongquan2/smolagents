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

**目标**：脑子里能画出 agent 跑一步的完整调用链。

按这个**精确顺序**读，不要乱跳：

1. [src/smolagents/memory.py](../src/smolagents/memory.py)（约 316 行）— 最简单，先读
2. [src/smolagents/tools.py](../src/smolagents/tools.py) 的 `Tool` 基类部分 — 工具是怎么定义的
3. [src/smolagents/models.py](../src/smolagents/models.py) 的 `Model` 基类和 `InferenceClientModel` — 其他具体 model 类先跳过
4. **⭐ [src/smolagents/agents.py](../src/smolagents/agents.py)** — 重点看 `MultiStepAgent.run()` 和 `_step_stream()`，这就是 ReAct 循环的实现
5. [src/smolagents/local_python_executor.py](../src/smolagents/local_python_executor.py) — 浏览即可，知道它在解析并执行 LLM 输出的 Python 代码

**学习方法**：边读边在源码里加 `print` 或断点，跑一个简单 agent，亲眼看每个变量的内容。**不要纯看代码**。

**本周产出**：能画出
`User 输入 task → memory 加 task → model 生成 → 解析代码 → 执行 → 结果回 memory → 再生成…直到 final_answer`
这条链路。

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
- [ ] **Week 2**：读源码（memory → tools → models → agents → executor）
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

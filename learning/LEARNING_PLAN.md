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

- [ ] **Week 1 Day 1-2**：概念阅读
- [ ] **Week 1 Day 3**：跑通豹子 demo
- [ ] **Week 1 Day 4-5**：Guided Tour
- [ ] **Week 2**：读源码（memory → tools → models → agents → executor）
- [ ] **Week 3**：自定义 Tool + 改造一个 example
- [ ] **Week 4**：多 agent / MCP / 沙箱 / 横向对比

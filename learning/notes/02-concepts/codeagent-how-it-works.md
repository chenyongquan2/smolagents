---
created: 2026-05-06
status: active
tags: [concepts, codeagent, mental-model, prerequisite-day4]
---

# CodeAgent 工作机制：4 个递进问题串成的完整心智模型

⚠️ **必读前置**：
- [codeagent-vs-toolcallingagent.md](codeagent-vs-toolcallingagent.md)（Week 1 概念）
- [llm-vs-api-server-architecture.md](llm-vs-api-server-architecture.md)（4 角色术语）
- [chat-template-explained.md](chat-template-explained.md)（messages → token）

> 本笔记是**Day 4 读 agents.py 之前的最后认知拼图**。从 4 个递进问题（每个都是初学者真实疑惑）出发，构建 CodeAgent 完整工作机制心智模型。

> 💡 **术语统一**：本笔记严格使用 [llm-vs-api-server-architecture.md §2](llm-vs-api-server-architecture.md) 约定的 4 角色（用户 / agent 框架 / LLM API 服务器 / LLM 模型）。

---

## 1. 一句话定位

CodeAgent 工作机制 = **预定义工具（原子操作）+ LLM 写 Python 代码（编排逻辑）+ 沙箱执行（安全兜底）+ 错误反馈（自我修正）**。

四个组件缺一不可。**LLM 不是直接执行工具，是在写"调度脚本"调度工具**。

---

## 2. ⭐ Q1：CodeAgent 需要告诉 LLM 模型有哪些工具吗？

### 答：必须告诉，但走的是 prompt 文本路径，不是 OpenAI tools 字段

| | ToolCallingAgent | CodeAgent |
|---|---|---|
| 工具信息怎么到模型？ | HTTP body 的 `tools` 字段 → LLM API 服务器拼进 prompt | agent 框架直接把工具描述拼进 system prompt 文字 |
| 渲染调用 | `get_tool_json_schema(tool)` → JSON | `tool.to_code_prompt()` → "假装的 Python def" 文本 |
| body["tools"] 字段 | 有内容 | **空 / 不存在** |
| LLM 输出 | 结构化 `tool_calls` JSON | Python 代码块 |

### 为什么必须告诉？反证

如果不告诉，LLM 模型会瞎猜：
- 自己编造函数名 → `NameError`
- 尝试 `import requests` 自己发 HTTP → 沙箱拒绝
- 或干脆放弃任务

**LLM 模型不会神奇地知道你的 Python 环境里有什么** —— 必须**被告知**。

📚 详见 [tool-schema-rendering-mental-model.md](../03-source/day2-tools/tool-schema-rendering-mental-model.md)（Day 2 写过的 4 种渲染形态）

---

## 3. ⭐ Q2：既然有 tool 代码（如 `get_weather`），为何还要 LLM 写代码？

### 答：tool 是"原子操作"，LLM 写代码是"编排逻辑"

```
预定义 Tool（get_weather/calculate）  =  食材和炊具（厨房里的）
LLM 写代码                            =  厨师（决定怎么用食材做菜）
```

**任务**："今天北京和上海哪个城市更热？"

光有 `get_weather` 工具不够。LLM 实际写：

```python
beijing = get_weather("Beijing")          # ← 调框架预定义工具
shanghai = get_weather("Shanghai")        # ← 调框架预定义工具

# ⬇️ 下面 LLM 自己写（不是工具）
import re
b_temp = float(re.search(r'(\d+)', beijing).group(1))
s_temp = float(re.search(r'(\d+)', shanghai).group(1))
diff = abs(b_temp - s_temp)
hotter = "北京" if b_temp > s_temp else "上海"

final_answer(f"{hotter}更热，热 {diff}°C")  # ← 调框架预定义工具
```

**没有 LLM 这层"决策 + 编排 + 数据处理"代码**，光有工具函数解决不了具体问题。

### 关键认知转变

| 误解 | 实际 |
|---|---|
| Tool = 完整解决方案 | Tool = 单一原子操作 |
| 工具够全 → agent 够强 | 工具是"词汇"，**LLM 编排是"语法"** —— 没有语法说不出句子 |

### ToolCallingAgent 也是同样道理

很多人以为 ToolCallingAgent "调工具就完事"。**错**。多步任务里它仍要靠多轮 ReAct 编排：

```
Round 1: LLM 决定调 get_weather("Beijing") → 框架执行 → "北京 22°C"
Round 2: LLM 决定调 get_weather("Shanghai") → 框架执行 → "上海 28°C"
Round 3: LLM 基于前两次结果决定调 final_answer("上海更热")
```

**LLM 仍在编排**，只是用 JSON 表达"调哪个工具"而不是 Python 代码。

📚 详见 [codeagent-vs-toolcallingagent.md](codeagent-vs-toolcallingagent.md) §3-§5（编排能力差异）+ [compare_agents.py](../scripts/compare_agents.py) 实测（CodeAgent 2 步 vs ToolCallingAgent 5 步）

---

## 4. ⭐ Q3：LLM 能写任意代码吗？

### 答：**能**写"沙箱内有限 Python"，**不能**写任意代码

LLM 写的代码分 3 层：

```
┌──────────────────────────────────────────────────────────┐
│  Layer 3: 调 agent tool（预定义函数）                      │
│      get_weather() / calculate() / final_answer()        │
├──────────────────────────────────────────────────────────┤
│  Layer 2: 纯 Python 计算（沙箱允许）                        │
│      变量、循环、条件、try/except                          │
│      列表/字典/集合操作 / 推导式 / lambda                   │
│      白名单内置函数（print/range/len/sum/sorted...）        │
│      白名单标准库 import（re/math/json/datetime ...）       │
│      ↑ LLM 可以自由写！比 tool 调用范围更广                  │
├──────────────────────────────────────────────────────────┤
│  Layer 1: 沙箱禁止的（安全考虑）                            │
│      任意 import (os/subprocess/socket/requests/__import__)│
│      文件操作 (open/Path)                                  │
│      网络操作（绕过 tool 直接发 HTTP）                       │
│      访问内部对象 (__class__/__globals__/__bases__)        │
│      ↑ 防止 LLM"删硬盘"或"绕过 tool 偷数据"                  │
└──────────────────────────────────────────────────────────┘
```

### 为什么 Layer 1 被禁？

LLM 是**不可信的代码生成者**：
- 可能被 prompt injection 让它写删文件代码
- 可能"自己脑补"后写危险代码（"清理一下临时文件" → `rm -rf /tmp`）

**默认禁所有任意 import**，只白名单纯计算库。**所有外部副作用必须经过 tool 这道审计层** —— 开发者完全控制 agent 能干什么。

### 心智模型

| 角色 | 职责 |
|---|---|
| **Tool**（Layer 3）| LLM 接触**外部世界**的唯一通道（网络 / 文件 / 数据库 / API）|
| **沙箱 Python**（Layer 2）| LLM 的"大脑工作空间" —— 自由处理 / 计算 / 编排 |
| **沙箱禁止**（Layer 1）| 安全边界 —— 防危险操作 |

📚 Day 6 会读 [local_python_executor.py](../../../src/smolagents/local_python_executor.py) 看具体实现（AST 解析 + 白名单 + 受控执行）

---

## 5. ⭐⭐ Q4：谁告诉 LLM 这些限制？

### 答：3 层机制 —— prompt 教（主动）+ 沙箱拒（被动）+ 错误反馈（闭环）

**没人能"强制 LLM 知道"任何东西**。机制是：

### Layer 1（主动）：system prompt 教

CodeAgent 启动时根据 `agent.tools` + `agent.authorized_imports` 自动渲染出这样一段 system prompt（模板见 [code_agent.yaml](../../../src/smolagents/prompts/code_agent.yaml)）：

```
You are an expert agent who can solve any task using Python code.

# 第 ① 部分：教 LLM 模型有哪些工具可用
Here are the tools available:
def get_weather(city: str) -> str:
    """查询某城市当前天气"""
def calculate(expression: str) -> str:
    """计算数学表达式"""
def final_answer(answer: str) -> str:
    """提交最终答案"""

# 第 ② 部分：教 LLM 模型能 import 什么
You can use these Python modules: ['re', 'math', 'json', ...]
You CANNOT import 'os', 'subprocess', 'requests'.

# 第 ③ 部分：教协议规则
Always write code in ```py ... ```<end_code> blocks.
Don't make up Observation yourself.

# 第 ④ 部分：few-shot 示例
Example 1: ...
```

**LLM 模型每轮 ReAct 都看一遍这段说明书**。LLM 训练时学过指令跟随，**倾向于**遵守。

### Layer 2（被动）：沙箱执行时拒

LLM 是不可靠的，可能违规。[local_python_executor.py](../../../src/smolagents/local_python_executor.py) 3 道关：

```
LLM 输出代码字符串
    ↓
① AST 解析（语法树）
    ↓
② AST 遍历检查
    ├─ Import 节点：是否在白名单？不在 → InterpreterError
    ├─ Name 节点：是否在已知作用域？不在 → NameError
    └─ Attribute 节点：访问 __class__ 等？是 → 拒
    ↓
③ 受控执行 → 正常返回 或 抛错
```

### Layer 3（反馈）：错误信息进 observation 让 LLM 自我修正

⭐ **这是最关键的闭环**。

```
ReAct 第 1 轮：
  LLM 写错（试图任意 import）:
    ```py
    import requests
    weather = requests.get("https://api.weather.com/...")
    ```<end_code>
    
  沙箱拒绝 →
  Observation: InterpreterError: Import of 'requests' is not allowed.
               You can only use these modules: ['re', 'math', ...]

ReAct 第 2 轮：
  LLM 看到 Observation 后明白了，改用 prompt 里教的工具:
    ```py
    weather = get_weather("Beijing")
    ```<end_code>
    
  沙箱通过 → Observation: 北京 22°C 晴
```

**LLM 通过错误反馈"现学现卖"** —— ReAct 循环的自我修正能力。

---

## 6. ⭐⭐ 4 问题串成的完整闭环

```
              ┌─────────────────────────────────────────────────┐
              │   agent 框架（smolagents）                       │
              │                                                 │
              │   Q1 + Q4 Layer 1（主动）：拼 system prompt     │
              │     ├─ 工具列表 (Tool.to_code_prompt) ← Q1      │
              │     ├─ authorized_imports 白名单 ← Q4           │
              │     └─ 协议规则 + few-shot 示例                  │
              └────────────────────┬────────────────────────────┘
                                   ↓ HTTP body
              ┌─────────────────────────────────────────────────┐
              │   LLM API 服务器 → LLM 模型                       │
              │     模型读 prompt → 写 Python 代码 ← Q2 (编排)    │
              │     代码分 3 Layer ← Q3                          │
              └────────────────────┬────────────────────────────┘
                                   ↓ 返回代码
              ┌─────────────────────────────────────────────────┐
              │   agent 框架沙箱（local_python_executor）         │
              │                                                 │
              │   Q4 Layer 2（被动）：AST 检查 + 白名单           │
              │     ├─ 合规 → 执行返回结果                        │
              │     └─ 不合规 → 拒 + 错误信息                     │
              └────────────────────┬────────────────────────────┘
                                   ↓
              ┌─────────────────────────────────────────────────┐
              │   Q4 Layer 3（反馈）：错误进 memory               │
              │     ↓                                            │
              │     LLM 修正后再写 → 回 prompt 阶段（下一轮）       │
              └─────────────────────────────────────────────────┘
```

**4 个问题对应 4 个组件**，缺一不可：
- 缺 Q1（不告诉工具）→ LLM 瞎猜 / 失败率极高
- 缺 Q2（直接执行 tool 不让 LLM 写）→ 复合任务无法解决
- 缺 Q3（任意 Python）→ 安全隐患 + 失控
- 缺 Q4（不教 + 不拒 + 不反馈）→ LLM 学不会怎么写合规代码

---

## 7. ⭐ 跟其他笔记的同构模式

CodeAgent 的"prompt + 沙箱 + 反馈"= smolagents 反复出现的设计哲学：

| 主题 | 主动机制（教 LLM）| 被动机制（兜底）| 反馈机制 |
|---|---|---|---|
| **stop_sequences** | prompt 里教 "End with `<end_code>`" | LLM API 服务器检测字符串截断 | （响应直接停）|
| **CodeAgent 工具/沙箱** | system prompt 列 tools + imports | 沙箱 AST 检查拒绝 | 错误进 observation → 下一轮 LLM 看到 |
| **PlanningStep 重规划** | YAML 模板规定 4 段结构 | `<end_plan>` stop_sequence 截断 | （prompt 工程内）|
| **Tool 实例化** | 用户文档教 4 类属性怎么写 | `__init_subclass__` wrap `__init__` 校验 | 校验失败 raise → 用户改 |

**同一原则反复**：
> **永远不要单独信任 LLM 的"意愿"。给它提示 + 给它硬约束 + 给它错误反馈**。

📚 [model-stop-sequences.md §7](../03-source/day3-models/model-stop-sequences.md)（被动检测 vs 主动控制 —— 同一心智模型）

---

## 8. Day 4-6 阅读指南

带着这 4 个问题去读源码，每个问题在哪个文件落地：

| 问题 | 哪一天 / 哪个文件 | 看什么 |
|---|---|---|
| **Q1** 工具传递机制 | **Day 4** [agents.py](../../../src/smolagents/agents.py) 上半 | system prompt 拼装代码 + [code_agent.yaml](../../../src/smolagents/prompts/code_agent.yaml) 模板 |
| **Q2** LLM 编排逻辑 | **Day 5** [agents.py](../../../src/smolagents/agents.py) 下半 | `_step_stream` 每轮 ReAct 怎么用 LLM 决策 |
| **Q3** 沙箱限制 | **Day 6** [local_python_executor.py](../../../src/smolagents/local_python_executor.py) | AST 解析 + 白名单 + 受控执行 |
| **Q4** 教 + 拒 + 反馈 | **Day 4 + Day 6 拼起来** | code_agent.yaml + agents.py 错误反馈 + local_python_executor.py 拒绝逻辑 |

⚠️ **Q2 / Q4 不会在源码中"自动豁然开朗"** —— 它们是跨层心智模型，源码只展示机制不主动总结。**带着本笔记的心智框架读源码** = 真正消化。

---

## 9. 总结表

| 问题 | 核心答案 |
|---|---|
| CodeAgent 要告诉 LLM 工具吗？ | ✅ 必须，通过 system prompt 文本（不是 OpenAI tools 字段）|
| 既然有 tool 为啥还要 LLM 写代码？ | tool 是原子操作，LLM 写编排逻辑（决策 / 顺序 / 数据处理 / 控制流）|
| LLM 能写任意代码吗？ | ❌ 沙箱限制：能写 Layer 2-3（白名单 Python + tool 调用），不能写 Layer 1（任意 import / 文件 / 网络）|
| 谁告诉 LLM 限制？ | 3 层：prompt 教（主动）+ 沙箱拒（被动）+ 错误反馈（闭环自修正）|
| 同一设计哲学其他例子？ | stop_sequences / PlanningStep / Tool 校验都是同构模式 |
| Day 4-6 会自动豁然开朗吗？ | Q1/Q3 ✅，Q2/Q4 需带着本笔记心智框架读源码才能消化 |

---

## 相关链接

- 必读前置：
  - [codeagent-vs-toolcallingagent.md](codeagent-vs-toolcallingagent.md) — Week 1 概念
  - [llm-vs-api-server-architecture.md](llm-vs-api-server-architecture.md) — 4 角色术语
  - [chat-template-explained.md](chat-template-explained.md) — messages → token
- 同构模式参照：
  - [model-stop-sequences.md §7](../03-source/day3-models/model-stop-sequences.md) — 被动检测 vs 主动控制（最核心同构）
  - [planning-mechanics.md](../03-source/day1-memory/planning-mechanics.md) — PlanningStep 也是 prompt 教 + stop 截断
- Day 4-6 准备读：
  - [code_agent.yaml](../../../src/smolagents/prompts/code_agent.yaml) — system prompt 模板
  - [agents.py](../../../src/smolagents/agents.py) — Day 4-5 主菜
  - [local_python_executor.py](../../../src/smolagents/local_python_executor.py) — Day 6 沙箱

## 遗留问题

- [ ] CodeAgent system prompt 里 few-shot 示例的具体设计（待 Day 4 读 yaml 看）
- [ ] 沙箱白名单的具体清单（authorized_imports 默认值 + 可扩展性）
- [ ] LLM 写代码失败几次后框架会放弃吗？（max_steps 退出条件）—— 待 Day 4 看
- [ ] CodeAgent 的 stop_sequences 在哪定义（应该是 ["<end_code>"]，待 Day 4 验证）

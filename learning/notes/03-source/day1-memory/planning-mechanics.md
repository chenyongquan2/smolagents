---
created: 2026-05-02
status: active
tags: [planning, react, prompt-engineering, summary-mode, source-reading, week2-day1]
---

# PlanningStep 机制深入：role 切换技、planning_interval、重 plan 的 summary_mode

## 背景 / 动机

Day 1 读 [memory.py:153-183](../../../../src/smolagents/memory.py:153) 的 PlanningStep 时，引出了一连串"不读源码就想不到"的 agent 工程精髓。这些机制涉及：

- 它代码上为什么**重写 `dict()`**？
- `to_messages()` 为什么返回 **2 条** messages（包括一条**伪造的 user 消息**）？
- `planning_interval` 怎么控制周期性触发？为什么这样设计？
- 重 plan 时 LLM 看得到旧 plan 吗？（剧透：看不到）
- 上面说的全部用 [planning_demo.py](../../../scripts/planning_demo.py) 实证了

由于内容多，单独成文。

---

## 一、PlanningStep 类结构（[memory.py:153-183](../../../../src/smolagents/memory.py:153)）

```python
@dataclass
class PlanningStep(MemoryStep):
    model_input_messages: list[ChatMessage]    # 这次规划喂给 LLM 的输入
    model_output_message: ChatMessage          # LLM 的原始输出对象
    plan: str                                  # 提取出来的纯文本计划
    timing: Timing                             # 耗时信息
    token_usage: TokenUsage | None = None      # token 用量

    def dict(self): ...        # ⭐ 重写了！
    def to_messages(self, summary_mode=False): ...
```

### 比前面 3 个简单 Step 多出 4 个新点

#### ① 字段从 1-2 个变成 5 个

PlanningStep **把整次规划的请求-响应都留档**：input_messages、output_message、plan 文本、耗时、token 用量。

> 💡 **设计思想**：planning 是 agent 的"重要决策时刻"，全档留下方便事后 replay / 调试 / 计费。

#### ② ⭐ 第一次见到子类**重写 `dict()`**

为什么基类的 `asdict(self)` 不够？因为 `model_input_messages` 是 `list[ChatMessage]`，内部嵌套 dataclass，`asdict()` 直接调会出错或丢信息。所以这里需要：

```python
make_json_serializable(get_dict_from_nested_dataclasses(msg))
```

把嵌套结构拍平 + 处理无法 JSON 化的对象（图片、bytes 等）。

> 💡 **教训**：基类提供 80% 通用情况的实现，**特殊情况子类重写**。这是面向对象多态最朴素的用法。

#### ③ `Timing` / `TokenUsage` 是其他 dataclass

dataclass **可以嵌套 dataclass**，是常用模式。注意 `TokenUsage | None = None` 是 Python 3.10+ 的联合类型（等价于老写法 `Optional[TokenUsage]`）。

#### ④ ⭐⭐ `to_messages()` 返回 **2 条**

这是本笔记最重要的内容，单独开一节讲（下一节）。

---

## 二、为什么 `to_messages()` 要包含一条"伪造的 user 消息"？

```python
def to_messages(self, summary_mode: bool = False) -> list[ChatMessage]:
    if summary_mode:
        return []
    return [
        ChatMessage(role=MessageRole.ASSISTANT,
                    content=[{"type": "text", "text": self.plan.strip()}]),
        ChatMessage(role=MessageRole.USER,
                    content=[{"type": "text", "text": "Now proceed and carry out this plan."}]),
        # 这第二条消息制造了一次 role 切换，防止模型继续写 plan
    ]
```

### 关键背景：LLM 训练时只见过 user-assistant 严格交替

现代 LLM 用 **chat template**，训练数据都是：

```
<|user|>...<|end|><|assistant|>...<|end|><|user|>...<|end|>...
```

LLM 学到的"自然反应"：**user 刚说完，自己作为 assistant 接茬**。

### 没有伪造消息会怎样？

如果 PlanningStep 只产出 1 条 assistant 消息，下一次 LLM 调用看到：

```
<|user|>查巴黎温度<|end|>
<|assistant|>我的计划：1. 调天气工具...<|end|>
<|assistant|>{LLM 现在被强行要求继续}    ← ⚠️ 训练数据里几乎不存在的异常
```

实测翻车行为：
1. **继续完善 / 复述计划**："...更具体地说，我会先 import requests，然后..."
2. **重写一遍计划**（甚至和上一条几乎一样）
3. **加冗余解释**

→ agent **陷在 planning 模式出不来**，永远不开始执行。

### 加了伪造消息后

```
<|user|>查巴黎温度<|end|>
<|assistant|>我的计划：1. 调天气工具...<|end|>
<|user|>Now proceed and carry out this plan.<|end|>      ← 伪造的
<|assistant|>{LLM 在这里生成} ← 看到 user 在催，自然输出动作
```

LLM 看到**正常的交替**，且最近 user 在催执行，**自然切换到执行模式**：输出 tool_call 或 Python 代码。

### 类比：演员接戏

```
🎭 LLM = 演员
🎬 agent 框架 = 编剧
📜 messages = 剧本

编剧给演员塞一句"对手的台词"（伪造 user 消息），
让演员从独白模式（写计划）切换到对话模式（执行）。
```

> 💡 这是 **agent 工程的核心技法**：通过精心剪辑 messages 历史，引导 LLM 在每个时刻收到"最该收到的剧本"。
> 类似的还有 [memory.py:142](../../../../src/smolagents/memory.py:142) 的错误重试提示、[TaskStep](../../../../src/smolagents/memory.py:191) 的 `"New task:\n"` 前缀。

---

## 三、`planning_interval` 周期性重规划设计

### 触发公式（[agents.py:550-552](../../../../src/smolagents/agents.py:550)）

```python
if self.planning_interval is not None and (
    self.step_number == 1 or (self.step_number - 1) % self.planning_interval == 0
):
```

`planning_interval=2` 的触发位置（手算）：

| step_number | 计算 | 触发？ |
|---|---|---|
| 1 | `step_number == 1` ✓ | ✅ |
| 2 | `(2-1) % 2 = 1` | ❌ |
| 3 | `(3-1) % 2 = 0` ✓ | ✅ |
| 4 | `(4-1) % 2 = 1` | ❌ |
| 5 | `(5-1) % 2 = 0` ✓ | ✅ |

→ 第 1, 3, 5, 7, ... 步前重 plan。

### 为什么需要"周期性重规划"？

| 反例 | 缺陷 |
|---|---|
| ❌ 只在开头 plan 一次 | 旧计划基于不完整信息，新观察来了调不动方向（被旧计划绑架） |
| ❌ 每步都 plan | 成本翻倍（2x LLM 调用），大部分步骤其实不需要重新思考 |
| ❌ "卡住"才 plan | "卡住"难自动检测 |
| ✅ **每 N 步固定 plan** | 简单、可预测、用户可调 |

> 💡 **核心价值**：让 agent 大部分时间机械执行（便宜快），**每隔 N 步停下来根据 observation 重新校准方向**（昂贵但必要）。

### 经验法则（不是硬规则）

| 任务类型 | 推荐 `planning_interval` |
|---|---|
| 简单查询、单步骤 | `None`（不开 planning）|
| 中等复杂（3-5 步） | `None` 或 `5` |
| 复杂多阶段（10+ 步） | `3-5` |
| 探索性、路径不确定 | `2-3` |
| 极长任务（搜索 + 综合） | `5-10` |

---

## 四、⭐ 重 plan 时旧 plan 被故意隐藏（summary_mode 机制）

### 看源码（[agents.py:680-713](../../../../src/smolagents/agents.py:680)）

```python
# Summary mode removes the system prompt and previous planning messages output by the model.
# Removing previous planning messages avoids influencing too much the new plan.
memory_messages = self.write_memory_to_messages(summary_mode=True)
```

注释明说：**移除上一份计划，避免它过度影响新计划**。

### 机制连接

`summary_mode=True` 传入后，每个 step 自己决定该不该出场：

| Step 类型 | summary_mode=True 时 |
|---|---|
| `SystemPromptStep` | 返回 `[]` 隐身 |
| `TaskStep` | **不响应**，永远输出（任务必要上下文）|
| `PlanningStep` | 返回 `[]` ⭐ **隐身，关键** |
| `ActionStep` | 不输出 `model_output`，但仍输出 tool_calls 和 observations |

→ **重 plan 时 LLM 看到的是**：
- ✅ 原始 task
- ✅ 所有已执行 action 的 tool_call + observation
- 🚫 旧 plan 文本（被隐藏）

→ LLM **被迫基于事实（observation）重新规划**，避免被自己之前的旧想法绑架。

### 设计哲学：plan 是 hint，不是 state

| 选项 | 把 plan 当 | 缺陷 |
|---|---|---|
| ❌ A | **state**（程序状态，正式追踪 plan 项进度） | 计划僵化，新观察来了调不动 |
| ✅ B | **hint**（LLM 写给自己看的临时备忘）| 不严格，但灵活适应现实 |

> 💡 **核心思想**：LLM 不擅长严格遵循长程计划，但擅长根据当下情境合理推理。
> 所以 smolagents 把"长期记忆"放在 **observation** 上，**"长期计划"反而每次重写**。
> 未执行的 plan 项**不是被框架追踪的 todo list**，而是 **LLM 从 observation 自行推理出来的、随时可能改写**。

---

## 五、亲手验证：[planning_demo.py](../../../scripts/planning_demo.py) 实验

### 实验设置

- 任务："查 Beijing/Tokyo/Singapore 温度，取最大转华氏"（多步任务）
- ToolCallingAgent + `planning_interval=2`
- 假天气工具（不联网）

### 跑出来的 memory.steps

```
idx  类型              step_number  内容                              触发原因
─────────────────────────────────────────────────────────────────────
[0]  TaskStep          —            原始任务                          agent.run() 创建
[1]  PlanningStep      —            Initial Plan（6 步）              step_number=1 触发 plan
[2]  ActionStep        1            get_temperature(Beijing) → 25.0
[3]  ActionStep        2            get_temperature(Tokyo)   → 30.0
[4]  PlanningStep      —            Updated Plan（4 步，含已知 facts）⭐ step_number=3 触发 plan
[5]  ActionStep        3            get_temperature(Singapore)→28.0
[6]  ActionStep        4            final_answer(86.0) ⭐
```

### 三个核心预测全验证

| 预测 | 实际观察 |
|---|---|
| memory.steps 里出现 PlanningStep | ✅ 索引 [1] 和 [4] |
| 触发位置符合公式 step_number=1, 3, 5 | ✅ 触发 step_number = `[1, 3]` |
| PlanningStep.to_messages(summary_mode=True) 返回空 | ✅ 0 条消息 |

### 4 个高价值彩蛋

#### 彩蛋 1 ⭐⭐⭐：Updated Plan 里的 "Facts that we have learned"

实际 Updated Plan 文本：

```markdown
### 1.2. Facts that we have learned
- The current temperature in Beijing is 25.0°C.
- The current temperature in Tokyo is 30.0°C.

### 1.3. Facts still to look up
- The current temperature in Singapore.
```

**这是整个实验最重要的发现**。亲眼证明：

- 🚫 旧 plan 文本被隐藏（LLM 看不到原始 6 步计划）
- ✅ observations 全部保留（25.0, 30.0 这些事实 LLM 看得清清楚楚）
- 🧠 LLM **从 observations 自行推断**："已经知道两个，还差一个"
- 📝 写出**截短的新计划**（4 步，不是原本的 6 步）

→ **"plan 是 hint 不是 state"得到直接实证**。

#### 彩蛋 2：新计划主动**砍掉了已完成的部分**

| | 步骤数 |
|---|---|
| Initial Plan | 6 步 |
| Updated Plan | **4 步**（剔除已完成的"搜 Beijing"、"搜 Tokyo"）|

#### 彩蛋 3：Step 4 直接跳 final_answer，**省略了"算 max + 换算"独立步骤**

```
step 1: get_temperature(Beijing)   → 25.0
step 2: get_temperature(Tokyo)     → 30.0
step 3: get_temperature(Singapore) → 28.0
step 4: final_answer(86.0)         ← 直接给答案，没有先算 max 再换算
```

**LLM 在 generate `final_answer` 调用时把 `max(25, 30, 28)*1.8+32 = 86` 算好了**，直接填进参数。

> 💡 ToolCallingAgent 的"暗能力"：LLM 在 tool_call 的 arguments 里**已经能做简单数学**。
> 复杂计算才需要专门的 calculator tool 或 CodeAgent。

#### 彩蛋 4：plan 头部前缀**真的来自源码**

实测 Updated Plan 开头：

```
I still need to solve the task I was given:
```

和 [agents.py:737](../../../../src/smolagents/agents.py:737) 写死的字符串一字不差。
→ 这是 Day 3 读 [models.py](../../../../src/smolagents/models.py) 时会大量见到的 **prompt template 拼接** 模式的真实例子。

---

## 六、3 个稳定认知（Day 1 主要收获）

1. **`memory.steps` 是 agent 的"运行日志"**：交替出现 TaskStep / PlanningStep / ActionStep，**`step_number` 只增量于 ActionStep**
2. **重 plan 时 LLM 看不到旧 plan，但看得到所有 observation**（summary_mode 机制）：让 plan 永远基于"事实"而非"自己之前的想法"
3. **plan 文本里的步数 ≠ ReAct 步数**：本次实验 Updated Plan 写 4 步，但实际只产生 2 个 ActionStep（step 4 就 final_answer 了）

---

## 相关链接

- 源码：
  - [memory.py:153-183](../../../../src/smolagents/memory.py:153) PlanningStep 类
  - [agents.py:540-748](../../../../src/smolagents/agents.py:540) `_run_stream` + `_generate_planning_step`
- 实验脚本：[../../scripts/planning_demo.py](../../../scripts/planning_demo.py)
- 关联笔记：
  - [memory-data-structures.md](memory-data-structures.md) Step 家族整体
  - [../02-concepts/chat-message-roles.md](../../02-concepts/chat-message-roles.md) 为什么伪造 user 消息能起作用

## 遗留问题（已解答）

### ✅ Q1：`<end_plan>` 这个 stop_sequence 是干嘛的？

**双向约定**：prompt 端要求 LLM 写完 plan 末尾输出 `<end_plan>`（[toolcalling_agent.yaml:144, 197](../../../../src/smolagents/prompts/toolcalling_agent.yaml:144)），生成端用 `stop_sequences=["<end_plan>"]`（[agents.py:660,672,720,730](../../../../src/smolagents/agents.py:660)）强制截断。**目的**：防止 LLM 写完 plan 后接着开始执行（"现在我调用..."），保证 PlanningStep.plan 是**纯计划文本**。

### ✅ Q2：浪费的 4 步思考反映在 token_usage 哪？

**全部计入 `PlanningStep.token_usage.output_tokens`，且不会退还**。即使后续只执行了 1 步，5 步 plan 的 token 已经真金白银花掉。可以从 [planning_demo.py](../../../scripts/planning_demo.py) 输出看到 `input_tokens` 每轮累积上涨（因为 messages 历史塞了 plan 文本）。**工程含义**：`planning_interval=1`（每步都 plan）通常成本不划算。

### ✅ Q3：`update_plan_pre/post_messages` 默认值在哪？

在 [src/smolagents/prompts/](../../../../src/smolagents/prompts/) 下三个 YAML 文件（`toolcalling_agent.yaml` / `code_agent.yaml` / `structured_code_agent.yaml`）的 `planning` 段。

**关键发现**：实验里 Updated Plan 看到的 4 段结构（"Facts given / learned / still to look up / still to derive"）**严格来自 [toolcalling_agent.yaml:184-188](../../../../src/smolagents/prompts/toolcalling_agent.yaml:184) 的 `update_plan_post_messages` 模板硬规定**，不是 LLM 自由发挥。LLM 只是按模板填空。

→ **认知升级**：LLM 在 prompt 工程里其实是"填空机"，框架/模板规定大格式，LLM 只填具体内容。Day 3 读 [models.py](../../../../src/smolagents/models.py) 会更深入看到这种"prompt template 拼接"模式。

### ✅ Q4：CodeAgent 用 `planning_interval` 节奏会不会"错位"？

**会，而且很显著**。根因：`step_number` 计的是 ReAct 迭代次数，不是逻辑进度。

| | 1 step_number 对应多少逻辑动作 |
|---|---|
| ToolCallingAgent | ≈ 1 个 tool 调用 |
| CodeAgent | 1 段代码（可含多次 tool 调用 + 计算 + 控制流），可能 5+ |

→ ToolCallingAgent + `planning_interval=2` 节奏均匀；CodeAgent + `planning_interval=2` 可能任务都做完了还没触发第二次 plan。

**实用建议**：
- CodeAgent + 短任务 → 不开 planning
- CodeAgent + 长任务 → `planning_interval=1` 或 `2`（让 plan 更密集）
- ToolCallingAgent + 长任务 → `planning_interval=3-5`

> 💡 这是 smolagents 已知设计取舍：选**简单实现 + 用户自调** 而非**复杂的自动智能调度**。

---

## 十、⭐ 实战选型详解：什么时候开规划？开多频繁？

> 💡 §Q4 给了 3 条简短建议，本节深入回答"为什么"+"频率影响"+"验证方法"。

### 10.1 一句话本质

> **`planning_interval=None`（默认）= 不规划，因为 80% 任务不需要"显式规划"—— LLM 在每次 ReAct 循环里已经"隐式规划"了。规划是**贵**的（一次额外 LLM 调用），值不值看任务复杂度。**

### 10.2 两种工作姿势对比

```
没规划（默认）：              有规划（planning_interval=3）：
张三接到任务                  张三接到任务
  ↓                            ↓
直接干（边干边想）            先开 5 分钟规划会议（显式写 facts + plan）
Step 1: 想 + 干 + 看           ↓
Step 2: 想 + 干 + 看           Step 1: 干
Step 3: 想 + 干 + 看           Step 2: 干
...                            Step 3: 干
                                ↓
                              再开 5 分钟规划会议（review + 更新 plan）
                              Step 4: 干
                              ...
```

### 10.3 默认 `None` 的 4 个理由

| 理由 | 说明 |
|---|---|
| **大部分任务简单** | 单步计算 / 单步查询根本不需要规划 |
| **规划要钱** | 每个 PlanningStep 是一次额外的 LLM 调用 |
| **规划要时间** | 让用户多等几秒 |
| **可能噪音大** | 简单任务里强行规划反而打断 LLM 的"步步深入"思路 |

### 10.4 不开规划时 agent 怎么工作？

每次 ReAct 循环里，LLM 看到完整 memory（包含全部历史 observation），它的"想法"（`model_output` 字段）天然就包含：
- "我已经知道了什么"
- "下一步要干什么"

**规划逻辑被"吸收进每步思考"** —— 不需要单独的 PlanningStep 来表达。

### 10.5 ⭐ 不同 `planning_interval` 值的影响对比表

| `planning_interval` 值 | 行为 | 优点 | 缺点 |
|---|---|---|---|
| **`None`**（默认）| 不规划 | token 省、简单任务效率高 | 复杂任务可能"走偏" |
| **`1`**（每步都规划）| 每步规划一次 | 强力纠偏 | ❌ **token 爆炸**、噪音大、反而打断"深入"思路 |
| **`3`**（每 3 步规划一次）| step 1, 4, 7, 10 ... 规划 | 中等任务最佳平衡 | 中度 token 增加 |
| **`5-10`**（很少规划）| 仅长任务才触发 | 长任务防偏 | 短任务等于 None |

> ⚠️ 注意 §Q4 提过：CodeAgent 的 `planning_interval` 含义和 ToolCallingAgent 不同（CodeAgent 一步等于多个逻辑动作）—— 表里数值偏向 ToolCallingAgent 视角。CodeAgent 想要密集规划要用 `1` 或 `2`。

### 10.6 ⭐ 加规划带来的 3 个具体价值

#### 影响 ① · 防止"路径依赖"（最大价值）

不规划时 agent 容易**陷入局部最优**：
- Step 1 选错方向 → Step 2 在错方向上继续 → Step 3 越走越偏 → 最后撞 max_steps

**规划是定期"抬头看路"**，让 LLM 重新审视："现在已知什么 / 该不该改方向 / 接下来真正该干啥"。

#### 影响 ② · 让 LLM 显式写下 "Facts learned"

规划阶段强制 LLM 总结 observation —— 相当于**让 LLM 自己做了一次"信息整理"**，下面几步思考会更清晰。

#### 影响 ③ · `summary_mode` 隐藏旧"想法"

重规划时调 `write_memory_to_messages(summary_mode=True)` —— **隐藏所有旧 model_output（"想法"），保留 observations（"事实"）** —— 这样 LLM 重新规划时**只基于事实**，不被旧错误思路带偏。

> 💡 **这就是规划的真正价值**：纠偏机制。但前提是**任务真的会走偏**。

### 10.7 实战决策表

| 任务类型 | 例子 | 推荐值 |
|---|---|---|
| **单步计算 / 单步查询** | "2 ** 3.7384 = ?" | `None` |
| **简单问答（2-3 步）** | "查北京天气" | `None` |
| **中等复杂度（3-10 步）** | "查 3 个景点对比" | `None` 或 `5` |
| **复杂研究（10+ 步）** | "整理一份调研报告" | `3-5` |
| **多分支决策** | "根据用户偏好做推荐" | `3` |
| **极度复杂（20+ 步）** | "完成多步骤工作流" | `3` |

### 10.8 验证方法

跑同一个任务两次（一次 `None`，一次 `3`），看：

1. **token 消耗差异** —— 开规划会贵 30-50%
2. **步数差异** —— 规划可能让 step 数减少（不走弯路）也可能没变化
3. **答案质量** —— 复杂任务规划版可能更靠谱
4. **是否撞 max_steps** —— 不规划版更容易撞

> 💡 实验脚本：[planning_compare_demo.py](../../../scripts/planning_compare_demo.py)（同任务跑两次对比）。

### 10.9 关键启示

| 启示 | 含义 |
|---|---|
| **规划不是必需的** | LLM 在每步思考里已经隐式规划 |
| **规划是"显式纠偏机制"** | 防止路径依赖、走偏 |
| **太频繁规划反而有害** | `planning_interval=1` 让 token 爆炸且打断思考 |
| **`summary_mode` 是规划的"清思路"机制** | 重规划时隐藏旧想法只看事实 |
| **典型推荐值 = 3-5** | 中长任务里最佳平衡（CodeAgent 用 1-2）|
| **CodeAgent vs ToolCallingAgent 节奏不同** | 同样的 `planning_interval=3` 在两类 agent 里效果差很多（§Q4）|

---

## 十一、⭐⭐ 深入：规划是怎么影响后续 ActionStep 的？

> 💡 §10 讲了"什么时候开规划"（决策层），本节讲"开了之后机制怎么工作"（实现层）。

### 11.1 4 个核心问题

新手疑问：

1. 不开规划，每一步 ActionStep 内部 LLM 也会"隐式规划"吗？
2. 开规划，是相当于每隔 n 步多一次 LLM 调用吗？
3. 规划的产出是什么？
4. 规划如何传递影响后续 ActionStep？

下面 4 节逐一回答。

### 11.2 ✅ Q1：不开规划时，每步 ActionStep 也"隐式规划"

**是的**。每个 ActionStep 内 `_step_stream` 调一次 `Model.generate`，LLM 输出的 `model_output` 字段**同时包含**：

| 部分 | 内容 | 类比 |
|---|---|---|
| **Thought（思考）** | "我已知 X，下一步应该 Y" | 隐式规划 |
| **Action（行动）** | 代码块（CodeAgent）/ tool_call（ToolCallingAgent）| 实际动作 |

这是 ReAct 论文核心 —— **"思考 + 行动"二合一**，一次 LLM 调用搞定。

> 💡 **不规划 ≠ 不思考**，只是**不显式分离规划阶段**。规划逻辑被"吸收进每步思考"。

### 11.3 ✅ Q2：开规划 = 多 N/interval 次额外 LLM 调用

`planning_interval=3` = 每 3 步**额外**插一个 PlanningStep = **1 次额外 LLM 调用**。

#### 调用次数公式

| 模式 | N 步任务总 LLM 调用次数 |
|---|---|
| 不规划 | **N 次**（每步 1 次）|
| `planning_interval=3` | **N + ⌈N/3⌉ 次** |

**实例（6 步任务）**：

| 模式 | 规划调用 | 动作调用 | 总计 |
|---|---|---|---|
| 不规划 | 0 | 6 | **6 次** |
| `interval=3` | 2（step 1 前 + step 4 前）| 6 | **8 次** |

> ⚠️ **Token 消耗增加比次数还猛** —— 规划 input 通常包含**整个 memory**（比单步动作的 input 长得多）。**6 步任务规划版总 token 可能比不规划版高 50-80%**。

### 11.4 ✅ Q3：规划的产出是什么？

`PlanningStep` 的字段（[memory.py:153](../../../../src/smolagents/memory.py#L153)）：

```python
@dataclass
class PlanningStep(MemoryStep):
    model_input_messages: list[ChatMessage]    # 喂给 LLM 的输入
    model_output_message: ChatMessage          # LLM 原始输出
    plan: str                                  # ⭐ 文本规划（最重要）
    timing: Timing
    token_usage: TokenUsage | None
```

#### `plan` 字段的实际内容

LLM 输出由 [toolcalling_agent.yaml:184-188](../../../../src/smolagents/prompts/toolcalling_agent.yaml#L184) 模板严格规定，是**结构化文档**：

```
## 1. Facts survey
### 1.1 Facts given in the task
### 1.2 Facts that we have learned
### 1.3 Facts still to look up
### 1.4 Facts still to derive

## 2. Plan
1. Step A
2. Step B
...
```

#### 首次 vs 后续规划的 `plan` 文本前缀不同

[agents.py:678](../../../../src/smolagents/agents.py#L678) / [agents.py:736](../../../../src/smolagents/agents.py#L736)：

| 场景 | `plan` 文本前缀 |
|---|---|
| **首次**（initial）| "Here are the facts I know and the plan of action that I will follow to solve the task..." |
| **后续**（update）| "I still need to solve the task I was given... Here are the facts I know and my new/updated plan..." |

### 11.5 ⭐⭐ Q4：规划如何传递影响后续 ActionStep？

**关键机制 = `PlanningStep.to_messages()` 的"伪造 user 消息" trick**。

#### 传递流程

```
┌─ Step 1 之前规划 ─────────────────┐
│ _generate_planning_step()         │
│   ├─ 调 LLM 拿到 plan 文本         │
│   └─ yield PlanningStep(plan=...)  │
│                                    │
│ memory.steps.append(PlanningStep)  │ ← 进笔记本
└────────────────────────────────────┘
              │
              ▼
┌─ Step 1 内部 _step_stream ────────┐
│ messages = write_memory_to_messages│ ← 翻译笔记本
│   遍历 memory.steps:               │
│     PlanningStep.to_messages()     │ ← ⭐ 在这里翻译
│   返回完整 messages                 │
│                                    │
│ self.model.generate(messages)      │ ← LLM 看到 plan
└────────────────────────────────────┘
```

#### `PlanningStep.to_messages()` 实际产出（[memory.py:174](../../../../src/smolagents/memory.py#L174)）

```python
def to_messages(self, summary_mode: bool = False) -> list[ChatMessage]:
    if summary_mode:
        return []                                            # 重规划时隐藏旧 plan
    return [
        ChatMessage(ASSISTANT, plan),                        # ① 装作 LLM 之前说过 plan
        ChatMessage(USER, "Now proceed and carry out this plan."),  # ② ⭐ 伪造 user 催办
    ]
```

#### 两条消息的设计精妙

##### 第 ① 条 · `ASSISTANT` 角色（装作 LLM 自己说过的）

把 plan 包装成 ASSISTANT 消息 —— LLM 看到"**这是我自己刚才承诺的 plan**"，**会有"接着推进"的倾向**（人和 LLM 都不喜欢自相矛盾）。

##### 第 ② 条 · `USER` 角色（伪造一条催办）⭐

**这条是真正的 trick**。源码注释明确说：

```python
# This second message creates a role change to prevent models
# from simply continuing the plan message
```

如果只有第 ① 条（plan 是 ASSISTANT 角色），下一次 LLM 调用时 messages 末尾是 ASSISTANT —— LLM 会**继续写 plan**（因为它"以为"自己还没说完）。

伪造一条 USER 消息插在末尾 —— **强制 role 切换**，让 LLM 切换到"执行"模式。

> 💡 这就是 [chat-message-roles.md](../../02-concepts/chat-message-roles.md) 说的"**role 是 LLM 行为的方向盘**"的实际应用。

#### 完整 messages 剧本

假设 step 1 之前规划了，step 1 内部 LLM 看到的 messages 大概长这样：

```
[SYSTEM]    你是 CodeAgent，能干 X/Y/Z 工具...

[USER]      找出 50-100 之间所有素数...（task）

[ASSISTANT] Here are the facts I know and my plan:
            ## 1. Facts survey
            ### 1.1 Facts given: range 50-100
            ### 1.2 Facts learned: (空，第 1 步前没 observation)
            ### 1.3 Facts to look up: (无)
            ### 1.4 Facts to derive: 哪些数是素数
            ## 2. Plan
            1. 写 is_prime 函数
            2. 用列表推导式列出 50-100 的素数
            3. 计算总和、平均值
            4. 调 final_answer

[USER]      Now proceed and carry out this plan.   ← ⭐ 伪造

[?]         （等 LLM 这一步的输出 = ActionStep 的 model_output）
```

LLM 接到这套消息后，会自然地"按计划执行 step 1"，**不会再继续写规划**。

### 11.6 重规划场景的特殊处理（呼应 §10.6 影响 ③）

[agents.py:684](../../../../src/smolagents/agents.py#L684) update plan 时调 `write_memory_to_messages(summary_mode=True)`：

| 处理 | 效果 |
|---|---|
| `PlanningStep.to_messages` 返回 `[]` | **隐藏旧 plan**（避免新 plan 被旧的影响）|
| `ActionStep.to_messages` 隐藏 `model_output` | **隐藏旧"想法"**，只保留 observations（"事实"）|

→ **重规划时 LLM 看到的是"原始事实"，不会被旧错误想法带偏**。

### 11.7 关键启示

| 启示 | 含义 |
|---|---|
| **隐式规划 = ReAct 论文的"Thought"** | 每步 LLM 输出本身就含规划 |
| **显式规划 = 额外 LLM 调用** | N/interval 次额外调用，token 增加更多 |
| **plan 不是直接喂 LLM，是包装成 2 条 ChatMessage** | ASSISTANT plan + USER 催办 |
| **⭐ 伪造 USER 消息是 role 切换技** | 防止 LLM 以为还在写 plan，强制切换到"执行"模式 |
| **重规划时 `summary_mode` 隐藏旧 plan + 旧想法** | 只基于"事实"重新规划 |
| **role 是 LLM 行为的方向盘** | 通过 role 切换控制行为模式（见 [chat-message-roles.md](../../02-concepts/chat-message-roles.md)）|

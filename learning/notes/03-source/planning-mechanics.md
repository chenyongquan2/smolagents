---
created: 2026-05-02
status: active
tags: [planning, react, prompt-engineering, summary-mode, source-reading, week2-day1]
---

# PlanningStep 机制深入：role 切换技、planning_interval、重 plan 的 summary_mode

## 背景 / 动机

Day 1 读 [memory.py:153-183](../../../src/smolagents/memory.py:153) 的 PlanningStep 时，引出了一连串"不读源码就想不到"的 agent 工程精髓。这些机制涉及：

- 它代码上为什么**重写 `dict()`**？
- `to_messages()` 为什么返回 **2 条** messages（包括一条**伪造的 user 消息**）？
- `planning_interval` 怎么控制周期性触发？为什么这样设计？
- 重 plan 时 LLM 看得到旧 plan 吗？（剧透：看不到）
- 上面说的全部用 [planning_demo.py](../../scripts/planning_demo.py) 实证了

由于内容多，单独成文。

---

## 一、PlanningStep 类结构（[memory.py:153-183](../../../src/smolagents/memory.py:153)）

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
> 类似的还有 [memory.py:142](../../../src/smolagents/memory.py:142) 的错误重试提示、[TaskStep](../../../src/smolagents/memory.py:191) 的 `"New task:\n"` 前缀。

---

## 三、`planning_interval` 周期性重规划设计

### 触发公式（[agents.py:550-552](../../../src/smolagents/agents.py:550)）

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

### 看源码（[agents.py:680-713](../../../src/smolagents/agents.py:680)）

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

## 五、亲手验证：[planning_demo.py](../../scripts/planning_demo.py) 实验

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

和 [agents.py:737](../../../src/smolagents/agents.py:737) 写死的字符串一字不差。
→ 这是 Day 3 读 [models.py](../../../src/smolagents/models.py) 时会大量见到的 **prompt template 拼接** 模式的真实例子。

---

## 六、3 个稳定认知（Day 1 主要收获）

1. **`memory.steps` 是 agent 的"运行日志"**：交替出现 TaskStep / PlanningStep / ActionStep，**`step_number` 只增量于 ActionStep**
2. **重 plan 时 LLM 看不到旧 plan，但看得到所有 observation**（summary_mode 机制）：让 plan 永远基于"事实"而非"自己之前的想法"
3. **plan 文本里的步数 ≠ ReAct 步数**：本次实验 Updated Plan 写 4 步，但实际只产生 2 个 ActionStep（step 4 就 final_answer 了）

---

## 相关链接

- 源码：
  - [memory.py:153-183](../../../src/smolagents/memory.py:153) PlanningStep 类
  - [agents.py:540-748](../../../src/smolagents/agents.py:540) `_run_stream` + `_generate_planning_step`
- 实验脚本：[../../scripts/planning_demo.py](../../scripts/planning_demo.py)
- 关联笔记：
  - [memory-data-structures.md](memory-data-structures.md) Step 家族整体
  - [../02-concepts/chat-message-roles.md](../02-concepts/chat-message-roles.md) 为什么伪造 user 消息能起作用

## 遗留问题（已解答）

### ✅ Q1：`<end_plan>` 这个 stop_sequence 是干嘛的？

**双向约定**：prompt 端要求 LLM 写完 plan 末尾输出 `<end_plan>`（[toolcalling_agent.yaml:144, 197](../../../src/smolagents/prompts/toolcalling_agent.yaml:144)），生成端用 `stop_sequences=["<end_plan>"]`（[agents.py:660,672,720,730](../../../src/smolagents/agents.py:660)）强制截断。**目的**：防止 LLM 写完 plan 后接着开始执行（"现在我调用..."），保证 PlanningStep.plan 是**纯计划文本**。

### ✅ Q2：浪费的 4 步思考反映在 token_usage 哪？

**全部计入 `PlanningStep.token_usage.output_tokens`，且不会退还**。即使后续只执行了 1 步，5 步 plan 的 token 已经真金白银花掉。可以从 [planning_demo.py](../../scripts/planning_demo.py) 输出看到 `input_tokens` 每轮累积上涨（因为 messages 历史塞了 plan 文本）。**工程含义**：`planning_interval=1`（每步都 plan）通常成本不划算。

### ✅ Q3：`update_plan_pre/post_messages` 默认值在哪？

在 [src/smolagents/prompts/](../../../src/smolagents/prompts/) 下三个 YAML 文件（`toolcalling_agent.yaml` / `code_agent.yaml` / `structured_code_agent.yaml`）的 `planning` 段。

**关键发现**：实验里 Updated Plan 看到的 4 段结构（"Facts given / learned / still to look up / still to derive"）**严格来自 [toolcalling_agent.yaml:184-188](../../../src/smolagents/prompts/toolcalling_agent.yaml:184) 的 `update_plan_post_messages` 模板硬规定**，不是 LLM 自由发挥。LLM 只是按模板填空。

→ **认知升级**：LLM 在 prompt 工程里其实是"填空机"，框架/模板规定大格式，LLM 只填具体内容。Day 3 读 [models.py](../../../src/smolagents/models.py) 会更深入看到这种"prompt template 拼接"模式。

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

---
created: 2026-05-09
status: active
tags: [smolagents, agents, walkthrough, codeagent, step-stream, day5, react-loop]
---

# 小组长李四的另一种活法：CodeAgent 单步完整剧本

> 💡 **本篇定位**：和 [01b 演出版](01-toolcalling-walkthrough.md) 同源 —— 同样的人物剧组、同样的小组长李四、**同一个任务**。区别只在李四这次换了套**工作方法**。
>
> **推荐对照阅读**：先打开 [01b](01-toolcalling-walkthrough.md)（ToolCallingAgent 演出版），然后看本篇。**两篇 99% 时间用同一句话开头，少数地方故意不同 —— 那些不同处就是 Day 5 ⭐ 两个分歧点的真面目**。
>
> 🔬 **实证状态（2026-05-09）**：HF 暂时访问不了，本剧本未实测。但 CodeAgent 部分跟 ToolCallingAgent 重叠少（动作 ③ ④ 完全不同），剧本风险也较小。

---

## 这场戏的人物 & 道具

延续 01b 剧组，**新增 1 个新人物 + 1 件新道具**：

| 角色 / 道具 | 对应代码 | 和 01b 比 |
|---|---|---|
| 老板 | 用户脚本 `agent.run(...)` | **不变** |
| 项目经理张三 | `CodeAgent` 实例 | **换了风格** ← 从 ToolCalling 换成 Code |
| 小组长李四 | `_step_stream(action_step)` | **不变**（同一个人，今天工作方法不同）|
| 顾问 | LLM API 服务器 + LLM 模型 | **不变** |
| 工具人小王 | `get_temperature` tool | **不变** |
| 工具人小赵 | `final_answer` tool | **不变**（但今天小赵成了 Python 函数）|
| 🆕 **代码助手老沙（新）** | `self.python_executor` (`LocalPythonExecutor`) | Day 6 才详讲，今天只看他的接口 |
| 笔记本 | `agent.memory` | **不变** |
| 一张工作记录 | `action_step` | **不变** |
| 活页夹 | `memory_step.tool_calls / observations / model_output / code_action ...` | **多了一栏 `code_action`** |
| 🆕 **沙箱小屋（新）** | `python_executor` 内部 namespace + 受限 builtins | Day 6 详讲 |
| 储物柜 | `agent.state` | **不存在！** 因为沙箱小屋自己天然能跨步骤记变量（§4 重点）|
| 老板的对讲机 | `_run_stream` yield 出去的事件流 | **不变** |

> 💡 **核心人事变动**：ToolCallingAgent 那边李四是"工具人调度员"（直接派活给小王 / 小赵），CodeAgent 这边李四是 **"代码搬运工"** —— 他把顾问写的代码原封不动地塞给老沙跑，**自己不指挥具体 tool**。**小王 / 小赵的指挥权交给了老沙**（沙箱内部）。

---

## 这场戏的设定

```python
from smolagents import CodeAgent, InferenceClientModel, tool

@tool
def get_temperature(city: str) -> float:
    """Get current temperature in Celsius for a city."""
    fake_data = {"Beijing": 25.0, "Tokyo": 30.0, "Singapore": 28.0}
    return fake_data.get(city, 20.0)

agent = CodeAgent(
    tools=[get_temperature],     # final_answer 自动加（同 ToolCallingAgent）
    model=InferenceClientModel(model_id="Qwen/Qwen2.5-72B-Instruct"),
    max_steps=3,
    planning_interval=None,
    stream_outputs=False,
)
result = agent.run(
    "Find temperature of Beijing, Tokyo, Singapore. "
    "Convert the highest to Fahrenheit and return."
)
```

**和 01b 同样的任务**：3 个城市最高温转华氏。

**和 01b 不同的步数预期**：

| | ToolCallingAgent | CodeAgent |
|---|---|---|
| Step 数 | **4 步**（3 次 get_temperature + 1 次 final_answer）| **1 步** ⭐（一段 Python 同时完成 3 次查询 + max + 换算 + final_answer）|
| 原因 | 每步只能调一个 tool（JSON 结构限制）| 一段代码能塞任意多操作（Python 表达能力）|

> 💡 **本篇 zoom 范围 = Step 1 内部一次 `_step_stream(action_step)` 调用**，**这一次就够了** —— 因为通常 1 步搞定。如果 LLM 决定分多步（比如先调 1 个城市看看），剧本就是 Step 1 + Step 2 的重复，原理不变。

---

## 第 0 幕 · 张三把工作记录递给李四

**完全同 [01b 第 0 幕](01-toolcalling-walkthrough.md#第-0-幕--张三把工作记录递给李四)** ——
action_step 只有 step_number / timing 有值，其他全 None。

**唯一差别**：李四今天兜里揣着代码助手老沙的电话。

**代码层面**：[agents.py:1639](../../../../src/smolagents/agents.py#L1639) `CodeAgent._step_stream(memory_step)`。

---

## 第 1 幕 · 动作 ① · 李四翻笔记本

**完全同 [01b 第 1 幕](01-toolcalling-walkthrough.md#第-1-幕--动作---李四翻笔记本整理给顾问看的材料)**：

```python
memory_messages = self.write_memory_to_messages()
input_messages = memory_messages.copy()
memory_step.model_input_messages = input_messages
```

唯一注意点：**笔记本里的 system_prompt 不一样了**。

### 🆕 这里要先停一下，介绍 3 个新词

否则下面的"system_prompt 注入"那句话会看得云里雾里。

**新词 1 · `code_block_tags`（代码块标签）**

= 一对"信封"`(开口标签, 收口标签)`，CodeAgent 让 LLM 把代码塞进这对信封里。

| 配置 | tuple 长这样 | LLM 输出长这样 |
|---|---|---|
| **默认** | `("<code>", "</code>")` | `<code>x = 1</code>` |
| **markdown 模式** | ` ("```python", "```") ` | ```` ```python\nx = 1\n``` ```` |

**为什么要"信封"**？因为 LLM 输出是**一段文字**，里面夹着代码：

```
我需要查 3 个城市的温度，然后取最大值换算。代码：
<code>
temps = [get_temperature("Beijing"), ...]
final_answer(max(temps) * 1.8 + 32)
</code>
```

框架要靠这对标签把代码"抠出来"才能塞给沙箱跑（第 3 幕 `parse_code_blobs` 的工作）。

**新词 2 · `code_block_opening_tag` / `code_block_closing_tag`**

把上面那个 tuple **拆成两个独立变量** —— 仅仅是 prompt 模板里方便单独引用（模板里的占位符要 `{{code_block_opening_tag}}` 和 `{{code_block_closing_tag}}`，不能直接用 tuple）。**本质就是 `code_block_tags[0]` 和 `code_block_tags[1]`**。

**新词 3 · `authorized_imports`**

= LLM 能 import 的 Python 模块**白名单**。

```python
# 默认（BASE_BUILTIN_MODULES）大致包含：
["math", "json", "re", "datetime", "itertools", "collections", ...]

# 不在白名单的：
import os         # ❌ 沙箱拒绝
import subprocess # ❌ 沙箱拒绝
```

**目的**：沙箱安全。CodeAgent 让 LLM 写代码 → 万一 LLM 写出 `os.system("rm -rf /")` 就完蛋。白名单是第一道防线（Day 6 沙箱会详讲）。

用户可以通过 `CodeAgent(additional_authorized_imports=["pandas"])` 追加白名单。

### 回到正题

CodeAgent 的 `initialize_system_prompt()`（[agents.py:1621-1637](../../../../src/smolagents/agents.py#L1621)）会把这 3 个东西**填进 prompt 模板**。LLM 看到的是 [code_agent.yaml](../../../../src/smolagents/prompts/code_agent.yaml) 模板填好后的版本，大致教它：

- "你要用 `<code>...</code>` 包裹代码" ← `code_block_opening_tag` / `code_block_closing_tag` 被填进去
- "你能 import 的模块只有：`['math', 'json', 're', ...]`" ← `authorized_imports` 被填进去

**对比 ToolCallingAgent 的 system_prompt** 教的是 "你要用 JSON 工具调用格式" —— 这是两个 agent 行为差异的**根**。同一个 LLM 看到不同的 system_prompt，输出格式就完全不同了。

---

## 第 2 幕 · 动作 ② · 李四打电话问顾问（⭐ 这里开始不一样）

**李四视角**：

把整理好的材料念给顾问听，但今天交代的事**和 01b 不同**：

| 交代项 | 01b ToolCallingAgent | 02b CodeAgent |
|---|---|---|
| stop 信号 | `["Observation:", "Calling tools:"]` | `["Observation:", "Calling tools:", "</code>"]` ← ⭐ 多了 |
| tools 名片 | `tools_to_call_from=[get_temperature, final_answer]` | **不传！** ⭐ |
| 额外要求 | — | **进阶**：可能加 `response_format=CODEAGENT_RESPONSE_FORMAT`（structured 模式，下面 ★ 讲）|

### ★ 顺便提一下 structured 模式（**进阶 / 默认不走，第一遍可跳过**）

这一行涉及 3 个新词，先简单解释，避免后面看到 §番外 1 时云里雾里。**主线学习者只需要记住"默认不走这条路"，跳过本节直接看下面"顾问思考几秒"**。

**🆕 `response_format`** = LLM API 协议字段（OpenAI 标准），告诉 LLM API 服务器 **"强制 LLM 输出符合这个 JSON Schema"**。Day 3 [model-stop-sequences §9](../day3-models/model-stop-sequences.md) 提过 —— 这是 "constrained decoding 主动约束" 的一种，比 stop 更硬核（stop 是事后停，response_format 是事前强制结构）。

**🆕 `CODEAGENT_RESPONSE_FORMAT`** = smolagents 预定义的一个 JSON Schema 常量，长这样（简化）：

```python
{
    "type": "json_schema",
    "json_schema": {
        "name": "CodeAgentOutput",
        "schema": {
            "type": "object",
            "properties": {
                "thoughts": {"type": "string"},   # LLM 的思考
                "code": {"type": "string"},       # LLM 写的代码
            },
            "required": ["thoughts", "code"],
        }
    }
}
```

—— 强制 LLM 不输出"思考 + `<code>...</code>` 包裹代码"那种自由文本，而是直接输出 `{"thoughts": "...", "code": "..."}` 这种 JSON。

**🆕 structured 模式** = `CodeAgent(use_structured_outputs_internally=True)` 时启用这条路径。**默认 `False`**，所以主线剧本不走这条 —— 默认 LLM 输出仍然是"思考文字 + `<code>` 代码块"自由格式，框架靠 `parse_code_blobs` regex 抠代码（第 3 幕讲）。

**为什么会有 structured 模式**？因为 regex 抠代码偶尔会失败（LLM 偶尔忘了写 `<code>` 标签 / 写错格式），强制 JSON Schema 让解析更稳定。**代价**：要求 LLM API 服务器支持 `response_format`（不是所有 provider 都支持，Day 3 协议碎片化）。

详细见下面 **§番外 1**（演示 LLM 在两种模式下输出的差异）。

---

回到默认模式：顾问思考几秒，回话：

> "你应该跑这段代码：
> ```
> <code>
> temps = [get_temperature('Beijing'), get_temperature('Tokyo'), get_temperature('Singapore')]
> max_temp = max(temps)
> f = max_temp * 1.8 + 32
> final_answer(f)
> </code>
> ```"

这次顾问回话**没有 tool_calls 字段** —— 是一**段纯文字**，代码包在 `<code>...</code>` 里。

**代码层面**（[agents.py:1647-1701](../../../../src/smolagents/agents.py#L1647)）：

```python
memory_messages = self.write_memory_to_messages()
input_messages = memory_messages.copy()
memory_step.model_input_messages = input_messages

stop_sequences = ["Observation:", "Calling tools:"]
if self.code_block_tags[1] not in self.code_block_tags[0]:
    # If the closing tag is contained in the opening tag, adding it as a stop sequence would cut short any code generation
    stop_sequences.append(self.code_block_tags[1])         # ⭐ 加 closing tag

try:
    additional_args: dict[str, Any] = {}
    if self._use_structured_outputs_internally:
        additional_args["response_format"] = CODEAGENT_RESPONSE_FORMAT
    if self.stream_outputs:
        ... # (stream 分支同 01b 第 2 幕)
    else:
        chat_message: ChatMessage = self.model.generate(
            input_messages,
            stop_sequences=stop_sequences,
            **additional_args,                              # ⭐ 没有 tools_to_call_from！
        )
        memory_step.model_output_message = chat_message
        output_text = chat_message.content                  # ⭐ 直接拿 content 文字
        ...

    if not self._use_structured_outputs_internally:
        # 手动补 closing tag（如果 LLM 因为 stop 提前停了没写完）
        if output_text and not output_text.strip().endswith(self.code_block_tags[1]):
            output_text += self.code_block_tags[1]
            memory_step.model_output_message.content = output_text

    memory_step.token_usage = chat_message.token_usage
    memory_step.model_output = output_text
except Exception as e:
    raise AgentGenerationError(f"Error in generating model output:\n{e}", self.logger) from e
```

> 🤔 **新手疑问**：为什么"手动补 closing tag"只有 `if not self._use_structured_outputs_internally:` 才需要？
>
> 因为两种模式下 `output_text` 的**形态根本不同**：
>
> | 模式 | output_text 长什么样 | `</code>` stop 会触发吗 | 需要补 closing tag 吗 |
> |---|---|---|---|
> | **非 structured** | 自由文本 + `<code>代码</code>` 包裹 | ✅ 触发 → 服务器**截掉** `</code>` | ✅ 需要补 |
> | **structured** | 严格 JSON：`{"thoughts": "...", "code": "..."}` | ❌ 不触发（JSON 里没 `</code>` 字符串）| ❌ 不需要 |
>
> **非 structured 模式发生了什么**（呼应 Day 3 [stop-sequences §7 被动检测](../day3-models/model-stop-sequences.md)）：OpenAI 协议默认行为 = 检测到 stop 时**停止生成 + 不输出 stop 字符串本身**。所以 LLM 写到 `...final_answer(86.0)\n</code>` 时，服务器在 token 流里识别 `</code>` → 立刻停 → **截掉** `</code>` 返回 → `output_text` 缺了 closing tag → 框架手动补回让 memory 里的代码块语法完整（第 3 幕 `parse_code_blobs` 的 regex 需要完整的 `<code>...</code>` 对）。
>
> **structured 模式不需要补**：`response_format=CODEAGENT_RESPONSE_FORMAT` 强制 LLM 输出严格符合 JSON Schema 的结构（`{"thoughts": "...", "code": "..."}`）。JSON 自然结束在 `}` 处，整段输出**根本不含 `</code>` 字符串作为结构标记** —— 所以 `stop="</code>"` 即使传了也永不触发，服务器不会截任何东西。`output_text` 拿到完整 JSON 字符串，第 3 幕直接 `json.loads(output_text)["code"]` 取代码字段。
>
> 一句话本质：**非 structured 用 `</code>` 当 stop → 被截 → 需要补；structured 走 JSON 自然终止 → stop 永不触发 → 不需要补**。

**这一幕变了什么**：

| 变量 | 之前 | 之后 |
|---|---|---|
| `memory_step.model_output_message` | `None` | `ChatMessage(content="...代码字符串...")` |
| `memory_step.model_output` | `None` | `"...代码字符串..."` ← ⭐ 注意是文字，**`tool_calls` 字段为空** |
| `memory_step.token_usage` | `None` | `TokenUsage(...)` |

> 💡 **3 个关键差异点**：
>
> 1. **不传 `tools_to_call_from`**：LLM 不知道有"function calling 协议"可用，只能输出文字 + 代码块（**什么是 function calling 协议见下面 🆕 小节**）
> 2. **stop_sequences 加 `</code>`**：LLM 一写 `</code>` 立即停 —— **省 token**（不然 LLM 写完代码可能还会继续解释，浪费钱 + 拖慢）
> 3. **手动补 closing tag**：因为 stop 触发时 closing tag 本身**没被输出**（LLM 停在写 `</code>` 之前），所以李四要手动补一个，让 memory 里存的字符串语法完整。这是 Day 3 [stop_sequences §7 被动检测](../day3-models/model-stop-sequences.md) 的下游处理

### 🆕 一句话扫清术语：function calling 协议

这是 Week 1 / Day 2 / Day 3 反复提过但没正式介绍的概念，在这里集中讲清楚。

**本质**：OpenAI 在 2023 年 6 月给 chat completion 协议加的**扩展机制**，让 LLM 能"请求调用外部函数"，而不只是输出文字。**协议加了两个字段**：

| 协议字段 | 在哪一侧 | 谁填 | 干什么 |
|---|---|---|---|
| **`tools`** | 请求 body | agent 框架 | "告诉 LLM 你有这些工具可用，每个的 schema 长这样" |
| **`tool_calls`** | 响应 body | LLM API 服务器 | "LLM 决定调这个工具，参数是 X"（不是普通 content 文字）|

**没有这个协议的时代（GPT-3.5 早期）**：

```
你 → LLM：「巴黎天气怎样？」
LLM → 你：「抱歉，我无法访问实时数据。」   ← 只能输出文字
```

**有了这个协议（GPT-4 及之后）**：

```
你 → LLM：「巴黎天气怎样？附：我有这些工具：[get_weather, ...]」    ← 请求加 tools 字段
LLM → 你：响应 = {"tool_calls": [{"name": "get_weather", ...}]}    ← 响应给结构化 tool_calls 字段
你 → 真调 get_weather → 拿到 "12°C" → 发回 LLM
LLM → 你：「巴黎现在 12°C」                                          ← 最终文字答复
```

**因果关系**（回答"跟传 / 不传字段的关系"）：

```
agent 框架在请求里传了 tools 字段
    ↓
LLM 知道有这套协议可用
    ↓
响应里可能返回 tool_calls 字段（如果 LLM 决定调工具）
```

**对照两种 agent**：

| | ToolCallingAgent | CodeAgent |
|---|---|---|
| 请求里传 `tools` 字段？ | ✅ 传（`tools_to_call_from=...`）| ❌ 不传 |
| LLM 收到的协议信号 | "我可以走 function calling 协议" | "我只能用普通文本回应" |
| 响应有 `tool_calls` 字段吗？ | ✅ 有（结构化 JSON）| ❌ 没有，content 里是"思考 + `<code>` 代码块"自由文本 |
| 框架怎么解析 | 直接读 `chat_message.tool_calls` 字段（01 第 3 幕）| regex 从 content 里抠 `<code>...</code>`（第 3 幕 parse_code_blobs）|

**为什么 CodeAgent 故意放弃 function calling 协议**？让 LLM 用代码（Turing complete）表达决策 —— 一次能塞任意多操作（循环 / 计算 / 分支），而不是被 JSON 结构限制成"一次只能调一个 tool"。这就是 CodeAgent 通常 1 步搞定的根本原因。

📚 **跨厂商兼容性**：function calling 协议是 OpenAI 标准，但 Anthropic / Google Gemini / 国内主流厂商也基本兼容（字段名稍有差异，比如 Anthropic 用 `stop_reason: tool_use`）。不兼容的主要是 **reasoning / thinking 模型**（Day 3 [stop-sequences §9 协议碎片化](../day3-models/model-stop-sequences.md)）—— 这就是 Week 1 实战为什么不能用 thinking 模型跑 ToolCallingAgent 的根因。

---

## ⭐ 专题：控制 LLM 输出的 3 条路径（function calling vs structured output vs 自由文本）

第 2 幕涉及了 `tools_to_call_from`（function calling）和 `response_format=CODEAGENT_RESPONSE_FORMAT`（structured output）两个机制 + 默认的自由文本路径。**这 3 条都跟 JSON 有关，新手容易混淆 —— 集中讲清楚**。

### 一句话区分

| | function calling | structured output |
|---|---|---|
| **目的** | 让 LLM "请求调用外部函数" | 让 LLM "按固定结构吐数据" |
| **隐喻** | 🍽️ 点菜模式 | 📋 答题卡模式 |
| **LLM 的决定权** | 决定调不调、调哪个 | 不决定，必须按 schema 输出 |
| **响应里新增字段？** | ✅ 新增 `tool_calls` | ❌ 没新增（约束 `content` 必须是合法 JSON 字符串）|

### 协议字段精细对照

```
function calling 协议（点菜模式）
─────────────────────────────────
请求 body 加：
    tools = [{"name": "get_weather", "schema": {...}}, ...]

响应 body 给：
    {
      "content": null,                      ← content 字段（这次为空）
      "tool_calls": [{                      ⭐ 新增字段
        "name": "get_weather",
        "arguments": "{\"city\": \"Paris\"}"
      }]
    }


structured output 协议（答题卡模式）
─────────────────────────────────
请求 body 加：
    response_format = {"type": "json_schema", "schema": {...}}

响应 body 给：
    {
      "content": "{\"thoughts\": \"...\", \"code\": \"...\"}",
                ↑ content 字段还是普通文本，但这个文本必须严格符合 schema
      "tool_calls": null                    ← tool_calls 字段不动
    }
```

**关键差异 = "新字段 vs 约束旧字段"**：
- function calling **在响应里加了一个新字段**（`tool_calls`），承载"调用请求"这种新语义
- structured output **没加新字段**，只是把 `content` 字段的内容约束成合法 JSON 字符串

### smolagents 里的 3 条路径

| | 用 function calling？ | 用 structured output？ | LLM 输出形态 | 框架怎么解析 |
|---|---|---|---|---|
| **ToolCallingAgent** | ✅ 传 `tools` | ❌ | `tool_calls` 字段（结构化 JSON）| 直接读 `chat_message.tool_calls` 列表 |
| **CodeAgent（默认）** | ❌ | ❌ | `content` = "思考 + `<code>代码</code>`" 自由文本 | regex 抠 `<code>...</code>`（第 3 幕 `parse_code_blobs`）|
| **CodeAgent（structured 模式）** | ❌ | ✅ 传 `response_format` | `content` = `'{"thoughts":"...","code":"..."}'` JSON 字符串 | `json.loads(content)["code"]`（第 3 幕兜底）|

注意 CodeAgent 两条路径**都不用 function calling** —— 这是它的核心设计选择（Day 5 mental model §3-5 分歧点 1）。**function calling 是 ToolCallingAgent 独占**。

### 为什么 CodeAgent 不直接用 function calling 包代码？

理论上可以用 `tools=[{name: "execute_python", schema: {code: string}}]` 这种 —— 但 smolagents 没这么做：

1. **function calling 是给"调单个工具"设计的** —— 每个 tool_call 表示一次离散调用，不是"一段含逻辑的代码块"
2. **CodeAgent 的核心价值在"LLM 写多行 Python"** —— 自由文本 + `<code>` 包裹更自然，让 LLM 像写脚本一样写
3. **structured mode 是折中** —— 既要 JSON 严格性又要代码自由度（"思考 + 代码"两栏），但默认 mode 干脆放弃严格性

### 一次记牢的员工类比

把 LLM 比作员工，agent 框架比作老板：

| 模式 | 老板递给员工的 | 员工产出 |
|---|---|---|
| **function calling**（ToolCallingAgent）| 一份**菜单**（tools） | 在菜单上**勾选 1 道菜**（tool_calls）|
| **CodeAgent 默认** | **白纸** | 写一篇"含 `<code>` 代码块"的自由作文 |
| **CodeAgent + structured** | 带"思考 / 代码"**两栏的稿纸** | 必须按两栏填，但每栏写啥随意 |
| ❌ 不存在的 4 号选项 | 既给菜单又给答题卡 | 罕见组合，smolagents 不用 |

### 协议演进时间线（背景）

| 时间 | 事件 |
|---|---|
| 2023.6 | OpenAI 发布 **function calling**（GPT-3.5/4）—— LLM 第一次能"请求调用外部函数" |
| 2023.11 | OpenAI 发布 **JSON mode**（response_format: json_object）—— 强制 LLM 输出合法 JSON，但不约束 schema |
| 2024.8 | OpenAI 升级 **Structured Outputs**（response_format: json_schema）—— 强制符合具体 schema |
| 2024-2025 | Anthropic / Google / 国内厂商陆续跟进，但字段名 / 行为略有差异 |

---

## 第 3 幕 · 动作 ③ · 李四从顾问的话里抠代码（⭐ 分歧点 1 落地）

**李四视角**：

顾问没给我现成的 JSON 工具调用 —— 我得从他的回话**纯文字**里把代码段抠出来。

我有 3 把刀（按尝试顺序）：

| 刀 | 怎么抠 |
|---|---|
| ① 自定义 tags | `<code>(.*?)</code>` regex（默认 tags 是 `("<code>", "</code>")`）|
| ② markdown fallback | 如果 ① 没抠到，试 ```` ```python(.*?)```` ```` |
| ③ 裸代码兜底 | 如果 ② 还没抠到，`ast.parse(text)` 试整段文字是不是合法 Python |
| × 失败 | 抛 `AgentParsingError`（特别给 "final + answer" 的错误消息）|

刀 ① 命中 → 拿到代码字符串 `code_action`：

```python
temps = [get_temperature('Beijing'), get_temperature('Tokyo'), get_temperature('Singapore')]
max_temp = max(temps)
f = max_temp * 1.8 + 32
final_answer(f)
```

然后再用一把"修补刀" `fix_final_answer_code(code_action)`：检查代码里有没有"`final_answer = 某值`"这种赋值（会把 final_answer 函数变量盖掉）—— 有就改成 `final_answer_variable = ...`。**本剧本里没赋值，不变**。

**代码层面**（[agents.py:1703-1714](../../../../src/smolagents/agents.py#L1703) + [utils.py:198-251 parse_code_blobs](../../../../src/smolagents/utils.py#L198) + [local_python_executor.py:332 fix_final_answer_code](../../../../src/smolagents/local_python_executor.py#L332)）：

```python
try:
    if self._use_structured_outputs_internally:
        code_action = json.loads(output_text)["code"]
        code_action = extract_code_from_text(code_action, self.code_block_tags) or code_action
    else:
        code_action = parse_code_blobs(output_text, self.code_block_tags)   # ← 3 把刀
    code_action = fix_final_answer_code(code_action)                          # ← 修补刀
    memory_step.code_action = code_action                                     # ⭐ 写活页夹新栏目
except Exception as e:
    error_msg = f"Error in code parsing:\n{e}\nMake sure to provide correct code blobs."
    raise AgentParsingError(error_msg, self.logger)

tool_call = ToolCall(
    name="python_interpreter",
    arguments=code_action,
    id=f"call_{len(self.memory.steps)}",
)
yield tool_call                                                                # ⭐ 合成的 ToolCall
memory_step.tool_calls = [tool_call]
```

**这一幕变了什么**：

| 变量 | 之前 | 之后 |
|---|---|---|
| `code_action` | — | 代码字符串 |
| `memory_step.code_action` | `None` | 代码字符串 ⭐ **CodeAgent 独有字段** |
| `memory_step.tool_calls` | `None` | `[ToolCall("python_interpreter", code_action, id="call_2")]` ⭐ **合成的**，不是顾问给的 |
| **Yield 出去** | — | `ToolCall("python_interpreter", code, id="call_2")` |

> 💡 **3 个关键点**：
>
> 1. **`memory_step.code_action` 是 CodeAgent 独有字段**（Day 1 [action-step-anatomy](../day1-memory/action-step-anatomy.md) 13 字段中只 CodeAgent 用的那个）
> 2. **`memory_step.tool_calls` 仍然要写** —— 但里面是**合成的 `ToolCall(name="python_interpreter", arguments=代码)`**，不是 LLM 给的 —— **这是为了让 ToolCallingAgent 和 CodeAgent 的 log / replay / monitor 接口统一**（Day 1 已揭示的设计精髓）
> 3. **`yield ToolCall` 也照样发** —— 让外层 consumer 知道"即将执行代码"，跟 ToolCallingAgent 第 4a 幕完全平行

---

## 第 4 幕 · 动作 ④ · 李四派代码助手老沙跑代码（⭐ 分歧点 2 落地）

**李四视角**：

代码已经抠出来了，整段交给代码助手老沙。**李四自己不管小王、小赵的指挥** —— 那是老沙在沙箱小屋里的事。

老沙接过代码：

```python
temps = [get_temperature('Beijing'), get_temperature('Tokyo'), get_temperature('Singapore')]
max_temp = max(temps)
f = max_temp * 1.8 + 32
final_answer(f)
```

进沙箱小屋（Day 6 详讲，今天**只看接口**）：

1. AST 解析 → 检查每个语句是否安全
2. 在受限 namespace 跑 `get_temperature("Beijing")` → `25.0`（这里**真调用** Day 2 的 `Tool.__call__`）
3. 继续跑 → `temps = [25.0, 30.0, 28.0]`
4. 继续跑 → `max_temp = 30.0`
5. 继续跑 → `f = 86.0`
6. 继续跑 → `final_answer(86.0)` → **抛 `FinalAnswerException(86.0)` 被沙箱捕获** → `is_final_answer = True`

老沙交回一份**沙箱报告** `CodeOutput`：

```python
CodeOutput(
    output=86.0,           # final_answer 抛出的值
    logs="",               # 执行过程的 print 输出（这次没 print）
    is_final_answer=True,  # ⭐ 沙箱内部检测到 final_answer 调用
)
```

**代码层面**（[agents.py:1724-1755](../../../../src/smolagents/agents.py#L1724)）：

```python
### Execute action ###
self.logger.log_code(title="Executing parsed code:", content=code_action, level=LogLevel.INFO)
try:
    code_output = self.python_executor(code_action)              # ⭐ 调老沙
    execution_outputs_console = []
    if len(code_output.logs) > 0:
        execution_outputs_console += [Text("Execution logs:", style="bold"), Text(code_output.logs)]
    observation = "Execution logs:\n" + code_output.logs
except Exception as e:
    # 错误处理：保留 _print_outputs / 特判 import 错误
    if hasattr(self.python_executor, "state") and "_print_outputs" in self.python_executor.state:
        execution_logs = str(self.python_executor.state["_print_outputs"])
        if len(execution_logs) > 0:
            ...
            memory_step.observations = "Execution logs:\n" + execution_logs
    error_msg = str(e)
    if "Import of " in error_msg and " is not allowed" in error_msg:
        self.logger.log("[bold red]Warning: Code execution failed due to an unauthorized import - Consider passing said import under `additional_authorized_imports`...", level=LogLevel.INFO)
    raise AgentExecutionError(error_msg, self.logger)

truncated_output = truncate_content(str(code_output.output))
observation += "Last output from code snippet:\n" + truncated_output
memory_step.observations = observation
```

**这一幕变了什么**：

| 变量 | 之前 | 之后 |
|---|---|---|
| `code_output` | — | `CodeOutput(output=86.0, logs="", is_final_answer=True)` |
| `memory_step.observations` | `None` | `"Execution logs:\n\nLast output from code snippet:\n86.0"` |

> 💡 **5 个关键点**：
>
> 1. **`python_executor` 是个 callable** —— `__call__(code_action) -> CodeOutput`（Day 6 [PythonExecutor 抽象类](../../../../src/smolagents/local_python_executor.py#L1677) 详讲）
> 2. **没有 yield ToolOutput** ⭐⭐ —— 跟 ToolCallingAgent 第 4c 幕不同！CodeAgent 整段代码是 1 次执行，不是逐个 tool 调用，**事件层面只发 1 个 ToolCall + 1 个 ActionOutput**
> 3. **`logs` 是沙箱里 `print(...)` 的输出累积**，跟 `output`（最后表达式 / final_answer 值）分开存
> 4. **`is_final_answer` 由沙箱设**（不像 ToolCallingAgent 是凭 `tool_name == "final_answer"` 字符串判断）—— 沙箱实际是 catch `FinalAnswerException`
> 5. **错误特判 `Import of X is not allowed`** —— 引导用户加 `additional_authorized_imports`

---

## 第 5 幕 · 动作 ⑤ · 李四交差

**李四视角**：

老沙的报告里 `is_final_answer=True` 就是好消息！**这一步就是最后一步**。把 `output=86.0` 包成 `ActionOutput` 喊一声"工作交付！"，老板对讲机最后响一下。

**代码层面**（[agents.py:1757-1765](../../../../src/smolagents/agents.py#L1757)）：

```python
if not code_output.is_final_answer:
    execution_outputs_console += [Text(f"Out: {truncated_output}")]
self.logger.log(Group(*execution_outputs_console), level=LogLevel.INFO)
memory_step.action_output = code_output.output           # ⭐ 写活页夹
yield ActionOutput(output=code_output.output, is_final_answer=code_output.is_final_answer)
```

**这一幕变了什么**：

| 变量 | 之前 | 之后 |
|---|---|---|
| `memory_step.action_output` | `None` | `86.0` ⭐ CodeAgent **直接写 `action_output`**（ToolCallingAgent 不写，由外层处理）|
| **Yield 出去** | — | `ActionOutput(output=86.0, is_final_answer=True)` ⭐ 最后一响 |

**张三收到 `is_final_answer=True`** → Day 4 ③ §RunResult 收尾 → 老板拿到 `86.0`。

> ⚠️ **关键对比**：CodeAgent 把 `memory_step.action_output` 写在 `_step_stream` 内部；ToolCallingAgent 第 5 幕没写这一栏（由 Day 4 外层 _run_stream 处理）。这是 Day 5 mental-model §6 表格那个**注脚**的实证 —— 两子类在"谁写 action_output"上的不一致。

---

## 🎬 一图压缩：CodeAgent Step 1 的 8 个变化点

```
进入 _step_stream(action_step):
  ┌──────────────────────────────────────────────────────────┐
  │ 第 0 幕 │ action_step 出生：step_number=1, 其他 None      │
  ├──────────────────────────────────────────────────────────┤
  │ 第 1 幕 │ ↓ memory_step.model_input_messages = [SYS, USER]│
  ├──────────────────────────────────────────────────────────┤
  │ 第 2 幕 │ ↓ memory_step.model_output_message = ChatMessage│
  │         │ ↓ memory_step.model_output = "代码字符串..."     │
  │         │ ↓ memory_step.token_usage                        │
  │         │ ⚠️ 手动补 closing tag (</code>)                  │
  ├──────────────────────────────────────────────────────────┤
  │ 第 3 幕 │ parse_code_blobs (3 把刀) + fix_final_answer    │
  │         │ ↓ memory_step.code_action = "代码字符串..."     │
  │         │ ↓ memory_step.tool_calls = [合成的 ToolCall]    │
  │         │ ⭐ yield ToolCall("python_interpreter", code)   │
  ├──────────────────────────────────────────────────────────┤
  │ 第 4 幕 │ python_executor(code) → CodeOutput              │
  │         │ ↓ memory_step.observations = "Execution logs..."│
  ├──────────────────────────────────────────────────────────┤
  │ 第 5 幕 │ ↓ memory_step.action_output = 86.0              │
  │         │ ⭐ yield ActionOutput(86.0, is_final=True)      │
  └──────────────────────────────────────────────────────────┘
退出 _step_stream
```

**对比 [01b ToolCallingAgent](01-toolcalling-walkthrough.md#-一图压缩step-1-的-10-个变化点) 的 10 个变化点**：

| 维度 | ToolCallingAgent | CodeAgent |
|---|---|---|
| 总变化点 | 10 | 8（少了 4a/4b/4c/4d 4 个，多了 1 个 code_action）|
| yield 事件 | ToolCall, ToolOutput, ActionOutput | ToolCall（合成）, ActionOutput |
| 第 4 幕嵌套 | process_tool_calls 内部 2 阶段 yield | 直接 python_executor 一次 |
| 老板对讲机响 | 3 下（单 tool 单步）| **2 下** |
| `code_action` 字段 | **不写** | **写**（CodeAgent 独有）|
| `action_output` 字段 | 不在 _step_stream 写（外层写） | **在 _step_stream 写** |

---

## 🌟 番外篇 1 · structured_outputs 模式（`_use_structured_outputs_internally=True`）

**新场景**：用 `response_format=CODEAGENT_RESPONSE_FORMAT` 强制 LLM 输出 JSON。

**第 2 幕变化**（[agents.py:1658-1659](../../../../src/smolagents/agents.py#L1658)）：

```python
if self._use_structured_outputs_internally:
    additional_args["response_format"] = CODEAGENT_RESPONSE_FORMAT   # JSON Schema 强制
```

顾问回话**不是文字** —— 是 JSON：

```json
{"thoughts": "I should query temperatures...", "code": "temps = [...]\nfinal_answer(86.0)"}
```

**第 3 幕变化**（[agents.py:1705-1707](../../../../src/smolagents/agents.py#L1705)）：

```python
if self._use_structured_outputs_internally:
    code_action = json.loads(output_text)["code"]                                     # 拿 JSON.code 字段
    code_action = extract_code_from_text(code_action, self.code_block_tags) or code_action
```

**好处**：解析更稳定（JSON 严格 schema vs `<code>` regex）。**代价**：要求 provider 支持 `response_format`（不是所有都支持）。

---

## 🌟 番外篇 2 · `parse_code_blobs` 3 把刀（[utils.py:198-251](../../../../src/smolagents/utils.py#L198)）

**刀 ①**：`extract_code_from_text(text, self.code_block_tags)` — 正常 case，配 `<code>` 标签

**刀 ② fallback markdown**：

```python
if not matches:
    matches = extract_code_from_text(text, ("```(?:python|py)", "\n```"))
```

—— LLM 习惯输出 markdown 代码块，即使 system_prompt 教了用 `<code>` 也可能反弹

**刀 ③ 裸代码**：

```python
try:
    ast.parse(text)
    return text
except SyntaxError:
    pass
```

—— 万一 LLM 直接吐了一段没包裹的 Python 代码（`ast.parse` 成功就当代码用）

**× 失败兜底**：

```python
if "final" in text and "answer" in text:
    raise ValueError("...你想返回最终答案？应该写 final_answer(...)...")
raise ValueError("...regex pattern 没匹配，请写代码块...")
```

—— 错误消息引导 LLM 下一轮修正 → ReAct 反馈信号

---

## 🌟 番外篇 3 · `fix_final_answer_code` 修补（[local_python_executor.py:332](../../../../src/smolagents/local_python_executor.py#L332)）

**场景**：LLM 不知道 `final_answer` 是函数，错写成赋值：

```python
final_answer = 86.0          # ⚠️ 把 final_answer 函数变量覆盖了
print(final_answer)          # 不会触发 FinalAnswerException
```

**修补逻辑**：

```python
def fix_final_answer_code(code: str) -> str:
    assignment_pattern = r"(?<!\.)(?<!\w)\bfinal_answer\s*="
    if "final_answer(" not in code or not re.search(assignment_pattern, code):
        # 没赋值 / 没调用：不改（避免误改）
        return code
    # 既调用又赋值：把赋值改成 final_answer_variable
    ...
```

**安全门**：只在代码**同时包含 `final_answer(` 调用 + 赋值**时才修。如果只赋值不调用，原样返回 —— 让后续报错"final_answer 不可调用"。

---

## 🌟 番外篇 4 · 沙箱小屋 vs 储物柜（CodeAgent vs ToolCallingAgent 跨步状态对比）

**ToolCallingAgent 的 state 储物柜**（[01b 番外 3](01-toolcalling-walkthrough.md#-番外篇-3--state-储物柜机制跨步骤传图片)）：

- 一个 `dict`（`agent.state`）
- tool 返回 `AgentImage` → 存 `state["image.png"]` → 下一轮 LLM 写 `{"image_path": "image.png"}` → 替换回
- **关键点**：LLM 看不到 state 内容，只能通过字符串 key 引用

**CodeAgent 的沙箱小屋**：

- 沙箱内部一个 Python namespace（`executor.state`）
- 第一步跑 `x = get_temperature("Beijing")` → namespace 里 `x = 25.0`
- 第二步跑 `print(x)` → 沙箱仍记得 `x` —— **变量天然跨步骤共享**
- **不需要 state 字典转换** —— Python namespace 直接做这件事

**两套机制的本质差异**：

| 维度 | state 储物柜（ToolCalling）| 沙箱 namespace（Code）|
|---|---|---|
| 实现 | `agent.state: dict` | `executor.state` Python namespace |
| LLM 接口 | 字符串 key（如 `"image.png"`）| 变量名（如 `x`）|
| LLM 看到的内容 | tool 返回类型描述（如 `"Stored 'image.png' in memory."`）| 直接是 print logs |
| 数据流 | 跨 tool 调用通过 state 字典转 | 跨 step 通过同一 namespace 续命 |
| 适用对象 | 二进制资产（图 / 音）| 任意 Python 对象 |

> 💡 **为什么 CodeAgent 通常更少 step**？除了"一段代码塞任意多操作"，还因为**变量天然跨步骤记着**（不需要 LLM 重新写 "image_path" 字符串）。这是 CodeAgent 的一个隐藏优势。Day 6 沙箱深度笔记会详讲。

---

## 老板视角事件序列（呼应 Day 4 ③' + 01b）

`agent.run(stream=True, ...)` 模式下，老板 for 循环里**这一整次任务**收到的事件顺序：

```
# Step 1（CodeAgent 通常一步搞定）
ChatMessageStreamDelta × N    （只在 stream_outputs=True）
ToolCall(name="python_interpreter", code)    （第 3 幕 yield）
ActionOutput(86.0, is_final=True)             （第 5 幕 yield）
ActionStep                                     ← Day 4 外层 yield（step 结束档案）
FinalAnswerStep(86.0)                          ← Day 4 外层 yield（任务终结）
```

**对比 [01b 老板视角](01-toolcalling-walkthrough.md#老板视角事件序列呼应-day-4-)**：

| | ToolCallingAgent | CodeAgent |
|---|---|---|
| Steps | 4 | 1 |
| 每步事件 | ToolCall + ToolOutput + ActionOutput | ToolCall(合成) + ActionOutput |
| **缺什么** | — | **没 ToolOutput**（沙箱执行不发反馈事件）|

---

## 单步调试断点对照表（HF 恢复后跑）

跑 [compare_agents.py](../../../scripts/compare_agents.py) CodeAgent 部分：

| 断点位置 | 应命中哪一幕 | Watch |
|---|---|---|
| [agents.py:1647](../../../../src/smolagents/agents.py#L1647) | **第 1 幕**（写 model_input_messages 前）| `memory_step.model_input_messages` |
| [agents.py:1699](../../../../src/smolagents/agents.py#L1699) | **第 2 幕末**（写 model_output 后）| `output_text`, `chat_message.tool_calls`（应为 None / 空）|
| [agents.py:1709](../../../../src/smolagents/agents.py#L1709) | **第 3 幕**（parse_code_blobs 后）| `code_action` |
| [agents.py:1711](../../../../src/smolagents/agents.py#L1711) | **第 3 幕末**（写 code_action 字段后）| `memory_step.code_action` |
| [agents.py:1721](../../../../src/smolagents/agents.py#L1721) | **第 3 幕**（yield 合成 ToolCall）| `tool_call.name`（应为 `"python_interpreter"`）|
| [agents.py:1727](../../../../src/smolagents/agents.py#L1727) | **第 4 幕**（调 python_executor 前）| `code_action` |
| [agents.py:1755](../../../../src/smolagents/agents.py#L1755) | **第 4 幕末**（写 observations 后）| `memory_step.observations` |
| [agents.py:1765](../../../../src/smolagents/agents.py#L1765) | **第 5 幕**（yield ActionOutput）| `code_output.is_final_answer`, `memory_step.action_output` |

---

## 关联阅读

- 配对（line-by-line 实现）：02-codeagent-step-stream-impl.md（待写）
- 对照阅读：[01-toolcalling-walkthrough.md](01-toolcalling-walkthrough.md) — 同任务 ToolCallingAgent 版
- 上游骨架：[00-step-stream-role-overview.md](00-step-stream-role-overview.md)
- 概念预备：[Week 1 codeagent-how-it-works](../../02-concepts/codeagent-how-it-works.md) — Q1-Q4 把 CodeAgent 工作机制讲透
- 下游：[Day 6 local_python_executor.py](../../../../src/smolagents/local_python_executor.py) — 沙箱小屋的内部装修（待读）

---

## 自检（学完本篇应能）

- [ ] 不看笔记默讲 CodeAgent Step 1 的 8 个变化点（第 0 → 第 5 幕）
- [ ] 一句话说出 CodeAgent 第 2 幕 vs ToolCallingAgent 第 2 幕的 3 个差异
- [ ] 解释为什么 CodeAgent `memory_step.tool_calls` 里塞的是"合成"的 ToolCall，而不是空 list
- [ ] 解释 CodeAgent 老板对讲机为什么响 2 下（不是 3 下），少了哪个事件
- [ ] 描述沙箱 namespace 跟 ToolCallingAgent 的 state 储物柜在跨步骤上的本质差异
- [ ] 解释为什么 CodeAgent 第 2 幕末要"手动补 closing tag"

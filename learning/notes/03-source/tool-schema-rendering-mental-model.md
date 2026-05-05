---
created: 2026-05-05
status: active
tags: [smolagents, tools, mental-model, schema, rendering, source-reading]
---

# Tool 渲染：一份数据，4 种形状

> ⚠️ **必读前置**：
> 1. [tool-class-role-overview.md](tool-class-role-overview.md) — Tool 类整体角色（特别是组 D：渲染方法）
> 2. [tool-lifecycle-checks-mental-model.md](tool-lifecycle-checks-mental-model.md) — Tool 实例两次质检（出厂 + 上岗），前置质检通过后才有渲染的资格

## 背景 / 动机

Tool 类[角色概览](tool-class-role-overview.md) 说：组 D 的方法负责"把 Python 类对象翻译成 LLM/网络/磁盘看得懂的形状"。**这是 Tool 类的最核心价值** —— Day 1 你听到的 "agent 把 tool schema 喂给 LLM" 这句话，**真正发生的地方就在这里**。

读完本笔记能回答：

1. 一个 Tool 实例需要被翻译给**几类客户**看？分别需要什么形状？
2. 这些形状**为什么不能合并成一种通用格式**喂给所有 LLM？
3. 为什么 Tool 类只有 3 个 `to_xxx` 方法、却有 4 类客户？**第 4 个形状由谁负责？**
4. CodeAgent 和 ToolCallingAgent 在拼 prompt 时，**到底从 Tool 拿了什么**？

---

## 1. 一句话定义 + 直觉画面

**Tool 实例是一份数据，需要被渲染成 4 种形状给 4 类客户看。**

直觉画面 —— 把 Tool 想成**一份产品规格说明** ：

```
                    一个 Tool 实例（产品规格说明）
                              │
        ┌──────────────┬──────┴──────┬──────────────┐
        ▼              ▼             ▼              ▼
   ① 给 CodeAgent  ② 给 ToolCalling  ③ 给 ToolCalling  ④ 给磁盘 / Hub
     LLM 看的       Agent LLM 看的    Agent LLM 看的     看的
     (system        系统提示里的       HTTP body 里     (持久化
      prompt 内      文字描述           的 tools         格式)
      Python def)                      JSON)
        │              │              │              │
        ▼              ▼              ▼              ▼
   to_code_prompt  to_tool_calling   get_tool_json    to_dict
                   _prompt           _schema
                                     ⚠️ NOT on Tool!
```

**关键认知**：3 个方法在 Tool 类上 + 1 个独立函数在 models.py 里。**第 ③ 个形状不是 Tool 类的责任**，这是新手最容易误解的地方（包括我之前的笔记也搞错过）。

---

## 2. 角色与客户：4 类消费者各自要什么形状

### ① CodeAgent 的 LLM —— 要"假装的 Python def"

CodeAgent 的核心机制是**让 LLM 写 Python 代码**作为动作（Day 1 [codeagent-vs-toolcallingagent.md](../02-concepts/codeagent-vs-toolcallingagent.md) 讲过）。所以 prompt 里需要让 LLM **看到工具像看到 Python 函数一样自然**：

```python
def get_temperature(city: str) -> number:
    """Get current temperature in Celsius for a city.

    Args:
        city: City name (English).
    """
```

**这不是真的 Python 函数** —— 是 `to_code_prompt()` 拼出来的字符串，注入到 system prompt。**LLM 看到这个伪 def，就知道有这个工具、参数怎么传**，写代码时 `get_temperature("Beijing")` 就调对了。

### ② ToolCallingAgent 的 LLM（文字部分）—— 要简洁文字描述

ToolCallingAgent 系统提示里需要给 LLM 一份**人类可读的工具清单**，告诉它"你手头有这些工具可用"：

```
- get_temperature: Get current temperature in Celsius for a city.
    Takes inputs: {'city': {'type': 'string', 'description': 'City name'}}
    Returns an output of type: number
```

**这就是 `to_tool_calling_prompt()` 的产出**。注意它**不是 JSON 而是普通文本**，因为它是写在 system prompt 里的描述，不是 HTTP `tools` 字段的真实参数。

### ③ ToolCallingAgent 的 LLM（机器部分）—— 要 OpenAI 标准 JSON

这才是真正进入 HTTP 请求体 `tools` 字段的部分（OpenAI / Anthropic 的 function calling 标准）：

```json
{
  "type": "function",
  "function": {
    "name": "get_temperature",
    "description": "Get current temperature in Celsius for a city.",
    "parameters": {
      "type": "object",
      "properties": {
        "city": {"type": "string", "description": "City name"}
      },
      "required": ["city"]
    }
  }
}
```

**关键事实**：这个形状**不是** Tool 类的 `to_tool_calling_prompt` 产出的。它由 [models.py:288](../../../src/smolagents/models.py#L288) 的 **独立函数 `get_tool_json_schema(tool)`** 产出，在拼 HTTP body 时调（[models.py:540](../../../src/smolagents/models.py#L540)）。

> 💡 **为什么放在 models.py 而不是 tools.py？** 因为这个形状是给 **LLM provider 的 API 协议**用的（OpenAI / Anthropic 等），属于"模型调用层"的关注点，不是 Tool 自身的核心职责。**这是关注点分离的好例子**。

### ④ 磁盘 / HF Hub —— 要序列化字典

`to_dict()` 把 Tool 序列化成 dict，包含完整源码、依赖列表、output_schema 等，便于 `save()` / `push_to_hub()` 落盘或上传：

```python
{
    "name": "get_temperature",
    "code": "from smolagents import Tool\n...\nclass GetTemperatureTool(Tool):\n    ...",
    "requirements": ["smolagents", ...],
    "output_schema": ...
}
```

**这个形状的客户是磁盘和 HF Hub**，第一遍学习不重要 —— 但理解它存在能让你看清"为什么 Tool 类有 `to_dict` 这个方法"。

---

## 3. 与已知的连接（类比对照）

### 类比 1：API 规格的多种呈现

一份 RESTful API 规格通常有 **3 种形态**同时存在：

| 形态 | 给谁看 | 例子 |
|---|---|---|
| HTML 文档（Swagger UI） | 人类开发者 | 漂亮的网页，有 Try-it-out 按钮 |
| OpenAPI JSON | 代码生成器 | 给 swagger-codegen / openapi-typescript |
| TypeScript `.d.ts` | TypeScript 编译器 | `.d.ts` 类型定义 |

**Tool 的 4 类形状本质上是同一回事** —— 一份规格给不同的"消费者"看，根据消费者的处理方式选最适合的语法。

### 类比 2：Jinja 模板引擎

`to_code_prompt` 内部就是个迷你模板引擎：从 `inputs` / `description` / `output_type` 这些数据 **拼出文本**。这跟 Django/Jinja 模板把数据填进 `<html>` 模板是同一思想 —— **数据 → 模板 → 视图**。

### 类比 3：序列化的多种格式

同一个 Python 对象可以序列化成 JSON / YAML / Pickle / MessagePack / Protobuf —— 选哪种取决于消费者。Tool 的 4 种渲染本质也是 **多目标序列化**。

---

## 4. 为什么这样设计（约束推导）

### 4.1 为什么不能用一种通用 schema 喂给所有 LLM？

**核心约束：LLM 的"动作格式"决定了它需要什么样的提示**

| LLM 模式 | 动作格式 | 最适合的工具呈现 |
|---|---|---|
| CodeAgent | LLM 写 Python 代码 | 假装的 Python `def`（LLM 见过海量 Python，识别度最高） |
| ToolCallingAgent | LLM 输出 OpenAI tool_calls JSON | OpenAI 标准 schema（LLM 训练时被这种格式喂过） |

**用错形态会怎样？**
- 把 OpenAI JSON 塞给 CodeAgent → LLM 写代码时不知道函数签名怎么对应，瞎猜
- 把 Python `def` 塞给 ToolCallingAgent → LLM 找不到 `tools` 字段，完全不知道有工具可用

**结论**：必须按 LLM 模式定制呈现形态。

### 4.2 为什么 ToolCallingAgent 需要**两份**渲染（系统提示 + tools 字段）？

| 部分 | 渲染方法 | 内容 | 用途 |
|---|---|---|---|
| 系统提示文字 | `to_tool_calling_prompt()` | 人类可读的工具清单 | 让 LLM 理解"我有哪些工具、它们能做啥" |
| HTTP `tools` 字段 | `get_tool_json_schema(tool)` | 机器格式 schema | 让 LLM 调工具时按 OpenAI 标准输出 tool_calls |

**两者缺一不可**：
- 没有系统提示文字 → LLM 不知道工具的语义/用法
- 没有 tools 字段 → LLM 即使想调工具，输出格式不被框架识别

> 💡 **这就是为什么 ToolCallingAgent 涉及 2 个独立函数（`to_tool_calling_prompt` + `get_tool_json_schema`）**。它们是**配对使用**的，一份给 LLM 看语义、一份给 LLM 输出格式参考。

### 4.3 为什么 `get_tool_json_schema` 不是 Tool 类的方法？

**关注点分离**：
- Tool 类的方法应该只关心**"我是什么"**（name / description / inputs / output_type）
- `get_tool_json_schema` 关心**"如何把我打包成给 LLM provider 的 API 协议格式"** —— 这属于**模型调用层**

如果把它放进 Tool 类，Tool 就被绑定到 OpenAI/Anthropic 的 function calling 协议上。**未来 Anthropic 改了协议、或者出了新的 LLM provider，要改 Tool 类**。放在 models.py 的话，改的是"调用层"，Tool 类完全不动。

> 💡 **架构嗅觉**：方法的归属取决于"它的依赖朝哪个方向"。如果方法依赖外部协议（OpenAI API），就不应该放在核心类里。

---

## 5. 4 个渲染路径全览

| 路径 | 渲染产出 | 渲染者 | 消费者 | 何时调用 |
|---|---|---|---|---|
| ① CodeAgent system prompt | 假装的 Python `def` 块 | `to_code_prompt()` ([tools.py:258](../../../src/smolagents/tools.py#L258)) | `code_agent.yaml` Jinja 模板 | 每次 ReAct 循环开始拼 prompt |
| ② ToolCallingAgent system prompt | 一行文字描述 | `to_tool_calling_prompt()` ([tools.py:289](../../../src/smolagents/tools.py#L289)) | `toolcalling_agent.yaml` Jinja 模板 | 每次 ReAct 循环开始拼 prompt |
| ③ ToolCallingAgent HTTP `tools` 字段 | OpenAI 标准 JSON | **`get_tool_json_schema(tool)`** ([models.py:288](../../../src/smolagents/models.py#L288)) ⚠️ NOT on Tool | Model.generate() 拼请求体 | 每次 ReAct 循环 LLM 调用前 |
| ④ 磁盘 / HF Hub | 序列化字典 | `to_dict()` ([tools.py:292](../../../src/smolagents/tools.py#L292)) | `save()` / `push_to_hub()` | 用户显式调 |

### YAML 模板里实际怎么用？

[code_agent.yaml:135](../../../src/smolagents/prompts/code_agent.yaml#L135)：

```yaml
{{ tool.to_code_prompt() }}
```

[toolcalling_agent.yaml:94](../../../src/smolagents/prompts/toolcalling_agent.yaml#L94)：

```yaml
- {{ tool.to_tool_calling_prompt() }}
```

**这是 Jinja2 模板调用 Tool 的方法把渲染结果嵌进 prompt 文本**。框架在每次 ReAct 循环开始时把模板和当前 tool 列表 + memory 渲染成最终的 messages 数组发给 LLM。

---

## 6. 数据流图：从 Tool 实例到 LLM 看到的最终形态

```
┌─────────────────────────────────────────────────────────┐
│ class WeatherTool(Tool):                                 │
│     name = "get_temperature"                             │
│     description = "..."                                  │
│     inputs = {"city": {"type": "string", ...}}           │
│     output_type = "number"                               │
│     def forward(self, city): ...                         │
└─────────────────────────────────────────────────────────┘
                           │
                  tool = WeatherTool()
                           │
        ┌──────────────────┼──────────────────┐
        ▼                  ▼                  ▼
                   [CodeAgent path]    [ToolCallingAgent path]
                           │                  │                  │
                           │                  │                  │
                  to_code_prompt()    to_tool_calling   get_tool_json
                           │           _prompt()           _schema(tool)
                           │                  │                  │
                           ▼                  ▼                  ▼
                  ┌────────────┐    ┌────────────┐    ┌────────────┐
                  │ "def get_  │    │ "- get_temp:│   │ {"type":   │
                  │  temp(city:│    │  ...        │    │  "function"│
                  │  string)   │    │  Takes ..." │    │  "function"│
                  │  -> number"│    │             │    │  : {...}}  │
                  └─────┬──────┘    └─────┬──────┘    └─────┬──────┘
                        │                  │                  │
                  injected into       injected into      attached to
                  code_agent.yaml    toolcalling_agent  HTTP request
                  system prompt       .yaml system       body's "tools"
                                      prompt              field
                        │                  │                  │
                        └──────────────────┴──────────────────┘
                                           │
                                           ▼
                                    ┌─────────────┐
                                    │  LLM 看到的  │
                                    │   完整请求    │
                                    └─────────────┘
```

---

## 7. 实现细节速查

### 7.1 `to_code_prompt()` 的拼装步骤

[tools.py:258-287](../../../src/smolagents/tools.py#L258)：

```python
def to_code_prompt(self) -> str:
    # 1. 拼参数签名："city: string, unit: string"
    args_signature = ", ".join(f"{n}: {s['type']}" for n, s in self.inputs.items())

    # 2. 拼函数签名："(city: string, unit: string) -> number"
    output_type = "dict" if has_schema else self.output_type
    tool_signature = f"({args_signature}) -> {output_type}"

    # 3. 拼 docstring：description + Args 段（必）+ Returns 段（仅当 output_schema 存在）
    tool_doc = self.description + "\n\nArgs:\n    city: City name\n    ..."

    # 4. 包成 def 块
    return f"def {self.name}{tool_signature}:\n    \"\"\"...\"\"\""
```

**输出长这样**：

```python
def get_temperature(city: string) -> number:
    """Get current temperature in Celsius for a city.

    Args:
        city: City name (English).
    """
```

### 7.2 `to_tool_calling_prompt()` 一行拼出来

[tools.py:289-290](../../../src/smolagents/tools.py#L289)：

```python
def to_tool_calling_prompt(self) -> str:
    return f"{self.name}: {self.description}\n    Takes inputs: {self.inputs}\n    Returns an output of type: {self.output_type}"
```

**简单粗暴 —— 一行 f-string 把所有信息拼成文本**。

### 7.3 `get_tool_json_schema(tool)` 在 models.py 的工作

[models.py:288-326](../../../src/smolagents/models.py#L288)：

```python
def get_tool_json_schema(tool: Tool) -> dict:
    properties = deepcopy(tool.inputs)
    required = []
    for key, value in properties.items():
        if value["type"] == "any":
            value["type"] = "string"        # OpenAI 不认识 "any"，转成 string
        if not ("nullable" in value and value["nullable"]):
            required.append(key)             # 没标 nullable 的进 required 列表
        # ... 处理 anyOf 联合类型
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            }
        }
    }
```

**做的事**：从 `tool.inputs` 转换成 OpenAI function calling 标准格式，处理 nullable/anyOf 等边角。

### 7.4 `to_dict()` 的两条分支

[tools.py:292-365](../../../src/smolagents/tools.py#L292) 复杂得多，因为要把 Tool 序列化成可以重新构造的源码：

| 分支 | 触发条件 | 做的事 |
|---|---|---|
| SimpleTool 分支 | 用 `@tool` 装饰器创建的 | 提取 forward 函数源码，包装成 Tool 子类源码 |
| 普通子类分支 | 直接继承 Tool 的 | 用 `instance_to_source` 把整个类还原成源码字符串 |

**第一遍学习只需要知道 to_dict 存在 + 它输出 `{"name": ..., "code": ..., "requirements": ...}`** 的字典。具体实现等做 push_to_hub 实验时再深究。

---

## 8. ⚠️ 修正：role-overview 笔记里的一处错误

我之前在 [tool-class-role-overview.md §3 组 D](tool-class-role-overview.md) 写的：

> | `to_tool_calling_prompt` | 渲染成 OpenAI tools 字段格式 | ToolCallingAgent 拼 HTTP 请求体时 |

**这个说法不准确**。正确的是：
- `to_tool_calling_prompt` 渲染成**系统提示里的文字描述**，不是 HTTP `tools` 字段
- HTTP `tools` 字段由 **`get_tool_json_schema(tool)`**（在 [models.py](../../../src/smolagents/models.py#L288)）渲染，这是个**独立函数**不在 Tool 类上

role-overview 笔记会同步修正。**这个误解很常见**（连我自己写的时候都搞错了），新读源码时容易把"工具描述"和"工具协议"混在一起。**记住：Tool 类上的 3 个 to_xxx 方法 + 1 个外部 get_tool_json_schema = 4 个渲染产出**。

---

## 9. 自我验证（4 个问题）

读完本笔记后，应该能不查源码答出：

1. **Tool 实例需要被翻译给几类客户看？**
   - 4 类：CodeAgent LLM / ToolCallingAgent LLM 的文字部分 / ToolCallingAgent LLM 的 JSON 部分 / 磁盘

2. **CodeAgent 和 ToolCallingAgent 在拼 prompt 时分别从 Tool 拿了什么？**
   - CodeAgent：拿 `to_code_prompt()` 的 Python def 块塞进 system prompt
   - ToolCallingAgent：拿 `to_tool_calling_prompt()` 的文字描述塞进 system prompt + 拿 `get_tool_json_schema(tool)` 的 JSON 拼到 HTTP `tools` 字段

3. **为什么不能用一种通用 schema 喂给所有 LLM？**
   - LLM 模式不同（写代码 vs 输出 tool_calls JSON），需要不同的呈现形态匹配训练分布

4. **为什么 `get_tool_json_schema` 放在 models.py 而不是 Tool 类上？**
   - 关注点分离：它依赖外部协议（OpenAI 标准），属于模型调用层；Tool 核心类不应被绑定到具体协议

---

## 10. 对照源码精读

带着上面的 mental model 直接打开源码：

| 本笔记内容 | 源码位置 |
|---|---|
| §7.1 `to_code_prompt` | [tools.py:258-287](../../../src/smolagents/tools.py#L258) |
| §7.2 `to_tool_calling_prompt` | [tools.py:289-290](../../../src/smolagents/tools.py#L289) |
| §7.3 `get_tool_json_schema` ⚠️ 不在 Tool 类 | [models.py:288-326](../../../src/smolagents/models.py#L288) |
| §7.4 `to_dict` | [tools.py:292-365](../../../src/smolagents/tools.py#L292) |
| YAML 模板调用点 | [code_agent.yaml:135](../../../src/smolagents/prompts/code_agent.yaml#L135), [toolcalling_agent.yaml:94](../../../src/smolagents/prompts/toolcalling_agent.yaml#L94) |
| HTTP body 拼装点 | [models.py:540](../../../src/smolagents/models.py#L540) `completion_kwargs["tools"] = ...` |

**实战建议**：写一个简单 Tool 子类，分别打印 `tool.to_code_prompt()` / `tool.to_tool_calling_prompt()` / `get_tool_json_schema(tool)` 的输出，**亲眼对比 3 种形态**。这是 Day 2 的最后一个实验脚本（[learning/scripts/tool_schema_trace.py](../../scripts/) 待写）的核心目标。

---

## 相关链接

- 上层概览：[tool-class-role-overview.md](tool-class-role-overview.md)
- 横向关联：
  - [tool-lifecycle-checks-mental-model.md](tool-lifecycle-checks-mental-model.md) — 出厂质检通过后才有渲染的资格
  - Week 1 [codeagent-vs-toolcallingagent.md](../02-concepts/codeagent-vs-toolcallingagent.md) — 两种 agent 的 LLM 模式差异
  - Week 1 [model-and-protocols-overview.md](../02-concepts/model-and-protocols-overview.md) — function calling 协议背景
- 源码：
  - [tools.py:258-365](../../../src/smolagents/tools.py#L258) — Tool 类上的 3 个渲染方法
  - [models.py:288-326](../../../src/smolagents/models.py#L288) — `get_tool_json_schema`
  - [prompts/code_agent.yaml](../../../src/smolagents/prompts/code_agent.yaml), [prompts/toolcalling_agent.yaml](../../../src/smolagents/prompts/toolcalling_agent.yaml) — Jinja 模板

## 遗留问题

- [ ] `instance_to_source` 怎么把 Python 类对象还原成源码字符串？（to_dict 普通子类分支用到）
- [ ] OpenAI / Anthropic 的 function calling 协议历史 + 各家细节差异（[llm-protocols-deep-dive.md](../05-advanced/llm-protocols-deep-dive.md) 解封时再读）
- [ ] `MethodChecker` 是干什么的？（to_dict SimpleTool 分支调用了它）

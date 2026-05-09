---
created: 2026-05-05
status: active
tags: [smolagents, tools, schema, nullable, json-schema, openapi]
---

# Tool inputs 里的 `nullable` 字段

## 背景 / 动机

读 [tool_schema_trace.py](../../../scripts/tool_schema_trace.py) Demo 6 时遇到的疑问：

```python
inputs = {
    "city": {"type": "string", "description": "..."},
    "unit": {"type": "string", "description": "...", "nullable": True},
    #                                              ↑ 这是啥？
}
```

涉及 3 个问题：

1. `nullable` 是什么含义？来自哪个规范？
2. 标 vs 不标对 LLM 行为有什么影响？
3. 跟 Python 的默认值 / `Optional[X]` 类型注解什么关系？

> 💡 **直接答案**：`nullable: True` = "这个参数是可选的、LLM 可以不传"。**严格来源是 OpenAPI 3.0 的字段**（不是 JSON Schema 的，更不是 JSON 本身的）—— 详见 [json-schema-vs-openapi.md](../../02-concepts/json-schema-vs-openapi.md) 的协议层关系。跟 TypeScript `field?:` 或 Java `@Nullable` 一个意思。

---

## 1. 一句话定义

| 标记 | 含义 |
|---|---|
| `"nullable": True` | 这个参数 LLM 调用时**可以不传**（也允许传 null） |
| 不标 | 默认必填，LLM 必须传 |

**来源**：**OpenAPI 3.0 协议**里发明的字段（OpenAPI 3.1+ 已弃用，改回 JSON Schema 的 `type: ["X", "null"]` 风格）。**不是 JSON 本身的，也不是 JSON Schema 的**，更**不是** smolagents 自创。完整协议层关系见 [json-schema-vs-openapi.md](../../02-concepts/json-schema-vs-openapi.md)。

---

## 2. 直觉对照

Python 函数签名的"必传 vs 可选"：

```python
def get_temperature(city, unit="C"):
    #              ↑必传  ↑可选（有默认值）
```

对应到 Tool 的 `inputs`：

```python
inputs = {
    "city": {"type": "string", "description": "..."},                    # 必传
    "unit": {"type": "string", "description": "...", "nullable": True},  # 可选
}
```

类比对照：

| Python | TypeScript | Java | smolagents inputs |
|---|---|---|---|
| `unit="C"`（默认值） | `unit?: string` | `@Nullable String unit` | `"nullable": True` |

---

## 3. 在 smolagents 里 LLM 看到的差异

跑 [tool_schema_trace.py](../../../scripts/tool_schema_trace.py) Demo 6 看到：

**不标 nullable** 的字段（比如 city）：

```json
{
  "required": ["city"],     ← LLM 看到 city 在里面，知道"必须传"
  "properties": {
    "city": {"type": "string", "description": "..."}
  }
}
```

**标了 nullable** 的字段（比如 unit）：

```json
{
  "required": ["city"],     ← unit 不在里面
  "properties": {
    "unit": {"type": "string", "description": "...", "nullable": true}
                                                     ↑ 字段属性里也标
  }
}
```

LLM 收到 HTTP body 后看 `required` 列表 → **知道 unit 不在必填里 → 可以省略**。LLM 调用时输出：

```json
{"city": "Beijing"}        ← 只传 city，不传 unit
```

> 💡 **`required` 数组才是 LLM 真正"读"的信号**，远比 description 自然语言可靠（Demo 6 mental model 里讲过的"结构化信号 > 自然语言"）。

---

## 4. ⭐ 与 Python 默认值 / 类型注解的"双源真相"

`forward` 函数和 `inputs` 字典是**两份独立声明**，必须保持一致 —— 这就是 [validate_arguments 第 ⑥ 项](../../../../src/smolagents/tools.py#L219) 的双源真相对账。

**正例 1**：两边都"标记可选"

```python
inputs = {"unit": {..., "nullable": True}}
def forward(self, unit: str | None = None):  # 类型注解里有 | None
```

✅ 一致 —— 实例化通过

**正例 2**：两边都"必填"

```python
inputs = {"city": {"type": "string", ...}}   # 没 nullable
def forward(self, city: str):                # 没默认值、没 | None
```

✅ 一致 —— 实例化通过

**反例**：只在一边标

```python
inputs = {"unit": {..., "nullable": True}}   # 标了
def forward(self, unit: str):                # 没标 | None
```

```python
WeatherTool()
# 💥 AssertionError: Nullable argument 'unit' in inputs should have key 'nullable' set to True in function signature.
```

源码（[tools.py:219-226](../../../../src/smolagents/tools.py#L219)）：

```python
for key, value in self.inputs.items():
    if "nullable" in value:
        assert "nullable" in json_schema[key], ...   # inputs 标了 → forward 也得标
    if key in json_schema and "nullable" in json_schema[key]:
        assert "nullable" in value, ...               # forward 标了 → inputs 也得标
```

> 💡 **为什么必须双源一致？** 因为 LLM 看 `inputs`（通过 schema）来决定**传不传**，但 Python 实际执行靠 `forward` 签名（决定**能不能不传**）。两边声明不一致 → LLM 决策跟 Python 行为脱节，运行时崩。

---

## 5. 不标 nullable 但 forward 有默认值会怎样？

```python
class BadTool(Tool):
    name = "bad"
    description = "..."
    inputs = {"unit": {"type": "string", "description": "..."}}
    #                                  ↑ 没标 nullable
    output_type = "string"
    def forward(self, unit: str = "C"):    # 但有默认值
        return unit
```

**实例化**：能过（validate_arguments 不强制要求"有默认值就必须标 nullable"，因为它只看注解 `| None`，不看默认值本身）

**但运行时表现**：
- LLM 看 OpenAI schema → `required: ["unit"]` → **总是传 unit**（哪怕传个 null）
- 用户的默认值 `"C"` **永远用不上**
- LLM 多输出 token、agent 多算一次、用户白写默认值

> 💡 **最佳实践**：forward 有默认值 / `| None` 注解的参数，**对应的 inputs 字段就该标 `nullable: True`**。让两份声明语义对齐，避免"代码能跑但不符合预期"的隐性 bug。

---

## 6. 总结表

| 问题 | 答案 |
|---|---|
| nullable 是什么？ | JSON Schema 标准字段，标记"可选参数" |
| 来自哪个规范？ | **OpenAPI 3.0 发明的字段**（不是 JSON / JSON Schema 的；OpenAPI 3.1 已弃用）|
| 标了对 LLM 有啥影响？ | LLM 看到 `required` 列表里没这字段 → 知道可以不传 |
| 跟 Python 默认值什么关系？ | 语义上等价（都表达"可选"），但是**两套独立声明**，需要保持一致 |
| 跟 `Optional[X]` / `X \| None` 什么关系？ | 类型注解层面的对应物；validate_arguments 会校验两边一致 |
| 双源真相对账失败会怎样？ | 实例化时崩（出厂质检不通过） |
| 不标但 forward 有默认值合法吗？ | **能跑但不该这么写** —— LLM 会多余传参，默认值废了 |

---

## 7. 一段代码实测

```python
from smolagents import Tool
from smolagents.models import get_tool_json_schema

class T1(Tool):
    name = "t1"
    description = "..."
    inputs = {
        "x": {"type": "string", "description": "..."},                         # 必传
        "y": {"type": "string", "description": "...", "nullable": True},      # 可选
    }
    output_type = "string"
    def forward(self, x: str, y: str | None = None):
        return f"{x}-{y}"

t = T1()
schema = get_tool_json_schema(t)
print("required:", schema["function"]["parameters"]["required"])
# required: ['x']         ← 只有 x，y 因为 nullable=True 不在里面

print("y field:", schema["function"]["parameters"]["properties"]["y"])
# y field: {'type': 'string', 'description': '...', 'nullable': True}
```

---

## 相关链接

- 源码：
  - [tools.py:219-226](../../../../src/smolagents/tools.py#L219) — validate_arguments 第 ⑥ 项 nullable 一致性校验
  - [models.py:294-295](../../../../src/smolagents/models.py#L294) — get_tool_json_schema 把 nullable 字段排除出 required 列表
- 相关笔记：
  - [tool-schema-rendering-mental-model.md](tool-schema-rendering-mental-model.md) §6 — nullable 在 3 种渲染里的不同表达
  - [tool-lifecycle-checks-mental-model.md](tool-lifecycle-checks-mental-model.md) §5 第 ⑥ 项 — 双源真相对账机制
- 实验脚本：[tool_schema_trace.py](../../../scripts/tool_schema_trace.py) Demo 6
- 协议层背景：[json-schema-vs-openapi.md](../../02-concepts/json-schema-vs-openapi.md) — JSON / JSON Schema / OpenAPI 三者关系 + nullable 历史
- 外部规范：
  - [JSON Schema null type](https://json-schema.org/understanding-json-schema/reference/null.html) —— JSON Schema 用 `type` 数组表达可空（**没有** nullable 字段）
  - [OpenAPI 3.0 nullable](https://swagger.io/docs/specification/data-models/data-types/#null) —— `nullable` 字段的发源地

## 遗留问题

- [ ] `Optional[X]` vs `X | None` 的差异（user_profile 待解释清单里还有）
- [ ] `anyOf` 联合类型的处理（[models.py:298-316](../../../../src/smolagents/models.py#L298) 有相关代码）—— 进阶话题，碰到再说

---
created: 2026-05-05
status: active
tags: [protocol, json, json-schema, openapi, mental-model, prereqs]
---

# JSON / JSON Schema / OpenAPI 三者关系

## 背景 / 动机

读 [tool-input-nullable.md](../03-source/tool-input-nullable.md) 时遇到的疑问：

> `nullable` 字段到底是 JSON 本身的，还是 JSON Schema 的，还是 OpenAPI 的？

回答这个问题需要先把 3 个概念分清。这不只对 smolagents 有用 —— **以后看 OpenAI / Anthropic 的 function calling 协议、FastAPI、Pydantic、Swagger 文档**，都会反复用到这套区分。

读完能回答：

1. JSON 是数据还是协议？JSON Schema 跟 JSON 是什么关系？
2. OpenAPI 跟 JSON Schema 又是什么关系？
3. `nullable` 字段到底归谁？为什么协议演进会让这个字段反复横跳？
4. 为什么 LLM provider 的 function calling 协议看起来像 OpenAPI？

---

## 1. 一句话定义 + 直觉类比

| 概念 | 是什么 | 解决什么问题 |
|---|---|---|
| **JSON** | 一种**数据格式**（文本规范） | 让数据能在网络/磁盘上**传输或存储** |
| **JSON Schema** | 一种**描述 JSON 数据形状**的协议（本身**也是 JSON**） | 让你能**校验**一份 JSON 数据"长得对不对" |
| **OpenAPI** | 一种**描述 REST API**的协议（也是 JSON 或 YAML） | 让你能**完整定义一个 HTTP 服务** —— 有哪些 endpoint、参数、响应等 |

### 类比 1：程序员熟悉的对照

```
JSON         ←→  Python dict / 一个 .csv 文件          只是数据
JSON Schema  ←→  Python 类型注解 / TypeScript interface 数据的"形状定义"
OpenAPI      ←→  Swagger UI / 完整 API 文档             带 endpoint 的完整规范
```

### 类比 2：建筑

- **JSON** = 一砖一瓦（原材料）
- **JSON Schema** = 房间的图纸（描述空间形状）
- **OpenAPI** = 整栋建筑的施工图（图纸 + 房间布局 + 出入口 + 水电）

---

## 2. JSON 本身

```json
{"name": "Beijing", "temp": 25.0}
```

**就这。** 一个文本格式，定义了 6 种值类型：
- `string` / `number` / `boolean` / `null` / `array` / `object`

**JSON 完全不关心**：
- 这个对象**应该**有哪些字段
- name **必须**是字符串还是数字
- temp **可不可以**是 null

它只是个"数据载体"。一份合法 JSON **不一定有意义** —— `{"x": 1}` 和 `{"name": "Beijing", "temp": 25.0}` 都是合法 JSON，但它们能不能被某个 API 接受？JSON 自己不告诉你。

> 💡 **JSON 本身没有 `nullable` 概念**。它只有 `null` **值**，不存在描述"这字段可以为 null"的语法。

---

## 3. JSON Schema：描述 JSON 形状的协议

要校验"这份 JSON 是不是合法的城市天气数据"，需要一份**形状规格**。这就是 JSON Schema：

```json
{
  "$schema": "https://json-schema.org/draft-07/schema#",
  "type": "object",
  "properties": {
    "name": {"type": "string"},
    "temp": {"type": ["number", "null"]}
  },
  "required": ["name"]
}
```

**注意**：JSON Schema 本身**也是用 JSON 写的** —— "用 JSON 描述 JSON"。

### 用它做什么

```python
import jsonschema

data1 = {"name": "Beijing", "temp": 25.0}
data2 = {"name": "Beijing", "temp": None}      # null 在数据里
data3 = {"temp": 25.0}                          # 缺 name

jsonschema.validate(data1, schema)   # ✅ 通过
jsonschema.validate(data2, schema)   # ✅ 通过（temp 允许 null）
jsonschema.validate(data3, schema)   # ❌ 抛错：'name' is a required property
```

### JSON Schema 怎么表达"可空"？

**只有一种官方写法**：把 `type` 写成数组，包含 `"null"`：

```json
{"type": ["string", "null"]}      // 必须传，但值可以是 null
```

> 💡 ⚠️ **JSON Schema 任何版本（draft 4 / 6 / 7 / 2019-09 / 2020-12）都没有 `nullable` 关键字**。

### JSON Schema vs TypeScript 类型

| TypeScript | JSON Schema |
|---|---|
| `interface User { name: string; age?: number; }` | `{type: "object", properties: {...}, required: ["name"]}` |
| `name: string \| null` | `{type: ["string", "null"]}` |
| 编译期检查 | 运行时 / 工具校验 |

---

## 4. OpenAPI：描述 HTTP API 的协议

JSON Schema 只描述**单份数据**的形状。一个完整的 HTTP API 还有更多东西要描述：
- 有哪些 URL endpoint？（`GET /weather` vs `POST /users`）
- 每个 endpoint 接受什么参数？
- 返回什么状态码？每个状态码对应什么响应？
- 需要什么认证？
- 错误格式？

**OpenAPI** 就是为这个目的而生的协议，**内部使用 JSON Schema 来描述参数和响应的形状**：

```yaml
# OpenAPI 文档（部分）
openapi: 3.0.3
paths:
  /weather:
    get:
      parameters:
        - name: city
          in: query
          required: true
          schema:                        # ← 这里就是 JSON Schema
            type: string
      responses:
        '200':
          content:
            application/json:
              schema:                    # ← 这里也是 JSON Schema
                type: object
                properties:
                  name: {type: string}
                  temp: {type: number, nullable: true}    # ← OpenAPI 3.0 字段
                required: [name]
```

注意 `schema:` 节点下面的部分 —— **结构是 JSON Schema 的，但允许加 OpenAPI 的扩展字段**。

### OpenAPI 是 JSON Schema 的"超集"

```
┌────────────────────────────────────────────┐
│ OpenAPI                                     │
│  ┌──────────────────────────────────────┐  │
│  │ 路径 / endpoint / 参数位置 / 认证 ... │  │
│  │  ┌─────────────────────────────┐    │  │
│  │  │  JSON Schema（+ 扩展）       │    │  │
│  │  │  描述参数 / 响应的数据形状    │    │  │
│  │  │  ┌─────────────────────┐    │    │  │
│  │  │  │  JSON               │    │    │  │
│  │  │  │  实际数据载体        │    │    │  │
│  │  │  └─────────────────────┘    │    │  │
│  │  └─────────────────────────────┘    │  │
│  └──────────────────────────────────────┘  │
└────────────────────────────────────────────┘
```

**OpenAPI 不重新发明"数据形状描述"的轮子，直接复用 JSON Schema**。但它**可以扩展** —— 引入一些 JSON Schema 没有的字段，比如 `nullable`、`example`、`discriminator`。

---

## 5. ⭐ `nullable` 的历史 —— 谁发明的、为什么、为什么后来又弃用

这是回答用户最初问题的关键。

### 时间线

| 时间 | 协议 | 怎么表达"可空" | nullable 字段？ |
|---|---|---|---|
| 一直以来 | JSON Schema（任何版本） | `"type": ["string", "null"]`（type 数组） | ❌ **从来没有** |
| 2017 | **OpenAPI 3.0** | 引入 `"nullable": true` **单独字段** | ✅ **OpenAPI 3.0 发明** |
| 2021+ | OpenAPI 3.1 | 跟 JSON Schema 对齐，回到 type 数组 | ⚠️ **已弃用** |
| 现在 | smolagents | OpenAPI 3.0 风格的 `"nullable": True` | ✅ 用着 |

### 为什么 OpenAPI 3.0 要发明 `nullable`？

**OpenAPI 3.0 用的是 JSON Schema 的一个子集**（不允许 type 是数组）。也就是说：

```json
{"type": ["string", "null"]}    ❌ 在 OpenAPI 3.0 里不合法（type 必须是单个字符串）
```

但又确实需要表达"可空"，于是 OpenAPI 3.0 团队**新增了一个 `nullable` 字段**：

```json
{"type": "string", "nullable": true}    ✅ OpenAPI 3.0 风格
```

### 为什么 OpenAPI 3.1 又弃用了？

OpenAPI 3.1 决定**完全对齐 JSON Schema**（不再做子集限制），所以可以直接用 type 数组了：

```json
{"type": ["string", "null"]}    ✅ OpenAPI 3.1 + JSON Schema 通用
```

`nullable` 字段就成了"历史包袱"，正式弃用。

### 结论：**`nullable` 是 OpenAPI 3.0 的发明，不是 JSON 的，也不是 JSON Schema 的**

**这就是为什么 [tool-input-nullable.md](../03-source/tool-input-nullable.md) 之前说"JSON Schema 标准"是不准确的** —— 严格说应该是"OpenAPI 3.0 字段（基于 JSON Schema 但加了扩展）"。

---

## 6. 三者关系图（带实际数据流）

```
JSON  ─────────  数据本身（一份具体的城市天气数据）
   ▲
   │ "我长成这样"
   │
JSON Schema ───  数据形状的描述（"城市天气数据应该有哪些字段、什么类型"）
   ▲
   │ "我用它来定义参数 / 响应的形状（可加扩展字段）"
   │
OpenAPI ───────  完整 API 的描述（"我有哪些 endpoint、用什么参数、返回什么"）
```

简单说：
- **JSON Schema 是 OpenAPI 的一部分**（OpenAPI 内嵌 JSON Schema 并可扩展）
- **JSON Schema 不依赖 OpenAPI**（你可以单独用 JSON Schema 校验任何 JSON 数据）
- **JSON 是最底层的载体**（JSON Schema 和 OpenAPI 文件本身**都是用 JSON/YAML 写的**）

---

## 7. ⭐ 在 smolagents 里的体现

```python
# Tool 实例（一份描述工具的"数据"）
tool.inputs = {"city": {"type": "string", ...}}

           ↓ get_tool_json_schema(tool) (models.py:288)

# OpenAPI 风格的 function calling 描述
{
  "type": "function",
  "function": {
    "name": "get_temp",
    "parameters": {                      # ← 这里是 JSON Schema 风格
      "type": "object",
      "properties": {
        "unit": {
          "type": "string",
          "nullable": true               # ← 但加了 OpenAPI 3.0 的扩展字段
        }
      },
      "required": ["city"]
    }
  }
}

           ↓ HTTP 请求

POST https://api.openai.com/v1/chat/completions
Body: {
  "messages": [...],
  "tools": [<上面的 OpenAPI 风格对象>]
}
```

> 💡 OpenAI / Anthropic 的 function calling 协议**就是 OpenAPI 3.0 风格**，因为它本来就是用来描述 API 的协议 —— 工具调用本质上跟 "调一个 HTTP API" 是同一回事。

---

## 8. 谁会让你混淆 —— 4 个常见说法的真伪

| 说法 | 严格说对吗？|
|---|---|
| "JSON 有 null 类型" | ✅ 对（`null` 是 JSON 6 种值类型之一）|
| "JSON 有 nullable 字段" | ❌ 错（JSON 只是数据格式，不存在描述字段属性的语法）|
| "JSON Schema 有 nullable 字段" | ❌ 错（任何版本都没有，只有 type 数组）|
| "OpenAPI 有 nullable 字段" | ⚠️ 半对 —— OpenAPI **3.0** 有，**3.1+ 已弃用** |
| "smolagents 用 JSON Schema 风格的 nullable" | ❌ 错 —— smolagents 用的是 **OpenAPI 3.0 风格**的 `"nullable": True` |

**这就是为什么不少博客 / Stack Overflow 答案讨论 `nullable` 时含糊不清** —— 协议演进太快，作者自己也没分清。

---

## 9. 总结表

| 问题 | 答案 |
|---|---|
| JSON 是协议吗？ | 是数据格式，不是描述协议 |
| JSON Schema 跟 JSON 啥关系？ | 用 JSON 描述 JSON 的形状（"用 JSON 写的 JSON 类型定义"）|
| OpenAPI 跟 JSON Schema 啥关系？ | OpenAPI 内嵌 JSON Schema 描述参数/响应，可加自己的扩展字段 |
| `nullable` 是谁的？ | **OpenAPI 3.0 的发明**（JSON Schema 任何版本都没有） |
| 为什么 OpenAPI 3.0 要发明 nullable？ | 因为 OpenAPI 3.0 是 JSON Schema 的子集，不让用 type 数组 |
| 为什么 OpenAPI 3.1 弃用了？ | 3.1 完全对齐 JSON Schema，可以直接用 type 数组了 |
| smolagents 用哪个风格？ | OpenAPI 3.0 风格（`"nullable": True` 单独字段）|
| LLM function calling 协议是哪个家族？ | OpenAPI 风格 —— 因为 tool calling 本质就是描述 API |

---

## 10. 自测题

```python
# 这段 schema 在哪个协议下合法？
schema_a = {"type": ["string", "null"]}                    # ?
schema_b = {"type": "string", "nullable": True}            # ?
schema_c = {"name": "Beijing"}                             # ?
```

<details>
<summary>答案</summary>

| schema | JSON | JSON Schema | OpenAPI 3.0 | OpenAPI 3.1 |
|---|---|---|---|---|
| schema_a | ⚠️ 看上下文 | ✅ 合法 | ❌ 不允许 type 数组 | ✅ 合法 |
| schema_b | ⚠️ 看上下文 | ⚠️ nullable 会被当作未知字段（合法但无效）| ✅ 标准用法 | ⚠️ 已弃用但仍然被多数实现支持 |
| schema_c | ✅ 是合法 JSON 数据 | ❌ 不是有效 schema（缺 type）| ❌ | ❌ |

**关键观察**：
- 同一个 `{...}` 字符串，在不同协议下"合法 / 不合法 / 是数据 / 是 schema" 完全不同
- **协议是上下文** —— 同一份 JSON 字面量，看你说它是数据还是 schema 才能判断是否合法

</details>

---

## 相关链接

- 相关笔记：
  - [tool-input-nullable.md](../03-source/tool-input-nullable.md) — smolagents 里 nullable 字段的具体用法
  - [tool-schema-rendering-mental-model.md](../03-source/tool-schema-rendering-mental-model.md) — Tool 渲染成 OpenAPI 风格 JSON 的过程
  - [model-and-protocols-overview.md](model-and-protocols-overview.md) — Chat Completion 协议（也是 OpenAPI 风格）
  - [05-advanced/llm-protocols-deep-dive.md](../05-advanced/llm-protocols-deep-dive.md) — `deferred`，协议家族深入对比
- 外部参考：
  - [JSON 官方网站](https://www.json.org/) — 数据格式规范
  - [JSON Schema 官方网站](https://json-schema.org/) — 数据形状描述协议
  - [OpenAPI Specification 3.1](https://spec.openapis.org/oas/v3.1.0) — REST API 描述协议
  - [OpenAPI 3.0 to 3.1 Changes](https://www.openapis.org/blog/2021/02/16/migrating-from-openapi-3-0-to-3-1-0) — nullable 弃用的官方说明

## 遗留问题

- [ ] OpenAPI 还有哪些扩展字段（`example` / `discriminator` / `readOnly` / `writeOnly`）—— 碰到再补
- [ ] JSON Schema 的 `oneOf` / `anyOf` / `allOf` 联合类型 —— smolagents [models.py:298](../../../src/smolagents/models.py#L298) 见过 anyOf，进阶话题
- [ ] Pydantic / FastAPI 跟这套协议的关系 —— 它们用 Python 类型生成 JSON Schema / OpenAPI

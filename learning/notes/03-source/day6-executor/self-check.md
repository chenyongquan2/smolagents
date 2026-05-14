---
created: 2026-05-14
status: active
tags: [smolagents, executor, sandbox, self-check, day6]
---

# Day 6 自查手册：9 道题 + 详细答案 + 笔记溯源

> 💡 **使用方式**（同 Day 3 / Day 4 / Day 5 self-check）：盖住答案心里答 → 揭开对照 → 答错点笔记溯源。
>
> **题目数量较少**（9 题 vs Day 5 的 14 题），因为 LEARNING_PLAN Day 6 是"浏览即可 / 层次 1"。

---

## Q1（★ 事实）：`LocalPythonExecutor` 跟 Python 内置 `exec()` 的本质差异是什么？

<details>
<summary>👀 看答案</summary>

`LocalPythonExecutor` **不直接调 `exec()`**，而是**自己实现 AST 解释器** —— 把代码 `ast.parse` 成 AST 树，逐个节点过 `evaluate_xxx` 函数：

| | 内置 `exec()` | LocalPythonExecutor |
|---|---|---|
| 执行机制 | Python 解释器直接跑 | AST 节点 → 自实现 evaluator → 检查 + 执行 |
| 安全控制点 | 只能限制 globals/builtins，仍能被 dunder 反射绕过 | 每个 AST 节点过自己的代码，**完全控制语义层面** |
| 维护成本 | 0 | 30+ 个 evaluator 要维护 |

**核心思想**：宁愿写 1700 行 AST 解释器，也不要交出整个 Python 解释器的权限。沙箱逃逸是 CTF 经典题目，`exec` + globals 限制**防不住**。

**溯源**：[00 §5 AST 解释器入门](00-sandbox-role-overview.md#5-ast-解释器入门为什么不直接-exec)

</details>

---

## Q2（★★ 概念）：默写 3 层防御机制（每层一句话 + 1 个例子）

<details>
<summary>👀 看答案</summary>

| 层 | 防什么 | 怎么实现 | 例子 |
|---|---|---|---|
| **层 1：白名单 import**（模块层）| 危险模块如 os/subprocess/sys | `BASE_BUILTIN_MODULES` + `DANGEROUS_MODULES` 黑名单 + `check_import_authorized` | `import os` → `InterpreterError("Forbidden access to module: os")` |
| **层 2：危险 builtins 拦截**（函数层）| exec/eval/compile/dunder 反射 | `nodunder_getattr` + `DANGEROUS_FUNCTIONS` + `check_safer_result` + `safer_eval` 装饰器 | `exec("...")` → `InterpreterError("Forbidden access to function: exec")` |
| **层 3：资源限制**（运行时层）| 死循环 / 耗时 / 输出爆 | `timeout` 装饰器 + `MAX_OPERATIONS` + `MAX_WHILE_ITERATIONS` + `DEFAULT_MAX_LEN_OUTPUT` | `while True: pass` → `ExecutionTimeoutError`（30 秒）|

**溯源**：[00 §3 ⭐⭐ 3 层防御机制](00-sandbox-role-overview.md#3--3-层防御机制核心)

</details>

---

## Q3（★ 事实）：`BASE_BUILTIN_MODULES` 默认包含哪些模块？至少说 5 个

<details>
<summary>👀 看答案</summary>

11 个 stdlib：

```python
BASE_BUILTIN_MODULES = [
    "collections", "datetime", "itertools", "math",
    "queue", "random", "re", "stat", "statistics",
    "time", "unicodedata",
]
```

定义在 [utils.py:49](../../../../src/smolagents/utils.py#L49)。

**注意不包含**：os / sys / subprocess / io / socket / multiprocessing / pathlib / shutil / pty —— 这些在 [DANGEROUS_MODULES](../../../../src/smolagents/local_python_executor.py#L130) 显式黑名单。

**用户追加**：`CodeAgent(additional_authorized_imports=["pandas", "numpy"])`。

**溯源**：[00 §3 层 1 + §4 BASE_PYTHON_TOOLS](00-sandbox-role-overview.md#3--3-层防御机制核心)

</details>

---

## Q4（★★ 概念）：解释为什么沙箱内的 `print` 是假货？真正的 print 输出去哪了？

<details>
<summary>👀 看答案</summary>

**为什么是假货**：沙箱不暴露完整 Python builtins，[`BASE_PYTHON_TOOLS["print"] = custom_print`](../../../../src/smolagents/local_python_executor.py#L74)，而 `custom_print` 返回 None 不输出到 stdout。

**真正的 print 输出去哪**：

```python
state["_print_outputs"] = PrintContainer()   # 第 2 幕初始化
```

沙箱内代码调 `print(x)` 时，`custom_print` 把 x 写到 `state["_print_outputs"]`（一个特殊容器）。

**最终成为 `CodeOutput.logs`**（[LocalPythonExecutor.__call__:1757](../../../../src/smolagents/local_python_executor.py#L1757)）：

```python
logs = str(self.state["_print_outputs"])
return CodeOutput(output=..., logs=logs, ...)
```

—— 这就是 Day 5 02 第 4 幕末 `code_output.logs` 的来源。

**为什么这么设计**：让 agent 框架能"知道沙箱里发生了什么"（用于 observation 拼接 / debug），同时避免污染主进程 stdout。

**溯源**：[00 §3 层 2 + §4](00-sandbox-role-overview.md#3--3-层防御机制核心) + [01 第 2 幕](01-evaluate-python-code-walkthrough.md#4-第-2-幕--初始化执行环境)

</details>

---

## Q5（★★★ 设计意图）：`FinalAnswerException` 为什么用异常而不用普通返回值来传递 final_answer 的结果？

<details>
<summary>👀 看答案</summary>

LLM 可能写出这种代码（错误但常见）：

```python
temps = [...]
max_temp = max(temps)
final_answer(86.0)
print("now let me also try ...")
some_more_code()
```

如果 `final_answer` 只是普通返回值，**后面的 print / some_more_code 还会跑** —— 浪费资源 + 可能产生副作用 + 最终拿到的可能不是 86.0 而是后面代码的返回值。

用 **`raise FinalAnswerException`** 强制中断：异常爆出后所有后续代码**根本不跑** → 立刻跳到 [evaluate_python_code 第 5 幕的 except](../../../../src/smolagents/local_python_executor.py#L1649) → 返回 final_answer 的值 + `is_final_answer=True`。

**继承 `BaseException` 而非 `Exception` 的细节**（[code:1572](../../../../src/smolagents/local_python_executor.py#L1572)）：让 LLM 写的 `try: ... except Exception:` **抓不到** —— 保证 final_answer 的中断**穿透所有用户 try-except**。

**溯源**：[01 第 3 幕 + 子幕 4.3](01-evaluate-python-code-walkthrough.md#5-第-3-幕--包装-final_answercode1630-1636)

</details>

---

## Q6（★★ 概念）：`static_tools` 和 `custom_tools` 有什么差异？

<details>
<summary>👀 看答案</summary>

| | static_tools | custom_tools |
|---|---|---|
| 内容 | 注册工具（CodeAgent 传入）+ `BASE_PYTHON_TOOLS`（白名单 builtins）| 用户在沙箱内自己 `def` 的函数 |
| 在沙箱内能否被覆盖 | ❌ **不能**（任何 `xxx = ...` 试图覆盖 static_tools key 会 raise）| ✅ 能（用户 def 同名函数会覆盖）|
| 实际场景 | `get_temperature` / `final_answer` / `max` / `print` | LLM 写代码时 `def helper(...): ...` |

**为什么 static_tools 不能被覆盖**：防止 LLM 写 `final_answer = lambda x: print("hack")` 把内置功能改掉。

[evaluate_python_code](../../../../src/smolagents/local_python_executor.py#L1583) docstring：
> These tools cannot be overwritten in the code: any assignment to their name will raise an error.

**溯源**：[01 §2 老沙桌上有什么](01-evaluate-python-code-walkthrough.md#2-老沙桌上有什么入参-4-件)

</details>

---

## Q7（★★★ 设计意图）：`PythonExecutor` 抽象类存在的意义是什么？为什么不直接用 `LocalPythonExecutor`？

<details>
<summary>👀 看答案</summary>

`PythonExecutor` 是抽象基类，定义 3 个抽象方法：

```python
class PythonExecutor(ABC):
    @abstractmethod
    def send_tools(self, tools): ...
    @abstractmethod
    def send_variables(self, variables): ...
    @abstractmethod
    def __call__(self, code_action) -> CodeOutput: ...
```

**为什么需要这层抽象**：让 **远程 executor**（E2B / Docker / Modal / Wasm / Blaxel）和 LocalPythonExecutor **统一接口** —— 用户切换 `executor_type="e2b"` 时，CodeAgent 内部代码完全不用改：

```python
code_output = self.python_executor(code_action)   # ← 不管哪种 executor，调用方式一样
```

**远程 executor 的核心差异**：代码被序列化送到远程进程 / 容器 / WebAssembly 跑 —— **更隔离**（哪怕沙箱被攻破，攻击者也只拿到临时容器）。

**这是统一抽象层的又一个案例**（呼应 Day 2 [Tool 类](../day2-tools/tool-class-role-overview.md) + Day 5 [tools-are-python-callables](../../02-concepts/tools-are-python-callables.md)）—— smolagents 处处用同一招：定义抽象接口 → 多个实现共存 → 上层代码无感知地切换。

**溯源**：[00 §6 类结构概览](00-sandbox-role-overview.md#6-类结构概览)

</details>

---

## Q8（★★★ 设计意图）：LocalPythonExecutor 不是 100% 安全，列举至少 2 个具体风险点

<details>
<summary>👀 看答案</summary>

✅ 阻止得了：
- `import os` / `subprocess`（层 1 白名单）
- `exec` / `eval` / `compile`（层 2 黑名单）
- 死循环（层 3 timeout）
- dunder 反射 `__class__.__base__.__subclasses__()`（`nodunder_getattr`）

⚠️ 阻止不了 / 风险点：

1. **白名单库本身有漏洞**：`pandas` / `numpy` 某些版本能读文件 / 网络 IO，沙箱无法预防（白名单内的都是"信任"的）
2. **内存爆炸**：`[1] * 10**9` 这种没死循环但耗光内存
3. **用户传 `additional_authorized_imports=["*"]`**：通配符允许所有 import → 层 1 失效 → 等于关沙箱
4. **同进程内存共享**：LocalPythonExecutor 跟主进程共享地址空间 —— 沙箱代码 segfault 主进程也跟着死
5. **DoS 风格攻击**：超出 timeout 一点 + 不停消耗 CPU 但不死循环

**生产严格隔离**：用 E2BExecutor / DockerExecutor 把代码丢到远程独立进程 / 容器，限制 CPU/内存/网络。**LocalPythonExecutor 适用于学习 / 原型 / 信任自己 prompt**。

**溯源**：[00 §8 沙箱不是 100% 安全](00-sandbox-role-overview.md#8-沙箱不是-100-安全局限性诚实标记)

</details>

---

## Q9（★★★★ 跨层闭环）：用我们的例子代码追踪 `final_answer(max_temp * 1.8 + 32)` 怎么变成 `CodeOutput(output=86.0, is_final_answer=True)` 的完整路径

代码：
```python
temps = [get_temperature("Beijing"), get_temperature("Tokyo"), get_temperature("Singapore")]
max_temp = max(temps)
final_answer(max_temp * 1.8 + 32)
```

<details>
<summary>👀 看答案</summary>

```
第 1 幕  ast.parse(code)
         → expression.body = [Assign1, Assign2, Expr]

第 2 幕  state["_print_outputs"] = PrintContainer()
         state["_operations_count"] = {"counter": 0}

第 3 幕  static_tools["final_answer"] 被替换为：
         def final_answer(*args): raise FinalAnswerException(原final_answer(*args))

第 4 幕  for node in expression.body:
  ├─ Assign1: temps = [...]
  │    evaluate_assign → evaluate_call × 3
  │    state["temps"] = [25.0, 30.0, 28.0]
  │
  ├─ Assign2: max_temp = max(temps)
  │    evaluate_assign → evaluate_call("max", [evaluate_name("temps")])
  │    state["max_temp"] = 30.0
  │
  └─ Expr: final_answer(max_temp * 1.8 + 32)
       evaluate_call:
         ├─ 解析参数：
         │   BinOp(BinOp(max_temp * 1.8) + 32)
         │   evaluate_binop: 30.0 * 1.8 = 54.0
         │   evaluate_binop: 54.0 + 32 = 86.0
         ├─ 查名："final_answer" 在 static_tools 里？✅（第 3 幕的包装版）
         └─ 调用 static_tools["final_answer"](86.0)
              ↓
              raise FinalAnswerException(86.0)   ← ⭐ 异常爆发

第 5 幕  捕获：
         except FinalAnswerException as e:
             return e.value, True
             #        ↑ 86.0   ↑ is_final_answer=True

LocalPythonExecutor.__call__:
  logs = str(state["_print_outputs"])    # ""（没 print 任何东西）
  return CodeOutput(output=86.0, logs="", is_final_answer=True)
```

**这就是 Day 5 02 第 4 幕末 `code_output` 拿到的对象**。

**溯源**：[01 §6 第 4 幕 + §7 第 5 幕](01-evaluate-python-code-walkthrough.md#6-第-4-幕--遍历-ast-节点逐个-evaluate核心戏code1639-1648)

</details>

---

## 自检评分

- ✅ **7-9 题答对** = Day 6 浏览到位，可以推 Day 7 综合总结
- ⚠️ **5-6 题答对** = 重读 00 §3（3 层防御）+ 01 §6（第 4 幕核心）
- 🆘 **< 5 题答对** = 重读 00 全文 + 跟 Day 5 02 第 4 幕对照看

---

## 关联阅读

- 上游 [00 sandbox-role-overview](00-sandbox-role-overview.md)
- 上游 [01 evaluate-python-code-walkthrough](01-evaluate-python-code-walkthrough.md)
- 同源剧本 [Day 5 02 第 4 幕](../day5-step-stream/02-codeagent-walkthrough.md)
- 概念 [Week 1 codeagent-how-it-works Q3+Q4](../../02-concepts/codeagent-how-it-works.md)
- 下游 Day 7 综合 —— 调用链全图 + Week 2 总结

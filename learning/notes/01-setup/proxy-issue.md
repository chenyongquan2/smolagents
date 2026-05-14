---
created: 2026-05-01
status: done
tags: [setup, network, proxy, troubleshooting]
---

# 国内访问 HuggingFace 的代理踩坑记录

> 本文回答：**浏览器能上 HF，为什么 Python 跑 smolagents 报 "WinError 10061 目标计算机积极拒绝"？**

---

## 现象

```python
agent.run("...")
```

报错：

```
httpcore.ConnectError: [WinError 10061] 由于目标计算机积极拒绝，无法连接。
```

而**浏览器**打开 https://huggingface.co/ 完全正常。

---

## 排查过程

### 第 1 步：确认网络状况

```bash
curl -s -o /dev/null -w "%{http_code} %{time_total}s\n" https://huggingface.co
# → 000 5.0s    （直连超时）

curl -s -o /dev/null -w "%{http_code} %{time_total}s\n" https://api.deepseek.com
# → 401 0.26s   （直连秒通，401 是没带 key 正常报错）
```

> 💡 **结论**：不是网络全坏，是 huggingface.co 在国内被墙。DeepSeek 等国内 API 直连完全 OK。

### 第 2 步：找浏览器走的代理端口

浏览器走 **Windows 系统代理**。Python 默认**不读**系统代理设置（这是 httpx/requests 的标准行为）。

```powershell
# PowerShell 查注册表
Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings'
```

输出：
```
ProxyEnable   = 1
ProxyServer   = 127.0.0.1:7897   ← 真正的代理端口
AutoConfigURL =
```

> ⚠️ **不要假设端口**：v2rayN 默认 10809，Clash for Windows 默认 7890，Clash Verge 默认 7897。**用注册表查实际值最稳**。

### 第 3 步：验证代理能用

```bash
curl -s -x http://127.0.0.1:7897 -o /dev/null -w "%{http_code} %{time_total}s\n" https://huggingface.co
# → 200 0.28s   ✅
```

### 第 4 步：让 Python 走这个代理

`httpx`/`requests` 都会读 `HTTPS_PROXY` / `HTTP_PROXY` 环境变量。把代理写到 `.env`：

```bash
HTTPS_PROXY=http://127.0.0.1:7897
HTTP_PROXY=http://127.0.0.1:7897
```

然后**确保 `load_dotenv()` 在 import 网络相关库之前调用**：

```python
from dotenv import load_dotenv
load_dotenv()   # ⭐ 必须在 from smolagents import ... 之前

from smolagents import CodeAgent, ...
```

实际上 smolagents 内部的 `httpx` 客户端是 lazy 创建的，所以 `load_dotenv()` 只要在 `agent.run()` 之前调用就行。但**最安全的做法是放在所有 import 之前**。

---

## 关键认知

### 1. 浏览器和 Python 用的是两套代理机制

| 工具 | 代理来源 |
|------|----------|
| Chrome/Edge/Firefox | Windows 系统代理（注册表） |
| `httpx` / `requests` | 环境变量 `HTTPS_PROXY` / `HTTP_PROXY` |
| `urllib` (Python 标准库) | 环境变量（同上） |
| `git` | `git config http.proxy` 单独设置 |
| Node.js (npm) | 环境变量 + `~/.npmrc` |

> 💡 **推论**：解决一处代理问题不代表全部 OK。每装新工具/语言，都要确认它怎么读代理。

### 2. "目标计算机积极拒绝" 的真正含义

`WinError 10061` 不是"被墙"，是**有东西主动 RST 连接**。常见原因：

- 你**配了**代理（环境变量或脚本里），但代理软件**没启动**（端口没监听）
- 配的端口不对（Clash 在 7897，但你写了 10809）

> 💡 跟 timeout（"我喊半天没人理"）不同，refused 是"对方说不"。先排查本地是不是配错了，再考虑外部网络。

### 3. 为什么不直接用 Windows 系统代理？

Python 历史上没有跨平台读"系统代理"的标准 API。第三方库（`pypac`、`urllib.request.ProxyHandler`）能做但都不完美。

业界惯例就是认环境变量，简单粗暴。**学习阶段不要折腾这个**，`.env` 写一下完事。

### 4. ⚠️ 代理软件可能只暴露 SOCKS5 没暴露 HTTP 代理

不同代理软件默认暴露的协议不同：

| 代理软件 | 默认 HTTP 代理 | 默认 SOCKS5 |
|---|---|---|
| Clash for Windows / Verge | ✅ 7890 / 7897 | ✅ 7891 |
| v2rayN | ✅ 10809 | ✅ 10808 |
| **ToLine** | ❌ 默认不暴露 | ✅ 2801 |
| Trojan-Qt5 | 看版本 | ✅ 1080 |

**结论**：不能假设代理软件一定提供 HTTP 代理端口。**用 `netstat -ano \| findstr 127.0.0.1 \| findstr LISTENING` 看实际监听**。

#### 如果你的代理软件只有 SOCKS5

`httpx` / `requests` 默认**不支持 SOCKS5**（要加包），配置流程：

```bash
# 1. 装 SOCKS 支持
C:/workspace/smolagents/.venv/Scripts/pip install "httpx[socks]"
```

```bash
# 2. .env 用 socks5:// 前缀
HTTPS_PROXY=socks5://127.0.0.1:2801
HTTP_PROXY=socks5://127.0.0.1:2801
```

```bash
# 3. 验证（curl 原生支持 socks5）
curl -sS -x socks5://127.0.0.1:2801 https://huggingface.co -o /dev/null -w "%{http_code} %{time_total}s\n"
# → 200 3.1s ✅
```

```bash
# 4. 重启 VS Code 调试 session 让新 .env 生效（.env 不会热加载）
```

> 💡 **判别 HTTP 还是 SOCKS5 的快速法**：用 curl `-x http://...:PORT` 测，如果返回 `curl: (56) CONNECT tunnel failed, response 404` 那个端口就**不是 HTTP 代理**（很可能是 SOCKS5，或者根本不是代理）—— 换成 `-x socks5://...:PORT` 再试。

---

## 当前配置（已固化）

`C:\workspace\smolagents\.env`：

```bash
# 当前用 ToLine（只暴露 SOCKS5 端口 2801）
HTTPS_PROXY=socks5://127.0.0.1:2801
HTTP_PROXY=socks5://127.0.0.1:2801
HF_TOKEN=hf_xxxxxxxxxxxxx

# 历史配置（Clash for Windows / Verge HTTP 代理 7897）
# HTTPS_PROXY=http://127.0.0.1:7897
# HTTP_PROXY=http://127.0.0.1:7897
```

**已装的额外依赖**：
- `httpx[socks]` (引入 `socksio` 1.0.0)  ← SOCKS5 支持

---

## 长期方案（如果代理不稳）

学习阶段嫌代理麻烦，可以换成**国内直连的 LLM**：

```python
# DeepSeek（国内秒连，便宜）
import os
from smolagents import OpenAIModel

model = OpenAIModel(
    model_id="deepseek-chat",
    api_base="https://api.deepseek.com/v1",
    api_key=os.environ["DEEPSEEK_API_KEY"],
)
```

去 https://platform.deepseek.com/api_keys 申请 key，充 1-10 元够学很久。

但 HF Hub 上的某些**工具**（pull tool from hub、上传 agent）还是要走代理，所以代理别完全停掉。

---

## 相关链接

- [how-to-run.md](how-to-run.md) — 项目运行
- [vscode-debugging.md](vscode-debugging.md) — 调试
- [httpx 关于代理的官方说明](https://www.python-httpx.org/environment_variables/#httpx_proxy)

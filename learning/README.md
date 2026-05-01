# learning/ — 个人学习目录

> 这个目录是**我学习 smolagents 的所有个人内容**：计划、笔记、练习脚本。
> 与上游官方代码（`../src/`、`../examples/`、`../docs/` 等）严格隔离。

## 目录结构

```
learning/
├── README.md                ← 你在这里
├── LEARNING_PLAN.md         ← 4 周学习计划（顶层入口）
├── .env.example             ← 环境变量模板（实际 .env 在项目根目录）
├── scripts/                 ← 自己写的练习脚本
│   ├── my_first_agent.py    ← 第一个 agent demo
│   └── compare_agents.py    ← CodeAgent vs ToolCallingAgent 对比
└── notes/                   ← 学习笔记（详见 notes/README.md）
    ├── README.md            ← 笔记索引 + 写作规范
    ├── _template.md         ← 新笔记模板
    ├── questions.md         ← 问题清单
    ├── 01-setup/
    ├── 02-concepts/
    ├── 03-source/
    ├── 04-experiments/
    └── 05-advanced/
```

## 入口指引

刚来？按这个顺序：

1. **[LEARNING_PLAN.md](LEARNING_PLAN.md)** — 看整体 4 周计划
2. **[notes/01-setup/how-to-run.md](notes/01-setup/how-to-run.md)** — 怎么把项目跑起来
3. **[notes/01-setup/vscode-debugging.md](notes/01-setup/vscode-debugging.md)** — 怎么单步调试
4. **[notes/README.md](notes/README.md)** — 笔记索引 + 笔记管理最佳实践

## 跑脚本的方式

在**项目根目录** `C:\workspace\smolagents\` 下执行：

```bash
.venv/Scripts/python.exe learning/scripts/my_first_agent.py
.venv/Scripts/python.exe learning/scripts/compare_agents.py
```

> 脚本通过 `find_dotenv()` 自动定位项目根目录的 `.env`，不用担心 cwd 问题。

## 与上游代码的关系

| 类型 | 位置 | git 行为 |
|------|------|---------|
| 上游官方代码 | `../src/`, `../examples/`, `../docs/` 等 | 跟随 `main` 分支同步 upstream |
| 个人学习内容 | `learning/`（本目录） | 在 `personal-study` 分支提交，不污染 main |
| 本机配置 | `../.env`, `../.vscode/`, `../.claude/` | 已在 `.gitignore`，不提交 |

> 如果将来要从上游拉新版：`git checkout main && git pull upstream main`，本目录完全不受影响。

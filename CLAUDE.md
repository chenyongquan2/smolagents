# CLAUDE.md

Personal learning fork of HuggingFace smolagents. Current focus: studying the codebase to learn AI agent fundamentals. See `learning/LEARNING_PLAN.md` for the 4-week plan and current progress.

## Branch & upstream hygiene

- **Active branch**: `personal-study`. Never commit learning artifacts to `main` — `main` must stay clean for clean diffs against upstream `huggingface/smolagents`.
- **Don't modify upstream files** unless I explicitly ask. Upstream-owned paths:
  - `src/` `tests/` `docs/` `examples/`
  - `pyproject.toml` `Makefile` `e2b.toml` `README.md` `AGENTS.md` `CODE_OF_CONDUCT.md` `CONTRIBUTING.md` `LICENSE` `SECURITY.md`
- **All my work goes under `learning/`**. If a task seems to require touching upstream files, ask first — I'd rather find a workaround under `learning/`.

## Where things live

```
learning/
├── LEARNING_PLAN.md     ← 4-week plan + per-day progress checkboxes + weekly summaries
├── notes/
│   ├── README.md        ← notes index + writing conventions (read this before adding a note)
│   ├── 01-setup/        ← env / debugging / proxy
│   ├── 02-concepts/     ← Week 1 conceptual notes
│   ├── 03-source/       ← Week 2 source-reading notes (current focus)
│   └── 05-advanced/     ← deferred topics
└── scripts/             ← runnable demos that accompany notes
```

## Notes conventions (enforced)

- For any new class / module / non-trivial mechanism, write `*-role-overview.md` (or `*-mental-model.md` for concepts) **before** the implementation note. This is governed by the teaching constitution — see `~/.claude/projects/C--workspace-smolagents/memory/feedback_teaching_style.md` (auto-loaded each session).
- Implementation notes must start with a ⚠️ **必读前置** link to the corresponding overview.
- When adding a new note, **also update `learning/notes/README.md` index** (overview entries listed before implementation entries).
- Filename convention: lowercase + hyphens, no spaces, no Chinese in filenames.
- Frontmatter required (see `learning/notes/_template.md`).

## Demo script conventions (`learning/scripts/`)

- **Encoding fix is mandatory** — Windows console defaults to GBK and will UnicodeEncodeError on emoji. Top of every script:
  ```python
  import sys
  if hasattr(sys.stdout, "reconfigure"):
      sys.stdout.reconfigure(encoding="utf-8")
  ```
- Run with the project venv: `C:/workspace/smolagents/.venv/Scripts/python.exe learning/scripts/<name>.py`
- For network-dependent scripts (HF / OpenAI), env vars must come from `.env` (Clash 7897). See `~/.claude/.../memory/env_network_setup.md`.

## Communication

- Default to **中文** responses.
- Teaching style follows the constitution in user memory (先讲用途/调用时机/角色，再讲实现). Don't dive into line-by-line source until the mental model is established.

## Don't

- Don't run `git commit` / `git push` proactively — wait for explicit ask.
- Don't add CLAUDE.md content that duplicates user memory or LEARNING_PLAN.md — link instead.
- Don't bypass the overview-first rule even for "small" topics. If unsure whether something needs an overview, default to writing one.

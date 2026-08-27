# memsearch — WorkBuddy Plugin

English | [简体中文](README.zh-CN.md)

[![CodeBuddy](https://img.shields.io/badge/CodeBuddy-plugin-00A1E0)](https://www.codebuddy.ai)
[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://pypi.org/project/memsearch/)
[![memsearch](https://img.shields.io/badge/powered%20by-memsearch-FF6900)](https://github.com/zilliztech/memsearch)
[![License](https://img.shields.io/badge/license-MIT-green)](https://github.com/zilliztech/memsearch/blob/main/LICENSE)

Give WorkBuddy a memory. Every finished turn gets summarized into a daily Markdown
journal and indexed into Milvus; every new question searches that history first, so
the agent remembers what you did last week without being told.

It is a thin hook layer around the
[memsearch](https://github.com/zilliztech/memsearch) Python package — the package
does the summarizing, embedding and indexing; the plugin just wires it into
WorkBuddy's lifecycle and never blocks your session (heavy work runs in the
background, hooks return in under a second).

## Install

**1. Install the memsearch package** into the Python that WorkBuddy will use:

```bash
pip install memsearch
```

**2. Configure it once** — pick a provider name you already defined under
`[llm.providers.<name>]` in `~/.memsearch/config.toml` and route the summarize
slot to it (WorkBuddy reuses the `openclaw` slot):

```bash
memsearch config set plugins.openclaw.summarize.provider <name>
memsearch config set plugins.openclaw.summarize.enabled true
```

WorkBuddy has no headless CLI, so `provider = native` will not work here — it must
be a real provider entry.

**3. Install the plugin** inside WorkBuddy: open **Experts ∙ Skills ∙ Connectors**,
go to **Skills** > **Plugins**, click **`+`** and enter
`KagaJiankui/memsearch-workbuddy`. Restart WorkBuddy once so the hook wiring is
picked up.

That's it. Talk to WorkBuddy for a turn or two.

## How to tell it's working

Three things to check, in order of how fast they show up:

1. **Right after a turn ends** — the project's `.memsearch/memory/YYYY-MM-DD.md`
   grows a `### HH:MM` entry with a bullet summary of what you just did.
2. **On your next question** (10+ characters) — the context gets a
   `[memsearch] 相关历史记忆` block with up to two past hits, or the
   `[memsearch] Memory available` marker when nothing matched.
3. **On a fresh session** — the status line shows the summarize route and a
   recent-memory preview.

## What each hook does

| Hook | What it does |
|------|--------------|
| `SessionStart` | Injects a preview of the most recent journals, kicks off a background index of the memory dir |
| `UserPromptSubmit` | Searches top-2 relevant memories for your prompt and injects them as context |
| `Stop` / `SubagentStop` | Summarizes the turn into the daily journal, indexes it, then runs due maintenance in the background |
| `PreCompact` | Passes through |

Failures degrade quietly: if the CLI, provider or search fails for any reason, the
hook falls back to a small marker line (or a written "summary unavailable" bullet in
the journal) — the session itself is never blocked.

## Memory maintenance (runs itself, one config line)

After indexing, due maintenance tasks (`project_review`, `user_profile`,
`memory_to_skill` skill distillation) run detached — once a day by default, never
during your turn. Route them to a provider that emits clean JSON:

```bash
memsearch config set plugins.openclaw.memory_to_skill.model Qwen/Qwen3.5-35B-A3B
```

Avoid DeepSeek-V3.2 for `memory_to_skill`: its function-call markup leaks into the
output as text and the JSON parse fails (the task retries next cycle, nothing breaks).

## Notes

- First search after indexing may find nothing for ~15 minutes — Zilliz Cloud
  serverless stats lag behind the actual data. It self-heals; later turns see the
  memory.
- Set `MEMSEARCH_DISABLE=1` to make every hook a no-op without uninstalling.
- Per-project memory lives in `<project>/.memsearch/` (append-only Markdown, plus
  index/maintenance bookkeeping). Delete the project folder to forget a project.

## Attribution

The prompt files in [`prompts/`](workbuddy/prompts/) are **copied verbatim** from
[zilliztech/memsearch](https://github.com/zilliztech/memsearch)'s
`plugins/_shared/prompts/`.

> memsearch is licensed under the MIT License. Copyright (c) Zilliz.

This repository is an independent WorkBuddy (CodeBuddy) plugin built on the memsearch
Python package; it is not affiliated with or endorsed by the upstream project.

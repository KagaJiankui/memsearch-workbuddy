# memsearch — WorkBuddy 插件

[English] | [简体中文](README.zh-CN.md)

[![CodeBuddy](https://img.shields.io/badge/CodeBuddy-plugin-00A1E0)](https://www.codebuddy.ai)
[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://pypi.org/project/memsearch/)
[![memsearch](https://img.shields.io/badge/powered%20by-memsearch-FF6900)](https://github.com/zilliztech/memsearch)
[![License](https://img.shields.io/badge/license-MIT-green)](https://github.com/zilliztech/memsearch/blob/main/LICENSE)

给 WorkBuddy 一个记忆。每轮对话结束都会被总结进当天的 Markdown 日记并索引进
Milvus；下次提问会先检索这段历史，上周做过什么，不用你开口它自己记得。

它是 [memsearch](https://github.com/zilliztech/memsearch) Python 包外面的一层薄
hook：总结、向量化、索引都由包来做，插件只负责把这一切接进 WorkBuddy 的生命周期，
并且绝不卡住你的会话——重活全部在后台跑，hook 秒回。

## 安装

**1. 装 memsearch 包**（装到 WorkBuddy 会用到的那个 Python 里）：

```bash
pip install memsearch
```

**2. 配置一次**——在 `~/.memsearch/config.toml` 里选一个你已经配好的
`[llm.providers.<name>]`，把 summarize 槽指过去（WorkBuddy 复用 `openclaw` 槽）：

```bash
memsearch config set plugins.openclaw.summarize.provider <name>
memsearch config set plugins.openclaw.summarize.enabled true
```

WorkBuddy 没有 headless CLI，`provider = native` 在这里行不通，必须填真实的
provider 条目。

**3. 在 WorkBuddy 里装插件**：打开 **"专家∙技能∙连接器"**，进 **技能** >
**套件**，点 **"+"**，输入 `KagaJiankui/memsearch-workbuddy` 确认。然后重启一次
WorkBuddy，让 hook 接线生效。

就这样。跟 WorkBuddy 聊一两轮试试。

## 怎么确认装好了

按出现速度从快到慢，检查三处：

1. **一轮对话刚结束**——项目的 `.memsearch/memory/YYYY-MM-DD.md` 里多出一条
   `### HH:MM`，附带你刚才所做的事的要点总结。
2. **下一次提问时**（10 个字符以上）——上下文里出现
   `[memsearch] 相关历史记忆` 块（最多两条命中），一条都没匹配到时则是
   `[memsearch] Memory available` 标记。
3. **新开会话时**——状态行显示 summarize 路由和最近记忆预览。

## 每个 hook 做什么

| Hook | 行为 |
|------|------|
| `SessionStart` | 注入最近日记预览，并后台增量索引记忆目录 |
| `UserPromptSubmit` | 按你的提问检索最相关的两条历史记忆注入上下文 |
| `Stop` / `SubagentStop` | 把本轮总结进当日日记并索引，随后在后台运行到期维护 |
| `PreCompact` | 直接放行 |

失败一律安静降级：CLI、provider 或搜索无论什么原因失败，hook 都会退回一条小
标记（或在日记里写入"summary unavailable"条目）——会话本身绝不会被卡住。

## 记忆维护（自动运行，只需一行配置）

索引完成后，到期维护任务（`project_review`、`user_profile`、`memory_to_skill`
技能蒸馏）会在后台执行——默认每天一次，绝不占用你的对话时间。给它们指一个能
输出干净 JSON 的模型：

```bash
memsearch config set plugins.openclaw.memory_to_skill.model Qwen/Qwen3.5-35B-A3B
```

`memory_to_skill` 别用 DeepSeek-V3.2：它的函数调用标记会以文本形式漏进输出，
JSON 解析直接失败（任务下个周期自动重试，不会坏数据）。

## 备注

- 索引完成后第一次搜索可能查不到东西，约 15 分钟——Zilliz Cloud serverless 的
  统计有滞后。会自愈，之后几轮就能看到记忆了。
- 设 `MEMSEARCH_DISABLE=1` 可以让所有 hook 空转，不用卸载插件。
- 每个项目的记忆在 `<项目>/.memsearch/` 里（只追加的 Markdown，加索引和维护
  记录）。删掉这个文件夹就是忘记这个项目。

## 出处

[`prompts/`](workbuddy/prompts/) 中的提示词文件**逐字复制**自
[zilliztech/memsearch](https://github.com/zilliztech/memsearch) 的
`plugins/_shared/prompts/`。

> memsearch 以 MIT 许可证发布。版权所有 (c) Zilliz。

本仓库是一个基于 memsearch Python 包的独立 WorkBuddy（CodeBuddy）插件，与上游
项目无隶属关系，也未获得其背书。

#!/usr/bin/env python3
# memsearch-diag hook — 捕获 WorkBuddy hook 的完整 stdin payload。
# 目的：钉死 memsearch 在 WorkBuddy 上为什么无法产出 .memsearch 文件。
#   1) transcript_path 传没传、指向什么格式（.jsonl 还是 .txt？）
#   2) 各 hook 事件的 stdin 字段都有哪些
#   3) 环境变量里 CODEBUDDY_PLUGIN_ROOT / CODEBUDDY_PROJECT_DIR / 是否兼容 CLAUDE_*
#
# 输出契约：必须向 stdout 打印一个合法 JSON（hook 主机要求），否则会被判超时。
# 诊断日志写在项目根或用户主目录下的 .memsearch-diag.log，与工作线程解耦。
# 全局开关与日志路径由同目录 diag-hook_conf.py 控制（ENABLED / LOG_PATH）。

import os
import sys
import json
import time
import importlib.util


def _load_conf():
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "diag-hook_conf.py")
    spec = importlib.util.spec_from_file_location("diag_hook_conf", p)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception:  # noqa
        return None
    return mod


_CONF = _load_conf()
CONF_ENABLED = bool(getattr(_CONF, "ENABLED", True))
CONF_LOG_PATH = str(getattr(_CONF, "LOG_PATH", "") or "").strip()

# 全局禁用：不读 stdin，直接回合法 JSON 退出（fail-open：conf 缺失/损坏时默认启用）。
if not CONF_ENABLED:
    sys.stdout.write('{"continue":true}')
    sys.stdout.flush()
    sys.exit(0)

# ---------------------------------------------------------------------------
# 1. 立即读完整 stdin（用 None 挂参 + 一次性 read，避免 json.load 因 EOF 卡住）。
#    顺带抓取环境变量快照。
# ---------------------------------------------------------------------------
RAW = ""
try:
    RAW = sys.stdin.read() or ""
except Exception as e:  # noqa
    RAW = f"<stdin.read failed: {e}>"

ENV_KEYS = [
    "CODEBUDDY_PLUGIN_ROOT",
    "CODEBUDDY_PROJECT_DIR",
    "CLAUDE_PLUGIN_ROOT",
    "CLAUDE_PROJECT_DIR",
    "MEMSEARCH_DIR",
    "MEMSEARCH_NO_WATCH",
    "MEMSEARCH_DISABLE",
    "HOME",
    "PWD",
]
ENV_SNAP = {k: os.environ.get(k, "") for k in ENV_KEYS}

# 解析 stdin 成 dict（失败则保留原始字符串，便于诊断）
PAYLOAD = None
try:
    PAYLOAD = json.loads(RAW) if RAW.strip() else {}
except Exception as e:  # noqa
    PAYLOAD = {"__parse_error__": str(e), "__raw_head__": RAW[:2000]}

HOOK_EVENT = (PAYLOAD or {}).get("hook_event_name") or os.environ.get("HOOK_EVENT_NAME", "unknown")


# ---------------------------------------------------------------------------
# 2. 立即给 hook 主机一个合法 JSON 回应（保证 hook 不被判超时）。
# ---------------------------------------------------------------------------
RESPONSE = {"continue": True}
if HOOK_EVENT in ("SessionStart", "UserPromptSubmit"):
    # 只在注入类事件给一段 tiny 上下文，其余事件保持空，避免干扰诊断
    RESPONSE = {
        "continue": True,
        "hookSpecificOutput": {
            "hookEventName": HOOK_EVENT,
            "additionalContext": "[memsearch-diag] probe registered.",
        },
    }
try:
    sys.stdout.write(json.dumps(RESPONSE))
    sys.stdout.flush()
except Exception:  # noqa
    sys.stdout.write('{"continue":true}')
    sys.stdout.flush()


# ---------------------------------------------------------------------------
# 3. 写诊断日志（在 stdout 已 flush 之后做，不阻塞 hook 响应）。
# ---------------------------------------------------------------------------
def first_bytes(path, n=60):
    try:
        with open(path, "rb") as f:
            return f.read(n)
    except Exception as e:  # noqa
        return f"<unreadable: {e}>"


def log_write():
    lines = []
    lines.append("=" * 80)
    lines.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] event={HOOK_EVENT}")
    lines.append("--- ENV ---")
    for k, v in ENV_SNAP.items():
        lines.append(f"  {k} = {v!r}")
    lines.append("--- STDIN (raw, head 2500) ---")
    lines.append((RAW or "<empty>")[:2500])
    ts = PAYLOAD.get("transcript_path") or ""
    lines.append("--- transcript_path ---")
    lines.append(f"  value = {ts!r}")
    if ts:
        lines.append(f"  exists = {os.path.isfile(ts)}")
        if os.path.isfile(ts):
            head = first_bytes(ts)
            lines.append(f"  first 60 bytes = {head!r}")
            lines.append(f"  suffix = {os.path.splitext(ts)[1]!r}")
    lines.append("")
    log_text = "\n".join(lines)

    # 候选日志路径（多个，至少一个可写）；conf 指定 LOG_PATH 时只用该路径
    candidates = []
    if CONF_LOG_PATH:
        candidates.append(CONF_LOG_PATH)
    else:
        if PAYLOAD.get("cwd"):
            candidates.append(os.path.join(PAYLOAD["cwd"], ".memsearch-diag.log"))
        pj = ENV_SNAP.get("CODEBUDDY_PROJECT_DIR") or ENV_SNAP.get("CLAUDE_PROJECT_DIR")
        if pj:
            candidates.append(os.path.join(pj, ".memsearch-diag.log"))
        candidates.append(os.path.join(os.path.expanduser("~"), ".memsearch-diag.log"))

    last_err = None
    for path in dict.fromkeys(candidates):  # 去重保序
        try:
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(log_text)
            last_err = None
            break
        except Exception as e:  # noqa
            last_err = f"{path}: {e}"
            continue
    if last_err:
        # 所有候选失败：fallback 到临时目录
        try:
            import tempfile
            with open(os.path.join(tempfile.gettempdir(), "memsearch-diag.log"), "a", encoding="utf-8") as f:
                f.write(log_text + f"\n[stderr fallback used: {last_err}]\n")
        except Exception:  # noqa
            pass


log_write()
sys.exit(0)

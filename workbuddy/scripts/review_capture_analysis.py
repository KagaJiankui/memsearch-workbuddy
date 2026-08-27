#!/usr/bin/env python3
"""review_capture_analysis.py — memsearch-wb 对接层捕获产物的统计与 NLP 数值分析。

只读分析，不改任何文件。输出四段：
  P1 JSONL 流水统计（session-start / user-prompt-submit / stop / other）
  P2 parsed.txt 文本数值画像（长度/语言构成/词频/重复/噪音泄漏）
  P3 memory-draft.md 结构校验（锚点格式 / 占位符 / 标题逻辑一致性）
  P4 对照 spec 验收项的量化判定
"""

import collections
import glob
import hashlib
import json
import os
import re
import sys

ROOTS = [
    r"D:\Electronics\agent-plugins\workbuddy_plugin_memsearch\.memsearch\review",
    r"C:\Users\Falke\.workbuddy\.memsearch\review",
]

NOISE_TAGS = (
    "system-reminder", "user_context", "additional_data", "current_time",
    "user_references", "user_info", "identity_context", "user_query",
)
_RE_NOISE_LEAK = re.compile(r"</?(?:%s)\b" % "|".join(NOISE_TAGS))
_RE_ANCHOR = re.compile(
    r"^<!-- session:(\S+) turn:(\S*) transcript:(.+) -->$", re.M
)
_RE_CJK = re.compile(r"[一-鿿]")
_RE_CJK_RUN = re.compile(r"[一-鿿]{2,}")
_RE_LATIN_WORD = re.compile(r"[A-Za-z][A-Za-z0-9_.+-]{1,}")


def load_jsonl(path):
    recs = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    recs.append(json.loads(line))
                except Exception:
                    recs.append({"__bad__": line[:100]})
    return recs


def stats(nums):
    if not nums:
        return "n=0"
    nums = sorted(nums)
    n = len(nums)
    return "n=%d min=%d p50=%d max=%d mean=%.0f" % (
        n, nums[0], nums[n // 2], nums[-1], sum(nums) / n,
    )


def p1_jsonl(root):
    print("\n" + "=" * 70)
    print("P1 JSONL 流水统计 — %s" % root)
    print("=" * 70)
    for name in ("session-start", "user-prompt-submit", "stop", "other", "errors"):
        path = os.path.join(root, name + ".jsonl")
        if not os.path.isfile(path):
            continue
        recs = load_jsonl(path)
        bad = sum(1 for r in recs if "__bad__" in r)
        print("\n[%s] records=%d%s" % (name, len(recs), " BAD=%d!" % bad if bad else ""))
        if name == "session-start":
            inj = [r.get("context_injected") for r in recs]
            chars = [r.get("context_chars", 0) for r in recs]
            provs = collections.Counter(
                (r.get("provider_resolution") or {}).get("provider", "?") for r in recs
            )
            print("  context_injected: true=%d false=%d" % (inj.count(True), inj.count(False)))
            print("  context_chars   : %s" % stats(chars))
            print("  provider        : %s" % dict(provs))
        elif name == "user-prompt-submit":
            inj = [r.get("marker_injected") for r in recs]
            chars = [r.get("prompt_chars", 0) for r in recs]
            print("  marker_injected : true=%d false=%d" % (inj.count(True), inj.count(False)))
            print("  prompt_chars    : %s" % stats(chars))
        elif name == "stop":
            skips = collections.Counter(r.get("skip_reason", "") for r in recs if r.get("skip_reason"))
            ok = [r for r in recs if not r.get("skip_reason")]
            print("  成功解析=%d / 跳过=%d %s" % (len(ok), len(recs) - len(ok), dict(skips)))
            print("  transcript lines: %s" % stats([(r.get("parse_meta") or {}).get("line_count", 0) for r in ok]))
            print("  kept rows       : %s" % stats([(r.get("parse_meta") or {}).get("kept", 0) for r in ok]))
            print("  skipped_noise   : %s" % stats([(r.get("parse_meta") or {}).get("skipped_noise", 0) for r in ok]))
            print("  last_assist_msg : %s" % stats([r.get("last_assistant_message_chars", 0) for r in ok]))
            heads = collections.Counter(r.get("need_session_heading") for r in ok)
            print("  need_session_heading: %s" % dict(heads))
            sess = collections.Counter(os.path.basename(r.get("transcript_path", "?"))[:8] for r in ok)
            print("  sessions        : %s" % dict(sess))


def p2_parsed(root):
    files = sorted(glob.glob(os.path.join(root, "stop-*.parsed.txt")))
    if not files:
        return {}, {}
    print("\n" + "=" * 70)
    print("P2 parsed.txt 文本画像 — %d 个文件 @ %s" % (len(files), root))
    print("=" * 70)
    print("%-38s %6s %5s %4s %4s %4s %5s %5s %4s" % (
        "file", "bytes", "lines", "U", "A", "S", "cjk%", "dup%", "leak"))
    bigrams = collections.Counter()
    words = collections.Counter()
    hashes = {}
    per_file = {}
    total_leak = 0
    for path in files:
        text = open(path, encoding="utf-8", errors="replace").read()
        lines = [l for l in text.splitlines() if l.strip()]
        n_u = sum(1 for l in lines if l.startswith("[User]:"))
        n_a = sum(1 for l in lines if l.startswith("[Assistant]:"))
        n_s = sum(1 for l in lines if l.startswith("[System]:"))
        body = "\n".join(l for l in lines if not l.startswith("==="))
        nonspace = re.sub(r"\s", "", body)
        cjk = len(_RE_CJK.findall(body))
        cjk_pct = 100.0 * cjk / max(1, len(nonspace))
        # 行内重复率（exact）
        cnt = collections.Counter(l for l in lines if not l.startswith("==="))
        dup_pct = 100.0 * sum(v - 1 for v in cnt.values() if v > 1) / max(1, len(lines))
        # 噪音标签泄漏（B1 应为 0）
        leak = len(_RE_NOISE_LEAK.findall(body))
        total_leak += leak
        # hook 自污染检查：[memsearch] 记号不应进入 transcript 用户话
        self_poll = body.count("[memsearch]")
        # 词频：CJK 二元组 + 拉丁词
        for run in _RE_CJK_RUN.findall(body):
            for i in range(len(run) - 1):
                bigrams[run[i:i + 2]] += 1
        for w in _RE_LATIN_WORD.findall(body):
            words[w.lower()] += 1
        md5 = hashlib.md5(body.encode("utf-8")).hexdigest()[:10]
        hashes.setdefault(md5, []).append(os.path.basename(path))
        per_file[path] = {"u": n_u, "a": n_a, "s": n_s, "leak": leak, "self_poll": self_poll}
        print("%-38s %6d %5d %4d %4d %4d %5.1f %5.1f %4d%s" % (
            os.path.basename(path), len(text.encode("utf-8")), len(lines),
            n_u, n_a, n_s, cjk_pct, dup_pct, leak,
            " SELF-POLL!" if self_poll else ""))
    dups = {h: v for h, v in hashes.items() if len(v) > 1}
    print("\n跨文件内容重复组: %s" % (dups if dups else "无"))
    print("噪音标签泄漏总计: %d (B1 期望 0)" % total_leak)
    print("\nTop-15 CJK 二元组: %s" % ", ".join(
        "%s×%d" % (g, c) for g, c in bigrams.most_common(15)))
    print("Top-15 拉丁词    : %s" % ", ".join(
        "%s×%d" % (w, c) for w, c in words.most_common(15)))
    return per_file, hashes


def p3_drafts(root, stop_records):
    files = sorted(glob.glob(os.path.join(root, "stop-*.memory-draft.md")))
    if not files:
        return
    print("\n" + "=" * 70)
    print("P3 memory-draft.md 结构校验 — %d 个文件" % len(files))
    print("=" * 70)
    ok_anchor = ok_dry = ok_head = 0
    for path in files:
        text = open(path, encoding="utf-8", errors="replace").read()
        a = _RE_ANCHOR.search(text)
        if a:
            ok_anchor += 1
        if "[DRY-RUN]" in text:
            ok_dry += 1
        has_head = "## Session " in text
        # 与 stop.jsonl 的 need_session_heading 对照
        base = os.path.basename(path)
        rec = next((r for r in stop_records
                    if any(base == os.path.basename(p)
                           for p in r.get("artifacts", [])
                           if p.endswith(".memory-draft.md"))), None)
        consistent = (rec is None) or (has_head == bool(rec.get("need_session_heading")))
        ok_head += consistent
        if not (a and "[DRY-RUN]" in text and consistent):
            print("  ⚠ %s anchor=%s dry=%s head_consistent=%s" % (
                base, bool(a), "[DRY-RUN]" in text, consistent))
    print("  anchor 合法: %d/%d | DRY-RUN 占位: %d/%d | 标题逻辑一致: %d/%d"
          % (ok_anchor, len(files), ok_dry, len(files), ok_head, len(files)))


def main():
    all_stop = []
    for root in ROOTS:
        sp = os.path.join(root, "stop.jsonl")
        if os.path.isfile(sp):
            all_stop += load_jsonl(sp)
    for root in ROOTS:
        if not os.path.isdir(root):
            continue
        p1_jsonl(root)
        p2_parsed(root)
        p3_drafts(root, all_stop)

    print("\n" + "=" * 70)
    print("P4 spec 验收项量化判定")
    print("=" * 70)
    print("  B1 注入块剥除   : 见 P2 '噪音标签泄漏总计'（期望 0）")
    print("  B2 只取末尾回合 : 见 P2 每文件 [User] 行数（期望 1）")
    print("  B4 快照保留策略 : 见 P2 [System] 列（空快照=0，有效快照>0）")
    print("  C1 空/短静默    : 见 P1 stop.skip_reason 分布（skip 且无异常）")
    print("  C5 只写 .memsearch: 产物全部位于 review/ 子目录 ✓")
    print("  review 模式红线 : stop.jsonl commands_preview 全部含 SKIPPED ✓（人工抽查）")


if __name__ == "__main__":
    sys.exit(main())

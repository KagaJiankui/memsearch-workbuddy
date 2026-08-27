# -*- coding: utf-8 -*-
"""Phase-4 T5 end-to-end tests for handler.py (review regression + live mode)."""
import json, os, pathlib, shutil, subprocess, sys, time

# NOTE: local-only paths, replace with your own before running
HANDLER = r"C:\path\to\workbuddy_plugin_memsearch\workbuddy\scripts\handler.py"
TRANSCRIPT = r"C:\Users\<USER>\.workbuddy\projects\<PROJECT>\<SESSION_ID>.jsonl"
SANDBOX = pathlib.Path(r"C:\Windows\Temp\wb-hook-test2")
TODAY = time.strftime("%Y-%m-%d")

def run(payload, env_extra=None, timeout=180):
    env = dict(os.environ)
    env.pop("MEMSEARCH_WB_REVIEW", None)
    if env_extra:
        env.update(env_extra)
    p = subprocess.run(
        [sys.executable, HANDLER],
        input=json.dumps(payload).encode("utf-8"),
        capture_output=True, timeout=timeout, env=env,
    )
    out = p.stdout.decode("utf-8", "replace").strip()
    try:
        resp = json.loads(out.splitlines()[0]) if out else {}
    except Exception:
        resp = {"_parse_error": out[:300]}
    return p.returncode, resp, p.stderr.decode("utf-8", "replace")[:300]

def fresh_sandbox():
    if SANDBOX.exists():
        shutil.rmtree(SANDBOX, ignore_errors=True)
    SANDBOX.mkdir(parents=True)

def stop_payload(**kw):
    d = {"hook_event_name": "Stop", "session_id": "t5e2e",
         "transcript_path": TRANSCRIPT, "cwd": str(SANDBOX),
         "stop_hook_active": False}
    d.update(kw)
    return d

fails = []
def check(name, cond, detail=""):
    print(("PASS" if cond else "FAIL"), "-", name, ("| " + detail if detail and not cond else ""))
    if not cond:
        fails.append(name)

# ---------- 1. review-mode regression ----------
fresh_sandbox()
rc, resp, err = run(stop_payload(), env_extra={"MEMSEARCH_WB_REVIEW": "1"})
check("review: exit 0 + continue", rc == 0 and resp.get("continue") is True, err)
rev = SANDBOX / ".memsearch" / "review"
check("review: stop.jsonl written", (rev / "stop.jsonl").is_file())
drafts = list(rev.glob("*.memory-draft.md")) + list(rev.glob("*.md"))
parsed = list(rev.glob("*.parsed.txt"))
check("review: draft + parsed artifacts", bool(drafts) and bool(parsed),
      "drafts=%s parsed=%s" % (drafts, parsed))
check("review: NO real memory dir", not (SANDBOX / ".memsearch" / "memory").exists())
check("review: NO index timestamp", not (SANDBOX / ".memsearch" / ".last-index-completed").exists())

# ---------- 2. live-mode Stop ----------
fresh_sandbox()
rc, resp, err = run(stop_payload(), timeout=180)
check("live: exit 0 + continue", rc == 0 and resp.get("continue") is True, err)
mf = SANDBOX / ".memsearch" / "memory" / ("%s.md" % TODAY)
check("live: memory file appended", mf.is_file() and mf.stat().st_size > 0)
if mf.is_file():
    body = mf.read_text(encoding="utf-8", errors="replace")
    check("live: has Session heading", "## Session" in body)
    check("live: has transcript anchor", "<!-- session:" in body and "transcript:" in body)
    check("live: has bullets", "- " in body)
ts = SANDBOX / ".memsearch" / ".last-index-completed"
check("live: index timestamp written", ts.is_file(), "missing")
if ts.is_file():
    age = time.time() - float(ts.read_text().strip())
    check("live: timestamp fresh (<180s)", 0 <= age < 180, "age=%.0f" % age)

# ---------- 3. SessionStart lag hint ----------
def session_start():
    return run({"hook_event_name": "SessionStart", "session_id": "t5e2e",
                "transcript_path": "", "cwd": str(SANDBOX)})

rc, resp, err = session_start()
msg = resp.get("systemMessage", "")
check("hint: fresh ts -> hint present", "远端索引" in msg or "追平" in msg, msg[:200])
check("hint: SessionStart still continue", resp.get("continue") is True)
# stale ts (2h old) -> no hint
ts.write_text(str(int(time.time()) - 7200))
rc, resp2, _ = session_start()
msg2 = resp2.get("systemMessage", "")
check("hint: stale ts -> hint absent", "追平" not in msg2, msg2[:200])
# missing ts -> no hint
ts.unlink()
rc, resp3, _ = session_start()
check("hint: missing ts -> hint absent", "追平" not in resp3.get("systemMessage", ""))
# missing CLI simulation not tested here (PATH intact)

# ---------- 4. guards ----------
fresh_sandbox()
rc, r1, _ = run(stop_payload(), env_extra={"MEMSEARCH_DISABLE": "1"})
check("guard: MEMSEARCH_DISABLE=1", r1 == {"continue": True}, str(r1)[:120])
rc, r2, _ = run(stop_payload(stop_hook_active=True))
check("guard: stop_hook_active", r2 == {"continue": True})
rc, r3, _ = run(stop_payload(transcript_path=r"C:\Windows\Temp\no-such.jsonl"))
check("guard: missing transcript", r3 == {"continue": True})
check("guard: missing transcript -> no memory write",
      not (SANDBOX / ".memsearch" / "memory").exists())

print("\n== %s ==" % ("ALL PASS" if not fails else "FAILURES: %s" % fails))
sys.exit(1 if fails else 0)

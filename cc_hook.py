"""
Claude Code hook script — writes session state to disk for the floating
indicator to pick up. Zero deps (stdlib only). Never blocks Claude: always
exits 0, swallows all errors. Logs to cc_hook.log next to this script for
diagnostic purposes (small, append-only).
"""
import json
import os
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).parent
STATE_DIR = ROOT / "state"
LOG_FILE = ROOT / "cc_hook.log"

EVENT_TO_STATUS = {
    "SessionStart":     "waiting",
    "UserPromptSubmit": "working",
    "Stop":             "waiting",
    # SubagentStop fires when a Task-spawned subagent finishes. Main is
    # still actively processing the subagent's output, so it stays working
    # — but the event lets us heartbeat the timestamp so the staleness
    # fallback doesn't kick in during long Task runs.
    "SubagentStop":     "working",
    "Notification":     "waiting",
    "SessionEnd":       "end",
}


def log(msg):
    try:
        with LOG_FILE.open("a", encoding="utf-8") as fh:
            fh.write(f"[{time.strftime('%H:%M:%S')} pid={os.getpid()}] {msg}\n")
    except Exception:
        pass


def main():
    # Force UTF-8 decoding of stdin: Claude Code emits UTF-8 JSON, but
    # Python's text-mode sys.stdin on Windows defaults to the system ANSI
    # codepage (cp936 here), which corrupts non-ASCII cwd paths into
    # surrogate escapes and later breaks the file write. Read raw bytes and
    # decode explicitly.
    try:
        raw = sys.stdin.buffer.read().decode("utf-8", errors="replace")
    except Exception as e:
        log(f"stdin read failed: {e}")
        sys.exit(0)

    try:
        payload = json.loads(raw) if raw else {}
    except Exception as e:
        log(f"json parse failed: {e}; raw={raw[:200]!r}")
        sys.exit(0)

    session_id = payload.get("session_id") or "unknown"
    cwd = payload.get("cwd") or ""
    event = payload.get("hook_event_name") or ""
    status = EVENT_TO_STATUS.get(event, "working")

    log(f"event={event} sid={session_id[:8]} cwd={cwd} -> status={status}")

    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        state_file = STATE_DIR / f"{session_id}.json"

        if status == "end":
            state_file.unlink(missing_ok=True)
            log(f"  unlinked {state_file.name}")
            sys.exit(0)

        prior = {}
        if state_file.exists():
            try:
                prior = json.loads(state_file.read_text(encoding="utf-8"))
            except Exception:
                prior = {}

        now = time.time()
        started = prior.get("started", now)
        if prior.get("status") != status:
            started = now

        payload_out = json.dumps({
            "session_id": session_id,
            "cwd": cwd,
            "status": status,
            "event": event,
            "updated": now,
            "started": started,
            "pid": os.getppid(),
        }, ensure_ascii=False)

        # Use an explicit open()/write()/close() with a flush so we can be
        # confident the bytes reached disk before this process exits, even
        # if Claude Code is sending us a SIGTERM-equivalent on hook timeout.
        with state_file.open("w", encoding="utf-8") as fh:
            fh.write(payload_out)
            fh.flush()
            os.fsync(fh.fileno())
        log(f"  wrote {len(payload_out)}B to {state_file.name}")
    except Exception as e:
        log(f"  write FAILED: {type(e).__name__}: {e}")
        log(traceback.format_exc())

    sys.exit(0)


if __name__ == "__main__":
    main()

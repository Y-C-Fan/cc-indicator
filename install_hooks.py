"""
Install / uninstall the cc-indicator hooks into ~/.claude/settings.json.

Merges with whatever is already there; never replaces unrelated keys.
Run:  python install_hooks.py           # install
      python install_hooks.py --remove  # uninstall
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HOOK_SCRIPT = ROOT / "cc_hook.py"
SETTINGS = Path(os.environ.get("USERPROFILE", str(Path.home()))) / ".claude" / "settings.json"

# We recognise our own entries by the absolute path to cc_hook.py appearing
# in the command — no shell-comment tricks (would break if Claude exec's the
# command directly without a shell).
TAG_NEEDLE = str(HOOK_SCRIPT).lower()

EVENTS = [
    "SessionStart", "SessionEnd",
    "UserPromptSubmit",
    "Stop", "SubagentStop",
    "Notification",
]


def hook_command():
    # Use pythonw.exe (no console window) so hooks don't flash a black box on
    # every event. Falls back to python.exe if pythonw isn't next to it.
    py = Path(sys.executable)
    pyw = py.with_name("pythonw.exe")
    interp = pyw if pyw.exists() else py
    interp_s = str(interp).replace("\\", "/")
    script_s = str(HOOK_SCRIPT).replace("\\", "/")
    return f'"{interp_s}" "{script_s}"'


def load_settings():
    if SETTINGS.exists():
        try:
            return json.loads(SETTINGS.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[!] {SETTINGS} 不是合法 JSON ({e})，先备份再写入。")
            backup = SETTINGS.with_suffix(".json.bak")
            backup.write_bytes(SETTINGS.read_bytes())
    return {}


def save_settings(data):
    SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def strip_ours(hooks_block):
    """Remove any matcher blocks/entries we previously added (identified by
    the cc_hook.py absolute path appearing in the command)."""
    clean = []
    for entry in hooks_block or []:
        kept = [h for h in entry.get("hooks", [])
                if not (isinstance(h, dict)
                        and TAG_NEEDLE in str(h.get("command", "")).lower())]
        if kept:
            entry = dict(entry, hooks=kept)
            clean.append(entry)
    return clean


def install():
    cfg = load_settings()
    hooks = cfg.get("hooks", {})
    cmd = hook_command()

    for ev in EVENTS:
        existing = strip_ours(hooks.get(ev, []))
        existing.append({
            "hooks": [{"type": "command", "command": cmd}]
        })
        hooks[ev] = existing

    cfg["hooks"] = hooks
    save_settings(cfg)
    print(f"[ok] hooks 已写入 {SETTINGS}")
    print(f"[ok] hook 脚本: {HOOK_SCRIPT}")
    print(f"[ok] 解释器: {sys.executable}")
    print("    新开的 Claude Code 会话就会上报状态了。")


def remove():
    cfg = load_settings()
    hooks = cfg.get("hooks", {})
    changed = False
    for ev in list(hooks.keys()):
        cleaned = strip_ours(hooks[ev])
        if cleaned != hooks[ev]:
            changed = True
        if cleaned:
            hooks[ev] = cleaned
        else:
            del hooks[ev]
    if not hooks:
        cfg.pop("hooks", None)
    save_settings(cfg)
    print(f"[ok] {'已移除' if changed else '没找到要移除的项'}")


if __name__ == "__main__":
    if "--remove" in sys.argv or "-r" in sys.argv:
        remove()
    else:
        install()

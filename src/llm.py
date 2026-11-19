"""The single entry point for every Claude call: `claude -p` on the user's Pro subscription.

Every call runs from the empty directory runs/sandbox_empty/ with tools, CLAUDE.md, skills,
hooks and memory disabled, and Claude Code's default system prompt replaced. Responses are
cached by a hash of all inputs, so re-running a stage never spends quota twice.
"""

import hashlib
import json
import re
import shutil
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SANDBOX = ROOT / "runs" / "sandbox_empty"
CACHE = ROOT / "results" / "cache"
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))


def call(model: str, system: str, prompt: str, tag: str, sample: int = 0) -> dict:
    """Return the cached or fresh record {"text", "usage", "is_error", ...} for one call.

    `tag` names the call in logs (e.g. "R1|inject|it1"); `sample` separates repeated samples
    of the same prompt so each gets its own cache entry.
    """
    effort = CONFIG["effort"]
    key = hashlib.sha256(
        json.dumps([model, effort, system, prompt, sample]).encode("utf-8")
    ).hexdigest()
    path = CACHE / f"{key}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))

    SANDBOX.mkdir(parents=True, exist_ok=True)
    if any(SANDBOX.iterdir()):
        raise RuntimeError(f"{SANDBOX} must stay empty")
    cmd = [
        shutil.which("claude") or "claude", "-p",
        "--model", model, "--effort", effort,
        "--tools", "", "--safe-mode", "--no-session-persistence",
        "--system-prompt", system, "--output-format", "json",
    ]
    started = time.time()
    proc = subprocess.run(
        cmd, input=prompt, capture_output=True, text=True, encoding="utf-8",
        cwd=SANDBOX, timeout=CONFIG["call_timeout_s"],
    )
    try:
        out = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"claude -p failed ({tag}): {(proc.stderr or proc.stdout)[-800:]}")

    record = {
        "tag": tag, "model": model, "effort": effort, "sample": sample,
        "system": system, "prompt": prompt,
        "text": out.get("result", ""), "is_error": out.get("is_error", True),
        "stop_reason": out.get("stop_reason"), "usage": out.get("usage", {}),
        "seconds": round(time.time() - started, 1),
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    if record["is_error"]:
        # never cache failures (e.g. usage limit reached) so a later run can retry them
        raise RuntimeError(f"claude -p returned an error ({tag}): {record['text'][:500]}")
    CACHE.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=1, ensure_ascii=False), encoding="utf-8")
    u = record["usage"]
    print(f"  [{tag}] {model} in={u.get('input_tokens', 0) + u.get('cache_creation_input_tokens', 0) + u.get('cache_read_input_tokens', 0)}"
          f" out={u.get('output_tokens', 0)} {record['seconds']}s")
    return record


def extract_json(text: str) -> dict:
    """Parse the JSON object in a model reply (inside a ```json fence, or the outermost braces)."""
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    raw = m.group(1) if m else text[text.find("{"): text.rfind("}") + 1]
    return json.loads(raw)


def extract_code(text: str, entry_point: str | None = None) -> str | None:
    """Return the last ```python fenced block that defines `entry_point` (a reply may end with a
    short snippet repeating one changed line), else the last block, or None."""
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.S)
    if entry_point:
        full = [b for b in blocks if re.search(rf"^\s*def\s+{re.escape(entry_point)}\s*\(", b, re.M)]
        if full:
            return full[-1]
    return blocks[-1] if blocks else None

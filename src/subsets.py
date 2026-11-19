"""Per-subset paths and settings. Every stage script accepts `--subset bcb`; without it, the
script runs on the HumanEval subset ("heval"), exactly as in the first run.

heval: Orchid-HEval tasks R1-R6, tests = HumanEval+ input/output pairs ("io").
bcb:   Orchid-BCB tasks B1-B6, tests = BigCodeBench unittest classes ("unittest").
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SUBSETS = {
    "heval": {
        "data": ROOT / "data", "results": ROOT / "results",
        "raw": ROOT / "data" / "raw" / "orchid_heval.jsonl", "key": "name", "prompt_field": "prompt",
        # few-shot exemplars come from tasks that are not among the evaluated six
        "exemplars": ["HumanEval/0", "HumanEval/131"],
    },
    "bcb": {
        "data": ROOT / "data" / "bcb", "results": ROOT / "results" / "bcb",
        "raw": ROOT / "data" / "raw" / "orchid_bcb.jsonl", "key": "task_id", "prompt_field": "instruct_prompt",
        "exemplars": ["BigCodeBench/0", "BigCodeBench/19"],
    },
}


def select(argv: list[str]) -> dict:
    """Remove `--subset NAME` from argv (in place) and return that subset's settings."""
    name = "heval"
    if "--subset" in argv:
        i = argv.index("--subset")
        name = argv[i + 1]
        del argv[i:i + 2]
    if name not in SUBSETS:
        raise SystemExit(f"unknown subset {name!r}; use one of {sorted(SUBSETS)}")
    s = dict(SUBSETS[name], name=name)
    s["original"], s["combined"] = s["data"] / "original", s["data"] / "combined"
    return s


def show(prompt: str, sub: dict) -> str:
    """How a requirement is shown inside a prompt: HumanEval prompts are code, so they are fenced;
    BigCodeBench instruct prompts are prose that already contain their own code fence."""
    return f"```python\n{prompt}\n```" if sub["name"] == "heval" else prompt

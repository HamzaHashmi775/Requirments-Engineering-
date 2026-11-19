"""Stage 4: generate code for the original and the combined requirement of every approved task.

Prompt follows the evalplus / BigCodeBench instruction format for chat models. Every
(task, variant, model, sample) is one cached `claude -p` call, so the script can be stopped and
re-run at any time (e.g. after the weekly limit resets) without repeating finished calls.

Usage (from the project root):  python src/generate.py [R1 R2 ... | B1 ...] [--subset bcb]
Output: <results>/generations.jsonl (one record per sample; rewritten on every run)
"""

import json
import sys

from llm import CONFIG, call, extract_code
from subsets import select, show

SYSTEM_GEN = "You are an expert Python programmer."
INSTRUCTION = "Please provide a self-contained Python script that solves the following problem in a markdown code block:\n{shown}"


def main() -> None:
    args = sys.argv[1:]
    sub = select(args)
    ids = args or [p.stem for p in sorted(sub["combined"].glob("*.json"))]
    tasks = [json.loads((sub["combined"] / f"{i}.json").read_text(encoding="utf-8")) for i in ids]
    not_ready = [t["id"] for t in tasks if t["status"] != "approved"]
    if not_ready:
        sys.exit(f"not approved yet: {not_ready}")

    records = []
    for t in tasks:
        t["entry_point"] = json.loads((sub["original"] / f"{t['id']}.json").read_text(encoding="utf-8"))["entry_point"]
        # strip both prompts so original and combined are formatted identically
        variants = {"original": t["original_prompt"].strip(), "combined": t["ambiguous_prompt"].strip()}
        for variant, prompt in variants.items():
            for model in CONFIG["models_under_test"]:
                for s in range(CONFIG["n_samples"]):
                    tag = f"{t['id']}|{variant}|{model}|{s}"
                    rec = call(model, SYSTEM_GEN, INSTRUCTION.format(shown=show(prompt, sub)), tag, sample=s)
                    records.append({"id": t["id"], "variant": variant, "model": model, "sample": s,
                                    "code": extract_code(rec["text"], t["entry_point"]), "usage": rec["usage"]})
    out = sub["results"] / "generations.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    missing = sum(r["code"] is None for r in records)
    print(f"wrote {len(records)} samples to {out} ({missing} without a code block)")


if __name__ == "__main__":
    main()

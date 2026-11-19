"""Build <data>/original/*.json for the tasks in <data>/task_map.json.

heval: the original (clear) requirement from Orchid-HEval, the reference solution, the Orchid
single-type variants (few-shot exemplars only), and the HumanEval+ test inputs (base + plus)
with expected outputs computed by running the reference solution.
bcb: the Orchid-BCB instruct prompt, the reference solution, the exemplars, and the
BigCodeBench unittest code; the reference must pass every test on this machine.

Usage (from the project root):  python src/prepare_tasks.py [--subset bcb]
"""

import gzip
import json
import sys
from pathlib import Path

from execute import run_function, run_unittest
from subsets import ROOT, select

TYPES = ["Lexical", "Syntactic", "Semantic", "Vagueness"]


def load_jsonl(path: Path, key: str) -> dict:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as f:
        return {r[key]: r for r in map(json.loads, f)}


def exemplars_of(o: dict) -> dict:
    return {ty: {"prompt": o[f"{ty}_prompt"], "explanation": o[f"{ty}_ambiguity_explanation"]} for ty in TYPES}


def heval_record(t: dict, o: dict, h: dict) -> dict:
    assert o["entry_point"] == h["entry_point"], t["task_id"]
    reference = h["prompt"] + h["canonical_solution"]
    inputs = h["base_input"] + h["plus_input"]
    run = run_function(reference, h["entry_point"], inputs)
    if "results" not in run:
        raise RuntimeError(f"{t['id']}: reference solution failed: {run}")
    bad = [i for i, r in enumerate(run["results"]) if not r["ok"]]
    if bad:
        raise RuntimeError(f"{t['id']}: reference raised on inputs {bad[:5]}")
    return {
        **t, "kind": "io", "entry_point": h["entry_point"],
        "original_prompt": o["prompt"], "reference_solution": reference,
        "single_type_exemplars": exemplars_of(o),
        "atol": h["atol"], "n_base": len(h["base_input"]),
        "tests": [{"input": i, "expected": r["out"]} for i, r in zip(inputs, run["results"])],
    }


def bcb_record(t: dict, o: dict, data_dir: Path) -> dict:
    """Witness tests in <data>/witness_tests/<id>.py, if present, are appended to the original
    tests (for ambiguities the original BigCodeBench tests cannot detect)."""
    reference = o["complete_prompt"] + o["canonical_solution"]
    test_code = o["test"]
    witness_file = data_dir / "witness_tests" / f"{t['id']}.py"
    if witness_file.exists():
        test_code += "\n\n" + witness_file.read_text(encoding="utf-8")
    run = run_unittest(reference, test_code)
    if "tests" not in run or not run["tests"] or any(v != "pass" for v in run["tests"].values()):
        raise RuntimeError(f"{t['id']}: reference does not pass its tests here: {run}")
    return {
        **t, "kind": "unittest", "entry_point": o["entry_point"],
        "original_prompt": o["instruct_prompt"], "reference_solution": reference,
        "single_type_exemplars": exemplars_of(o),
        "atol": 0.0, "test_code": test_code, "test_names": sorted(run["tests"]),
        "witness_tests": sorted(n for n in run["tests"] if n.startswith("WitnessTests.")),
    }


def main() -> None:
    sub = select(sys.argv)
    task_map = json.loads((sub["data"] / "task_map.json").read_text(encoding="utf-8"))
    orchid = load_jsonl(sub["raw"], sub["key"])
    if sub["name"] == "heval":
        heplus = load_jsonl(ROOT / "data" / "raw" / "HumanEvalPlus-v0.1.10.jsonl.gz", "task_id")
    sub["original"].mkdir(parents=True, exist_ok=True)

    for t in task_map:
        o = orchid[t["task_id"]]
        record = heval_record(t, o, heplus[t["task_id"]]) if sub["name"] == "heval" else bcb_record(t, o, sub["data"])
        path = sub["original"] / f"{t['id']}.json"
        path.write_text(json.dumps(record, indent=1, ensure_ascii=False), encoding="utf-8")
        n = len(record["tests"]) if record["kind"] == "io" else len(record["test_names"])
        print(f"{t['id']}  {t['task_id']:<18} {record['entry_point']:<20} pair={'+'.join(t['pair'])}  tests={n}")


if __name__ == "__main__":
    main()

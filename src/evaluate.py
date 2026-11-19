"""Stage 5: run every generated sample on the task's tests; compute pass@k and conflict rate.

- pass@k: unbiased estimator 1 - C(n-c, k) / C(n, k); a sample passes only if all tests pass.
- conflict rate: share of sample pairs that behave differently on at least one test.
  heval: different output on a HumanEval+ input (an exception counts as an output; two
  exceptions count as equal). bcb: different outcome (pass/fail/error) on a unittest method —
  coarser, since there are only 5-8 tests per task. Intra-model = pairs of one model's samples;
  inter-model = pairs over both models' samples.

Usage (from the project root):  python src/evaluate.py [--subset bcb]
- valid-task analysis: the same means restricted, per model, to tasks whose ORIGINAL prompt the
  model solves in >= VALID_RATE of its samples (separates benchmark test/prompt mismatches from
  ambiguity effects); reported next to the all-task results, never instead of them.

Output: <results>/samples_eval.jsonl, <results>/summary.json, and a table on stdout.
"""

import json
import sys
from itertools import combinations
from math import comb

from execute import outputs_equal, run_function, run_unittest
from llm import CONFIG
from subsets import select

ERR = {"__error__": True}
VALID_RATE = 0.8  # valid-task analysis: original pass@1 >= 4/5 for that model (decided 2026-11-19)


def pass_at_k(n: int, c: int, k: int) -> float:
    return 1.0 if n - c < k else 1.0 - comb(n - c, k) / comb(n, k)


def expected_of(task: dict) -> list:
    if task.get("kind", "io") == "unittest":
        return ["pass"] * len(task["test_names"])
    return [x["expected"] for x in task["tests"]]


def outputs_of(code: str | None, task: dict) -> list:
    """One entry per test: the output (heval) or the outcome "pass"/"fail"/"error" (bcb);
    ERR / "error" for exceptions or when the code cannot run at all."""
    if task.get("kind", "io") == "unittest":
        names = task["test_names"]
        run = run_unittest(code, task["test_code"]) if code is not None else {}
        return [run["tests"].get(n, "error") for n in names] if "tests" in run else ["error"] * len(names)
    if code is None:
        return [ERR] * len(task["tests"])
    run = run_function(code, task["entry_point"], [t["input"] for t in task["tests"]])
    if "results" not in run:
        return [ERR] * len(task["tests"])
    return [r["out"] if r["ok"] else ERR for r in run["results"]]


def same(a: list, b: list, atol: float) -> bool:
    return all(outputs_equal(x, y, atol) for x, y in zip(a, b))


def conflict_rate(outs: list[list], atol: float) -> float | None:
    pairs = list(combinations(outs, 2))
    return sum(not same(a, b, atol) for a, b in pairs) / len(pairs) if pairs else None


def main() -> None:
    sub = select(sys.argv)
    results = sub["results"]
    gens = [json.loads(l) for l in (results / "generations.jsonl").open(encoding="utf-8")]
    tasks = {}
    for g in gens:
        if g["id"] not in tasks:
            tasks[g["id"]] = json.loads((sub["original"] / f"{g['id']}.json").read_text(encoding="utf-8"))

    for g in gens:
        t = tasks[g["id"]]
        g["outputs"] = outputs_of(g["code"], t)
        expected = expected_of(t)
        g["n_failed_tests"] = sum(not outputs_equal(o, e, t["atol"]) for o, e in zip(g["outputs"], expected))
        g["passed"] = g["n_failed_tests"] == 0
    with (results / "samples_eval.jsonl").open("w", encoding="utf-8") as f:
        for g in gens:
            f.write(json.dumps({k: v for k, v in g.items() if k != "outputs"}, ensure_ascii=False) + "\n")

    models, ks = CONFIG["models_under_test"], CONFIG["pass_k"]
    rows = []
    for rid, t in tasks.items():
        for variant in ("original", "combined"):
            group = [g for g in gens if g["id"] == rid and g["variant"] == variant]
            row = {"id": rid, "pair": "+".join(t["pair"]), "variant": variant}
            for m in models:
                ms = [g for g in group if g["model"] == m]
                n, c = len(ms), sum(g["passed"] for g in ms)
                for k in ks:
                    row[f"{m}|pass@{k}"] = pass_at_k(n, c, k) if n >= k else None
                row[f"{m}|conflict"] = conflict_rate([g["outputs"] for g in ms], t["atol"])
            row["inter_model_conflict"] = conflict_rate([g["outputs"] for g in group], t["atol"])
            rows.append(row)

    def mean(xs):
        xs = [x for x in xs if x is not None]
        return sum(xs) / len(xs) if xs else None

    overall = {}
    for variant in ("original", "combined"):
        vr = [r for r in rows if r["variant"] == variant]
        overall[variant] = {key: mean(r[key] for r in vr) for key in vr[0] if "|" in key or key == "inter_model_conflict"}
    # valid-task analysis: per model, only tasks the model solves from the ORIGINAL prompt in at
    # least VALID_RATE of its samples, so test/prompt mismatches of the benchmark (failures on
    # the clear prompt too) are not counted as ambiguity effects. All tasks stay in `overall`.
    valid_only = {}
    for m in models:
        ok = [r["id"] for r in rows if r["variant"] == "original" and r[f"{m}|pass@1"] >= VALID_RATE]
        valid_only[m] = {"tasks": ok, "excluded": [rid for rid in tasks if rid not in ok]}
        for variant in ("original", "combined"):
            vr = [r for r in rows if r["variant"] == variant and r["id"] in ok]
            valid_only[m][variant] = {key: mean(r[key] for r in vr) for key in vr[0]
                                      if key.startswith(m + "|")} if vr else {}
    (results / "summary.json").write_text(json.dumps({"per_task": rows, "overall": overall, "valid_only": valid_only,
                                                      "valid_rate": VALID_RATE}, indent=1), encoding="utf-8")

    pct = lambda x: "  -  " if x is None else f"{100 * x:5.1f}"
    for m in models:
        print(f"\n{m}")
        print(f"{'task':<5}{'variant':<10}" + "".join(f"pass@{k:<4}" for k in ks) + "conflict")
        for r in rows + [{"id": "ALL", "variant": v, **overall[v]} for v in ("original", "combined")]:
            print(f"{r['id']:<5}{r['variant']:<10}" + "".join(f"{pct(r[f'{m}|pass@{k}']):<9}" for k in ks) + pct(r[f"{m}|conflict"]))
    print("\ninter-model conflict:  original " + pct(overall["original"]["inter_model_conflict"])
          + "   combined " + pct(overall["combined"]["inter_model_conflict"]))
    for m in models:
        for k in ks:
            o, c = overall["original"][f"{m}|pass@{k}"], overall["combined"][f"{m}|pass@{k}"]
            print(f"{m}  Δpass@{k} = {pct(o - c)} points")
    print(f"\nvalid tasks only (original pass@1 >= {VALID_RATE:.0%} for that model):")
    for m in models:
        v = valid_only[m]
        print(f"{m}  {len(v['tasks'])} tasks, excluded {v['excluded']}")
        for k in ks:
            o, c = v["original"].get(f"{m}|pass@{k}"), v["combined"].get(f"{m}|pass@{k}")
            if o is not None and c is not None:
                print(f"   pass@{k}: {pct(o)} -> {pct(c)}   Δ = {pct(o - c)}")


if __name__ == "__main__":
    main()

"""Stage 2: inject a pair of ambiguity types into each original requirement.

Injection agent -> Judge agent (up to N rounds, feedback loop) -> Explain agent, then an
automatic divergence check: the Explain agent's code for each alternative reading must behave
differently from the reference on the task's tests (heval: a different output on at least one
HumanEval+ input; bcb: at least one BigCodeBench unittest that the reference passes fails).

Usage (from the project root):
  python src/rewrite.py [R1 R2 ... | B1 B2 ...] [--subset bcb] [--force] [--feedback "..."]
  --force     redo an existing requirement with fresh calls (old version kept as rejected)
  --feedback  reviewer comment on the rejected version, passed to the Injection agent
  --recheck   only re-run the divergence checks of existing versions (no Claude calls)
Output: <data>/combined/*.json, status "pending_human_review" (Stage 3 is manual).
"""

import json
import sys

from execute import outputs_equal, run_function, run_unittest
from llm import CONFIG, call, extract_json
from subsets import select, show

NAMES = {"L": "Lexical", "S": "Syntactic", "M": "Semantic", "V": "Vagueness"}
DEFINITIONS = """\
- Lexical: a word in the requirement has multiple distinct meanings, causing different interpretations.
- Syntactic: the requirement's grammatical structure has multiple distinct meanings (e.g. unclear attachment, scope or pronoun reference), causing different interpretations.
- Semantic: a phrase or sentence in the requirement has multiple distinct meanings, causing different interpretations.
- Vagueness: the requirement omits necessary details, so it has multiple distinct meanings, causing different interpretations."""
# per-subset wording; the heval strings are exactly those of the first run (keeps its cache valid)
KEEP_RULE = {
    "heval": "Keep imports, the function signature, docstring delimiters and indentation exactly as in the original. Change only the natural-language text. Do not add examples.",
    "bcb": "Keep the code block (imports and function signature) exactly as in the original. You may reword the description and the output-format lines (\"The function should output with: ...\"); the output-format lines must stay consistent with the description and must NOT resolve either injected ambiguity (no part of the requirement may reveal which reading is intended). Do not add examples.",
}
# bcb only: the leak audit (data/leak_audit.csv) found ambiguities resolved by the unchanged
# output-format lines, so the judge checks the whole requirement for leaks
LEAK_CHECK = {
    "heval": ("", ""),
    "bcb": ("\n- no_leak: no other part of the requirement (output-format lines, imports, names) reveals which reading of either injected ambiguity is intended.",
            ' "no_leak": true,'),
}
FORMAT_HINT = {
    "heval": "<full rewritten code: imports + signature + docstring>",
    "bcb": "<full rewritten requirement text, including the unchanged code block>",
}

SYSTEM_INJECT = "You are an expert in requirements engineering who writes realistic ambiguous software requirements for a research benchmark."
SYSTEM_JUDGE = "You are a strict expert reviewer of ambiguous software requirements for a research benchmark."
SYSTEM_EXPLAIN = "You are an expert in requirements engineering and Python who explains ambiguities in software requirements precisely."


def exemplars(types: list[str], sub: dict) -> str:
    rows = {json.loads(l)[sub["key"]]: json.loads(l) for l in sub["raw"].open(encoding="utf-8")}
    parts = []
    for task in sub["exemplars"]:
        r = rows[task]
        for t in types:
            n = NAMES[t]
            parts.append(
                f"### {n} ambiguity example\nOriginal:\n{show(r[sub['prompt_field']].strip(), sub)}\n"
                f"Rewritten:\n{show(r[f'{n}_prompt'].strip(), sub)}\n"
                f"Explanation: {r[f'{n}_ambiguity_explanation']}\n"
            )
    return "\n".join(parts)


def inject_prompt(task: dict, feedback: str | None, sub: dict) -> str:
    a, b = (NAMES[t] for t in task["pair"])
    fb = f"\nA reviewer rejected your previous attempt:\n{feedback}\nFix these problems.\n" if feedback else ""
    return f"""Rewrite the function-level requirement below so that it contains EXACTLY two ambiguities: one {a} ambiguity and one {b} ambiguity.

Ambiguity types:
{DEFINITIONS}

Rules:
1. Inject the {a} ambiguity and the {b} ambiguity at two different places in the text.
2. Inject no other ambiguity; everything else stays as clear as in the original.
3. The original meaning must remain one plausible reading of the rewritten text.
4. Each injected ambiguity must allow another plausible reading that leads to a functionally different implementation (some input gives a different output).
5. {KEEP_RULE[sub['name']]}
6. It must read naturally, like a real developer wrote it, with a similar length.

Single-type examples from other tasks:

{exemplars(task['pair'], sub)}
Original requirement:
{show(task['original_prompt'].strip(), sub)}
{fb}
Reply with only a JSON object in a ```json fence:
{{"ambiguous_prompt": "{FORMAT_HINT[sub['name']]}",
 "ambiguities": [{{"type": "<{a} or {b}>", "span": "<exact ambiguous words>", "readings": ["<intended reading>", "<alternative reading>"]}}]}}"""


def judge_prompt(task: dict, candidate: str, sub: dict) -> str:
    a, b = (NAMES[t] for t in task["pair"])
    leak_rule, leak_field = LEAK_CHECK[sub["name"]]
    return f"""A requirement was rewritten to contain EXACTLY two ambiguities: one {a} and one {b}.

Ambiguity types:
{DEFINITIONS}

Original requirement:
{show(task['original_prompt'].strip(), sub)}

Rewritten requirement:
{show(candidate.strip(), sub)}

Evaluate the rewritten requirement:
- For each of {a} and {b}: type_correct (an ambiguity of exactly this type is present, at its own span); divergent (two plausible readings give different outputs for some input; give that input as Python call arguments in witness_input); plausibility 1-5 (how plausible the alternative reading is to a competent developer).
- intent_preserved: the original meaning is still a plausible reading.
- no_extra_ambiguity: no other ambiguity or unintended change of meaning was introduced.
- signature_unchanged: imports and function signature are identical to the original.{leak_rule}
- naturalness 1-5: reads like a requirement a real developer would write.
- feedback: concrete fixes for anything that fails (empty if all is fine).

Reply with only a JSON object in a ```json fence:
{{"per_type": [{{"type": "<{a} or {b}>", "type_correct": true, "divergent": true, "witness_input": "<args>", "plausibility": 5}}],
 "intent_preserved": true, "no_extra_ambiguity": true, "signature_unchanged": true,{leak_field} "naturalness": 5, "feedback": ""}}"""


def explain_prompt(task: dict, ambiguous: str, sub: dict) -> str:
    a, b = (NAMES[t] for t in task["pair"])
    return f"""The ambiguous requirement below contains one {a} ambiguity and one {b} ambiguity. The original (intended) requirement is also given.

Original requirement:
{show(task['original_prompt'].strip(), sub)}

Ambiguous requirement:
{show(ambiguous.strip(), sub)}

For each of the two ambiguities give: the exact ambiguous span; a concise explanation of its effect; the intended reading; the most plausible alternative reading; and a complete Python implementation (same imports and signature) of the requirement under the ALTERNATIVE reading of this ambiguity, with the other ambiguity resolved as intended.

Reply with only a JSON object in a ```json fence:
{{"ambiguities": [{{"type": "<{a} or {b}>", "span": "", "explanation": "", "intended_reading": "", "alternative_reading": "", "alternative_implementation": "<python code>"}}]}}"""


def judge_passes(j: dict) -> tuple[bool, int]:
    per = j.get("per_type", [])
    ok = (len(per) == 2 and all(p.get("type_correct") and p.get("divergent") and p.get("plausibility", 0) >= 3 for p in per)
          and j.get("intent_preserved") and j.get("no_extra_ambiguity") and j.get("signature_unchanged")
          and j.get("no_leak", True) and j.get("naturalness", 0) >= 4)  # no_leak: bcb judge only
    score = (sum(bool(p.get("type_correct")) + bool(p.get("divergent")) + p.get("plausibility", 0) for p in per)
             + 2 * bool(j.get("intent_preserved")) + 2 * bool(j.get("no_extra_ambiguity"))
             + 2 * bool(j.get("signature_unchanged")) + 2 * bool(j.get("no_leak", True)) + j.get("naturalness", 0))
    return bool(ok), score


def verify(task: dict, impl: str) -> dict:
    """Does the alternative implementation behave differently from the reference on the tests?"""
    if task.get("kind", "io") == "unittest":
        run = run_unittest(impl, task["test_code"])
        if "tests" not in run:
            return {"verified": False, "error": run}
        failing = sorted(n for n in task["test_names"] if run["tests"].get(n) != "pass")
        return {"verified": bool(failing), "n_diverging_tests": len(failing),
                "n_tests": len(task["test_names"]), "failing_tests": failing}
    run = run_function(impl, task["entry_point"], [t["input"] for t in task["tests"]])
    if "results" not in run:
        return {"verified": False, "error": run}
    diff = [i for i, (t, r) in enumerate(zip(task["tests"], run["results"]))
            if not (r["ok"] and outputs_equal(r["out"], t["expected"], task["atol"]))]
    return {"verified": bool(diff), "n_diverging_tests": len(diff), "n_tests": len(task["tests"]),
            "first_witness": task["tests"][diff[0]]["input"] if diff else None}


def rewrite(task: dict, sub: dict, attempt: int = 0, feedback: str | None = None) -> dict:
    """`attempt` > 0 (a --force redo) gives every call a fresh cache key; `feedback` is the
    human reviewer's comment on the rejected version, passed to the first injection round."""
    model, history, best = CONFIG["agent_model"], [], None
    for it in range(1, CONFIG["max_rewrite_iterations"] + 1):
        cand = extract_json(call(model, SYSTEM_INJECT, inject_prompt(task, feedback, sub), f"{task['id']}|inject|it{it}", attempt)["text"])
        judge = extract_json(call(model, SYSTEM_JUDGE, judge_prompt(task, cand["ambiguous_prompt"], sub), f"{task['id']}|judge|it{it}", attempt)["text"])
        passed, score = judge_passes(judge)
        history.append({"iteration": it, "candidate": cand, "judge": judge, "passed": passed, "score": score})
        if best is None or score > best["score"]:
            best = history[-1]
        if passed:
            break
        feedback = judge.get("feedback") or "The candidate did not meet the criteria."

    ambiguous = best["candidate"]["ambiguous_prompt"]
    expl = extract_json(call(model, SYSTEM_EXPLAIN, explain_prompt(task, ambiguous, sub), f"{task['id']}|explain", attempt)["text"])
    for amb in expl["ambiguities"]:
        amb["divergence_check"] = verify(task, amb["alternative_implementation"])
    return {
        "id": task["id"], "task_id": task["task_id"], "pair": task["pair"],
        "original_prompt": task["original_prompt"], "ambiguous_prompt": ambiguous,
        "judge_passed": best["passed"], "iterations_used": len(history),
        "explanation": expl, "history": history,
        "status": "pending_human_review",
        "human_review": {"approved": None, "notes": ""},
    }


def main() -> None:
    args = sys.argv[1:]
    sub = select(args)
    force = "--force" in args
    feedback = None
    if "--feedback" in args:
        i = args.index("--feedback")
        feedback = args[i + 1]
        del args[i:i + 2]
    ids = [a for a in args if not a.startswith("--")] or [p.stem for p in sorted(sub["original"].glob("*.json"))]
    sub["combined"].mkdir(parents=True, exist_ok=True)
    if "--recheck" in args:
        # re-run only the divergence checks of existing versions (e.g. after tests were added)
        for rid in ids:
            path = sub["combined"] / f"{rid}.json"
            result = json.loads(path.read_text(encoding="utf-8"))
            task = json.loads((sub["original"] / f"{rid}.json").read_text(encoding="utf-8"))
            for amb in result["explanation"]["ambiguities"]:
                amb["divergence_check"] = verify(task, amb["alternative_implementation"])
            path.write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")
            print(rid, [(a["type"], a["divergence_check"].get("verified"), a["divergence_check"].get("failing_tests"))
                        for a in result["explanation"]["ambiguities"]])
        return
    for rid in ids:
        out = sub["combined"] / f"{rid}.json"
        rejected = []
        if out.exists():
            if not force:
                print(f"skip {rid} (exists; use --force to redo)")
                continue
            old = json.loads(out.read_text(encoding="utf-8"))
            rejected = old.pop("rejected_attempts", [])
            old.pop("history", None)
            rejected.append({**old, "rejection_feedback": feedback})
        task = json.loads((sub["original"] / f"{rid}.json").read_text(encoding="utf-8"))
        print(f"{rid} ({'+'.join(task['pair'])}), attempt {len(rejected)}:")
        result = rewrite(task, sub, attempt=len(rejected), feedback=feedback)
        result["rejected_attempts"] = rejected
        out.write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")
        checks = [a["divergence_check"].get("verified") for a in result["explanation"]["ambiguities"]]
        print(f"  judge_passed={result['judge_passed']} iterations={result['iterations_used']} divergence_verified={checks}")


if __name__ == "__main__":
    main()

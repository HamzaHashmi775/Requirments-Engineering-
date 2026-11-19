"""Stage 6 (RQ3): can the models recognise, localise and resolve the injected ambiguities?

Each model under test gets every original and combined requirement once and must say whether
it is ambiguous, quote each ambiguous segment and give clarification options. Whether it
flagged the requirement is read from its own answer; the judge (agent model) is only called
for flagged combined requirements, to grade each injected ambiguity on the paper's levels:
  unaware (requirement not flagged) < detection (flagged, but this ambiguity not pinpointed)
  < localization (segment pinpointed) < tackling (pinpointed + options that resolve it).
A requirement's overall level is the best level over its two ambiguities (paper's single label).

Usage (from the project root):  python src/recognize.py [--subset bcb]
Output: <results>/recognition.jsonl, <results>/recognition_summary.json,
        <results>/recognition_review.csv (fill human_agrees to check every judge grade by hand)
"""

import csv
import json
import sys

from llm import CONFIG, call, extract_json
from subsets import select, show

LEVELS = ["unaware", "detection", "localization", "tackling"]

SYSTEM_RECOGNIZE = "You are an expert software engineer who reviews requirements before implementing them."
SYSTEM_JUDGE = "You are a strict, careful grader for a research study on ambiguity in software requirements."

RECOGNIZE = """Below is the requirement for a Python function you are asked to implement.

{shown}

Before implementing it, decide whether the requirement is ambiguous: does any wording allow more than one plausible interpretation that would lead to functionally different implementations (different outputs for some input)? Do not flag ordinary details that a competent developer would resolve the same way.

If it is ambiguous, list every ambiguous segment: quote the exact words, explain why they are ambiguous, and give concrete clarification options (the possible interpretations a stakeholder could choose between).

Reply with only a JSON object in a ```json fence:
{{"ambiguous": true, "issues": [{{"segment": "<exact quoted words>", "reason": "", "options": ["", ""]}}]}}
Use {{"ambiguous": false, "issues": []}} if it is not ambiguous."""

JUDGE = """A model reviewed the requirement below and reported ambiguities. The requirement contains exactly these injected ambiguities (ground truth):

Requirement:
{shown}

Ground-truth ambiguities:
{truth}

Model's answer:
```json
{answer}
```

For EACH ground-truth ambiguity, grade the model's answer:
- "detection": the model did not pinpoint this ambiguity (no reported segment refers to these words / this issue).
- "localization": a reported segment pinpoints this ambiguity (the same words or the same issue), but its options do not offer both the intended and the alternative reading (or no concrete options).
- "tackling": it pinpoints this ambiguity AND its options include readings equivalent to both the intended and the alternative reading.
Also count reported issues that match no ground-truth ambiguity (spurious_issues).

Reply with only a JSON object in a ```json fence:
{{"per_ambiguity": [{{"type": "<type>", "level": "detection|localization|tackling", "matched_segment": "<model's segment or empty>", "reason": ""}}], "spurious_issues": 0}}"""


def truth_text(task: dict) -> str:
    return "\n".join(
        f"{i}. {a['type']}: span \"{a['span']}\" — intended: {a['intended_reading']} — alternative: {a['alternative_reading']}"
        for i, a in enumerate(task["explanation"]["ambiguities"], 1))


def run(sub: dict) -> list[dict]:
    tasks = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(sub["combined"].glob("*.json"))]
    records = []
    for t in tasks:
        for variant, prompt in (("original", t["original_prompt"].strip()), ("combined", t["ambiguous_prompt"].strip())):
            for model in CONFIG["models_under_test"]:
                rec = call(model, SYSTEM_RECOGNIZE, RECOGNIZE.format(shown=show(prompt, sub)), f"{t['id']}|recognize|{variant}|{model}")
                try:
                    answer = extract_json(rec["text"])
                except ValueError:
                    answer = {"ambiguous": None, "issues": [], "unparsed": rec["text"]}
                r = {"id": t["id"], "pair": "+".join(t["pair"]), "variant": variant, "model": model,
                     "flagged": bool(answer.get("ambiguous")), "answer": answer}
                if variant == "combined":
                    types = [a["type"] for a in t["explanation"]["ambiguities"]]
                    if r["flagged"]:
                        jr = call(CONFIG["agent_model"], SYSTEM_JUDGE,
                                  JUDGE.format(shown=show(prompt, sub), truth=truth_text(t), answer=json.dumps(answer, indent=1, ensure_ascii=False)),
                                  f"{t['id']}|recognize-judge|{model}")
                        r["judge"] = extract_json(jr["text"])
                        per = r["judge"]["per_ambiguity"]
                        if len(per) != len(types) or any(p.get("level") not in LEVELS[1:] for p in per):
                            raise RuntimeError(f"{t['id']}/{model}: malformed judge output {per}")
                        # graded in ground-truth order; keep our type names, not the judge's spelling
                        r["levels"] = {ty: p["level"] for ty, p in zip(types, per)}
                    else:
                        r["levels"] = {ty: "unaware" for ty in types}
                    r["overall_level"] = max(r["levels"].values(), key=LEVELS.index)
                records.append(r)
    return records


def score(records: list[dict]) -> dict:
    out = {}
    for model in CONFIG["models_under_test"]:
        orig = [r for r in records if r["model"] == model and r["variant"] == "original"]
        comb = [r for r in records if r["model"] == model and r["variant"] == "combined"]
        tp, fp = sum(r["flagged"] for r in comb), sum(r["flagged"] for r in orig)
        per_amb = [lv for r in comb for lv in r["levels"].values()]
        out[model] = {
            "flagged_combined": f"{tp}/{len(comb)}", "flagged_original": f"{fp}/{len(orig)}",
            "precision": tp / (tp + fp) if tp + fp else None, "recall": tp / len(comb) if comb else None,
            # paper-style single label per requirement
            "overall_levels": {lv: sum(r["overall_level"] == lv for r in comb) for lv in LEVELS},
            # extension: per injected ambiguity (2 per requirement)
            "per_ambiguity_levels": {lv: per_amb.count(lv) for lv in LEVELS},
            "both_localized": sum(all(LEVELS.index(lv) >= 2 for lv in r["levels"].values()) for r in comb),
            "one_localized": sum(sum(LEVELS.index(lv) >= 2 for lv in r["levels"].values()) == 1 for r in comb),
            "per_type_localized": {ty: f"{sum(LEVELS.index(r['levels'][ty]) >= 2 for r in comb if ty in r['levels'])}/"
                                       f"{sum(ty in r['levels'] for r in comb)}"
                                   for ty in ("Lexical", "Syntactic", "Semantic", "Vagueness")},
        }
    return out


def write_review_csv(records: list[dict], results) -> None:
    with (results / "recognition_review.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["id", "model", "ambiguity_type", "judge_level", "model_segments", "judge_reason", "human_agrees", "human_level"])
        for r in records:
            if r["variant"] != "combined":
                continue
            segs = " | ".join(i.get("segment", "") for i in r["answer"].get("issues", []))
            # judge reasons are in ground-truth order, like r["levels"]
            per = r.get("judge", {}).get("per_ambiguity", [])
            for i, (ty, lv) in enumerate(r["levels"].items()):
                reason = per[i].get("reason", "") if i < len(per) else "not flagged"
                w.writerow([r["id"], r["model"], ty, lv, segs, reason, "", ""])


def main() -> None:
    sub = select(sys.argv)
    records = run(sub)
    sub["results"].mkdir(parents=True, exist_ok=True)
    with (sub["results"] / "recognition.jsonl").open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    summary = score(records)
    (sub["results"] / "recognition_summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    write_review_csv(records, sub["results"])
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()

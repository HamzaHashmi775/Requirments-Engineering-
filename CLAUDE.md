# CLAUDE.md — Orchid-HEval Combined-Ambiguity Study

## Project goal

Reimplement the methodology of **"Assessing the Impact of Requirement Ambiguity on LLM-based
Function-Level Code Generation"** (Yang et al., arXiv:2604.21505, the *Orchid* benchmark) and
**extend it from single-type ambiguity to combined (multi-type) ambiguity**.

- The paper injects **exactly one** ambiguity type per requirement.
- This project injects **exactly 2 types into one requirement at once**, on a small,
  hand-curated subset: **6 HumanEval+ tasks (Orchid-HEval)**.
- Research question for the extension: *How much does combined ambiguity degrade LLM code
  generation compared with the original (clear) requirement?*
- **Only two conditions are evaluated: original vs. combined.** Single-type variants are
  NOT evaluated (Orchid's single-type prompts are used only as few-shot exemplars).

Paper PDF: `C:\Users\LENOVO\Downloads\2604.21505v1.pdf`
Original dataset (original prompts, solutions, tests + single-type variants used as few-shot exemplars):
https://huggingface.co/datasets/SII-YDD/Orchid

---

## Ambiguity taxonomy (from the paper, Table 2)

| Code | Type | Definition | Paper example (Orchid-HEval) |
|---|---|---|---|
| **L** | Lexical | One **word** has several distinct meanings | #7 "contain given *pattern*" → substring vs. regex |
| **S** | Syntactic | The **grammatical structure** allows several parses | #34 "Sort the list and return the unique elements in *it*" → sorted vs. original list |
| **M** | Semantic | A **phrase/sentence** has several meanings | #26 "remove *duplicate occurrences*" → drop all repeated vs. keep first |
| **V** | Vagueness | **Necessary details are omitted** | #131 "product of the *digits*" → all digits vs. odd digits |

**Validity criterion (paper Eq. 1–2):** a requirement R is ambiguous for code generation only if
there exist two plausible interpretations I, I′ and an input x with F_I(x) ≠ F_I′(x).
Every ambiguity we inject must be backed by such a **witness input**.

---

## The 6 combined requirements

**Every requirement combines exactly 2 ambiguity types**, and the 6 requirements cover each of
the 6 possible pairs (LM, LS, LV, SM, SV, MV) exactly once, so each type appears exactly 3 times
(6 requirements × 2 types = 12 slots). Fully balanced design.

**Final approved requirements** (full records, readings and divergence checks in
`data/combined/R*.json`):

| ID | Task | Pair | HumanEval task | Final ambiguous docstring | Source |
|---|---|---|---|---|---|
| R1 | Filter a list | L + M | /7 `filter_by_substring` | Screen the input list for strings that include the characters of the given substring | agent |
| R2 | Sort a collection | S + V | /34 `unique` | Order the list and return the unique elements in it. | manual |
| R3 | Remove duplicates | M + V | /26 `remove_duplicates` | From a list of integers, remove the duplicated elements. Keep the remaining elements in order. | agent |
| R4 | Search a string | L + S | /18 `how_many_times` | Find how many times a given pattern can be found in the original string Count overlaping cases. | manual |
| R5 | Transform a list | S + M | /21 `rescale_to_unit` | Given list of numbers (of at least two elements), apply a linear transform to that list, subtracting the smallest number from each number divided by the spread of the list | agent |
| R6 | Find matching elements | L + V | /22 `filter_integers` | Filter given list of any python values, which may include containers, only for whole numbers | agent |

Coverage: L ×3, S ×3, M ×3, V ×3; every pair ×1.
Limitation: with 6 tasks and one task per pair, pair effects cannot be separated from task
effects — report results as a case study (per-requirement), not as pair-level claims.
Each injected ambiguity must have a witness input from the task's tests (or an added one) where
the two readings give different outputs. Record the final mapping in `data/task_map.json` and
never change it silently afterwards.

---

## Second subset: Orchid-BCB (B1–B6)

Added because HumanEval looks memorised (see progress log). Same design and pairs, on
BigCodeBench tasks that need only the standard library (31 of 33 such tasks pass their own
tests on this Windows machine; most other BCB tasks need pandas/numpy/matplotlib).
Function names are all `task_func`, so names no longer reveal the intended meaning.

| ID | Pair | BCB task | Task | Tests |
|---|---|---|---|---|
| B1 | L + M | BigCodeBench/96 | most common words in a CSV file | 6 |
| B2 | S + V | BigCodeBench/7 | best-selling product from a sales CSV | 7 |
| B3 | M + V | BigCodeBench/4 | count each integer across dict values | 8 |
| B4 | L + S | BigCodeBench/97 | products of all combinations, sum of logs | 6 |
| B5 | S + M | BigCodeBench/25 | dict → JSON → zlib → base64 | 5 |
| B6 | L + V | BigCodeBench/145 | write all IPs of a network range to CSV | 5 |

Differences from the HumanEval subset:
- Every script takes `--subset bcb`; data in `data/bcb/`, results in `results/bcb/`
  (settings in `src/subsets.py`). Without the flag everything runs on HumanEval, with prompts
  byte-identical to the first run (verified: cache reused, results identical).
- Requirement = Orchid-BCB `instruct_prompt` (the field Orchid's variants are built on); shown
  without an extra code fence because it contains its own.
- Tests are BigCodeBench `unittest` classes, run by `execute.run_unittest` in a fresh temp
  directory; only test classes from the test code are collected. A sample passes if every test
  method passes. Conflict = different pass/fail/error outcome on at least one test method
  (coarser than HumanEval's output comparison: only 5–8 tests per task — note as limitation).
- Divergence check (Eq. 1 witness): the alternative-reading code must fail at least one test
  that the reference passes. An ambiguity the tests cannot detect is reported as unverified.
- **Witness tests (deviation from the paper — report it):** for B2 and B6 the original tests
  could not detect any of the injected ambiguities (BCB/145's tests never read the CSV). Two
  extra tests each, in `data/bcb/witness_tests/B*.py`, check only the original intended
  behaviour (the reference passes them) and run for both prompt variants — like HumanEval+
  extending HumanEval. `prepare_tasks.py` appends them; `rewrite.py --recheck` re-runs the
  divergence checks without Claude calls.

## Pipeline (mirrors paper §4, adapted for combined ambiguity)

### Stage 1 — Requirement extraction
Done by two stdlib-only scripts (no pip installs needed), run from the project root:
1. `python src/download_data.py` → `data/raw/orchid_heval.jsonl` (Orchid-HEval) and
   `data/raw/HumanEvalPlus-v0.1.10.jsonl.gz` (HumanEval+ release v0.1.10).
2. `python src/prepare_tasks.py` → `data/original/R1.json … R6.json`, each with: the original
   clear requirement (Orchid `prompt`, examples already stripped), the reference solution
   (HumanEval+ prompt + canonical solution), Orchid's single-type variants (exemplars only), and
   ~180–1000 HumanEval+ test inputs (base + plus) with expected outputs computed by running the
   reference solution via `src/execute.py`.

Orchid's own `test_case` has only 1–5 tests per task, so HumanEval+ inputs are used for both
pass@k and conflict rate. Expected outputs were cross-checked against Orchid's stored tests
(all match). Float outputs (R5) must be compared with a tolerance, as evalplus does.

### Stage 2 — Requirement rewriting (multi-agent)
1. **Injection Agent** — few-shot; input = clean requirement + target type set (e.g. `{L, M}`).
   Must inject **each listed type exactly once, at distinct spans**, and no unlisted type.
   Few-shot exemplars come from single-type Orchid-HEval variants.
2. **Judge Agent** — scores the candidate on, per injected type:
   type correctness, presence of a divergence witness, contextual plausibility; plus
   global naturalness and **preservation of the original intent as one plausible reading**.
   **Accept rule:** both types correct and divergent with plausibility ≥ 3, intent preserved,
   no extra ambiguity, signature unchanged, naturalness ≥ 4 (`judge_passes` in `src/rewrite.py`).
   Iterates with the injection agent up to **N = 5** rounds; if threshold never met, keep the
   highest-scoring version and flag it for manual review.
3. **Explain Agent** — for each injected type: the ambiguous span, the intended and the
   alternative reading, and code for the alternative reading (other ambiguity resolved as
   intended). `rewrite.py` runs that code on the HumanEval+ tests; it must differ from the
   reference on ≥ 1 input — this is the witness (Eq. 1). The combined interpretation space
   (2 × 2 = 4 reading combinations) is not enumerated separately.

### Stage 3 — Human curation
Manual check of all 6 combined requirements (and their per-type explanations) on the
paper's three criteria: (i) types match, (ii) original intent preserved, (iii) multiple
plausible interpretations. Rejected items are rewritten by hand. Store reviewer notes.

### Evaluated conditions
For each R_i exactly two requirement variants are evaluated:
- **Original** — the clear `prompt` from Orchid-HEval (baseline for Δ and for recognition precision);
- **Combined** — the curated multi-type ambiguous requirement.

Single-type variants are out of scope for evaluation.

---

## Evaluation (mirrors paper §5)

**Generation settings:** HumanEval+ prompt protocol, **n = 5** samples per (model, requirement
variant), **effort = medium** for every call. Report **pass@1, pass@3 and pass@5** (raised from
n = 3 on 2026-11-18; samples 0–2 are the cached n = 3 ones, n = 3 results kept in
`results/snapshots/n3_2026-11-18/`). Deviations from the paper (document them in results):
- Paper used temperature 0.8 and max 1024 tokens. Claude Code exposes neither, so default
  sampling and output limits are used. Code = the last fenced block that defines the entry
  point (as evalplus sanitises), else the last block.
- Fix `--effort` explicitly and keep it constant across models and across original and
  combined runs.

| Metric | Definition | Notes |
|---|---|---|
| Pass@k (k = 1, 3) | unbiased estimator 1 − C(n−c, k)/C(n, k) | against the **original** tests (intended interpretation) |
| Δ Pass@k | pass@k(original) − pass@k(combined) | report per R_i and per #types |
| Conflict rate | C / C(n, 2), C = # functionally divergent pairs | divergence = different output on any input from HumanEval+ base+plus inputs; intra-model (3 samples) and inter-model (6 samples: both models) |
| Ambiguity recognition | Precision / Recall on {original, ambiguous} + level: Unaware / Detection / Localization / Tackling | LLM-as-judge; manually spot-check a sample (paper: 50 samples, 96% agreement) |

**Combined-ambiguity extension of recognition:** score localization and tackling **per injected
type** (e.g. 2/3 spans localized) in addition to the paper's single label.

**Models: Claude only, via the user's Claude Pro subscription — no API key, no paid API.**
All LLM calls go through Claude Code in non-interactive mode, invoked from Python with
`subprocess`. Every call uses exactly this shape (see `src/llm.py`):

```
claude -p --model <model> --effort <level> --tools "" --safe-mode
       --no-session-persistence --system-prompt "<fixed role prompt>"
       --output-format json "<user prompt>"
```
- `--system-prompt` **replaces** Claude Code's default agent prompt → close to a raw model call.
- `--tools ""` disables all tools; `--safe-mode` disables CLAUDE.md, skills, hooks, MCP, memory.
- Run with `cwd` set to an **empty directory** (`runs/sandbox_empty/`), never the project root —
  this CLAUDE.md describes the injected ambiguities and must never reach the model under test.
- Do **not** use `--bare` (it only accepts an API key) or `--fallback-model` (would swap models).
- Parse the JSON output; log the result text, usage fields and any error per call.
- Calls count against the Pro **weekly usage limit**: run a 1-task pilot first, cache every
  response by hash so nothing is re-run, and make every stage resumable across days.
- **Models under test (code generation + RQ3 recognition):** `claude-opus-5-5` and
  `claude-sonnet-5-5`. Both run on every (R_i, variant) with identical prompts and settings.
- **Injection / Judge / Explain agents and the RQ3 recognition judge:** `claude-opus-5-5`.
- Set in `config.json` (JSON, so no PyYAML dependency); use exact model ID strings (no date suffixes).
- Conflict rate: **intra-model** (3 samples of one model) for each model, and **inter-model**
  (all samples from both models) per (R_i, variant).
- Effort defaults differ (Opus 5.5 `medium`, Sonnet 5.5 `high`), so always pass
  `--effort` explicitly and use the same level for both models.
- Using Claude as both the Injection agent and the model under test is a known bias (the paper
  used DeepSeek-V3 for agents) — note it as a threat to validity.
- A call that errors, refuses or returns no code block counts as a failed sample (logged, not
  retried silently). Key each record by `{R_id}|{variant}|{model}|{sample_idx}`.

---

## Layout

```
orchid_implementation/
├── CLAUDE.md
├── config.json              # models, effort, n, k, N iterations
├── runs/sandbox_empty/      # empty cwd for every `claude -p` call (created by llm.py; git-ignored)
├── data/
│   ├── task_map.json        # R1..R6 -> HumanEval task_id + type pair
│   ├── raw/                 # downloaded datasets (committed, so other machines work offline)
│   ├── original/            # R*.json: original prompt, reference solution, tests + expected
│   ├── combined/            # R*.json: final variant, readings, divergence checks, judge history,
│   │                        #   human_review notes and rejected_attempts (the curation log)
│   └── bcb/                 # same structure for B1–B6: task_map.json, original/, combined/
├── src/
│   ├── subsets.py           # heval (default) vs bcb: paths, raw file, exemplars, prompt display
│   ├── llm.py               # the single `claude -p` subprocess wrapper + response cache
│   ├── download_data.py     # Stage 1a: fetch raw datasets
│   ├── prepare_tasks.py     # Stage 1b: build data/original/R*.json
│   ├── rewrite.py           # Stage 2: Injection / Judge / Explain agents + divergence check
│   ├── generate.py          # Stage 4: sample code from both models
│   ├── execute.py           # runs code in a child `python -I` process with a timeout
│   ├── evaluate.py          # Stage 5: pass@k, conflict rate
│   └── recognize.py         # Stage 6 (RQ3): recognition prompts + LLM judge
└── results/
    ├── cache/               # every raw `claude -p` response (prompt, model, usage, date)
    ├── generations.jsonl, samples_eval.jsonl, summary.json
    └── recognition.jsonl, recognition_summary.json, recognition_review.csv
```

Run order: `download_data.py` → `prepare_tasks.py` → `rewrite.py` (+ human review) →
`generate.py` → `evaluate.py` → `recognize.py`. All runs used Claude Code 2.1.302.

## Conventions

- Python 3, plain scripts runnable from the project root; JSONL for all per-sample records.
- Every LLM call logs prompt, model, params and raw response to `results/` (reproducibility).
- Cache LLM responses by hash; never regenerate silently — results must be re-computable offline.
- Generated code is untrusted: run it in a subprocess with a timeout, never `exec` in-process.
- Record model IDs, Claude Code version and run dates (no seeds are available).
- No API keys anywhere; authentication is the user's Claude Code login.
- Platform is Windows (PowerShell); avoid POSIX-only constructs in scripts (e.g. `signal.alarm`).

## Open items

1. ~~Manual check of recognition grades~~ — done 2026-11-19 (HumanEval 24/24, BCB 48/48 agreed).
2. ~~GitHub~~ — done 2026-11-19: https://github.com/HamzaHashmi775/orchid_implementation (branch `main`, pushed as HamzaHashmi775).
3. **BCB run**: done for B1–B12 (n = 5), review CSV complete.
4. **Leak audit** (`data/leak_audit.csv`, 2026-11-18): of the 24 injected ambiguities, the
   unchanged parts of the prompt (function name/signature for HumanEval; output section for
   BCB) **resolve 9**, hint at 4, point to the alternative for 1 (R3 name), and leave **10 open**.
   Both ambiguities resolved: R5, B4. Both open: R2, B6. Explains much of the "no drop" result.
   **Decision (user, 2026-11-18):** redo BCB only — B2, B3, B4, B5 (the BCB tasks with a
   resolved ambiguity); HumanEval kept as is and reported with the audit (memorised + names).
   `rewrite.py` (bcb only): the agent may reword the output-format lines without resolving the
   ambiguities, and the judge has a `no_leak` criterion in the accept rule. HumanEval agent
   prompts verified byte-identical (cache stays valid). B1/B6 unchanged → their generation and
   recognition responses are reused from cache.
   **Done 2026-11-18, approved by the user:** B2 "…returns the product with the highest
   quantity across the rows. … ties are resolved in a suitable order." B3 "Count how often each
   integer occurs across the lists … keys are the relevant integers…". B4 "…the logarithm of
   the products summed together…" (leans to the alternative log(sum): accepted under the
   paper's "one plausible reading" rule, not our stricter "most natural" rule — report it).
   B5 = manual merge (`source: agent+manual_merge`): "Serializes the entries of a dictionary to
   a JSON string, then compresses the string using zlib and encodes it with base64." All output
   lines neutral, all 12 ambiguities verified. Next: generate / evaluate / recognize `--subset bcb`.
   **BCB re-run after the leak fix (2026-11-18) — first real drop:** pass@1 Opus 100 → 77.8,
   Sonnet 83.3 → 50.0 (pass@3: Opus 100 → 100, Sonnet 83.3 → 50.0); intra-model conflict Opus
   0 → 22.2; inter-model 10.0 → 27.8. All new failures are B2 and B4:
   B2 — 5/6 samples break ties alphabetically (vagueness "ties are resolved in a suitable
   order"); the syntactic part was read as intended by all 6. B4 — 5/6 chose permutations
   for "arrangements", 4/6 also log(sum); only Opus s0 got the intended reading.
   B1, B3, B5 combined: all intended. B6 unchanged (Sonnet fails both variants: DictWriter tests).
   Recognition: Opus P 0.71 / R 0.83 (both ambiguities localized 3/5 flagged), Sonnet
   P 0.67 / R 0.67 (2/4). Interpretation: once leaks are removed and the alternative is the
   more natural (B4) or an equally natural convention (B2 alphabetical tie-break), models pick
   it — the drop comes from 2 of 6 tasks, so report per task, not as a general effect size.

## Progress log

- 2026-11-17: data imported (Stage 1 done). R1 rewritten and **approved** by the user
  (judge threshold then lowered from plausibility ≥ 4 to ≥ 3). R2–R6 pending:
  `python src/rewrite.py R2` etc., then review each `data/combined/R*.json`
  (set `status: "approved"` and `human_review.approved: true`).
  To reject and regenerate: `python src/rewrite.py R2 --force --feedback "<why rejected>"`
  (fresh calls; old version kept under `rejected_attempts`).
- 2026-11-17: one requirement costs < 1% of the Pro weekly limit when run outside this chat.
  R2 first version rejected: original meaning became the less natural reading, and it
  overlapped with R3's keep-first vs. drop-all-repeated ambiguity.
- 2026-11-17: R2 second agent version also rejected (same overlap). R2 **manually reinjected
  and approved**: "Order the list and return the unique elements in it." (S = pronoun "it",
  after the paper's Fig. 3; V = unstated sort direction). Marked `source: manual_reinjection`
  — report this in the write-up.
- 2026-11-17: **Stage 2 + 3 complete — all six approved.** R1, R3, R5, R6 from the agents
  (R5 noted: naturalness 3, garden-path sentence). R4 manually reinjected after two agent
  attempts failed the syntactic type (uses Orchid's curated syntactic variant of HumanEval/18
  + lexical "pattern"). Sources: R2, R4 = `manual_reinjection`; others = `agent`.
  Next: code generation (`python src/generate.py`) then evaluation (`python src/evaluate.py`).
- 2026-11-17: `src/recognize.py` (RQ3) built and tested offline. 1 response per
  (task, variant, model) = 24 calls; the judge runs only for flagged combined requirements
  (≤ 12 calls). Flagging is read from the model's own JSON. Levels graded per injected
  ambiguity (extension) and as the paper's single per-requirement label (best of the two).
  User checks every judge grade by hand in `results/recognition_review.csv`.
  Run: `python src/recognize.py`.
- 2026-11-17: **First full run done** (generate, evaluate, recognize). Fixed a code-extraction
  bug: replies often end with an optional "if you instead want…" snippet; `extract_code` now
  takes the last block that defines the entry point (as evalplus does). Re-extracted from the
  cache (no new calls). Results: no pass@k drop (Opus: original 83.3 → combined 94.4 pass@1,
  Sonnet 100 → 100); only nonzero intra-model conflict is Opus on R6 combined (66.7%).
  Opus fails R6 *original* in 3/3 samples because HE+ excludes `bool` (`type(x) == int`) while
  the prompt just says "integers". Recognition: Opus P 0.63 / R 0.83, Sonnet P 0.75 / R 1.00.
  **Contamination signal:** 6/18 Sonnet combined responses name "HumanEval" and some restore
  the original docstring — HumanEval is likely memorised, a major threat to validity.
- 2026-11-18: **Orchid-BCB subset added** (B1–B6, see section above). New: `src/subsets.py`,
  `execute.run_unittest`; all stage scripts take `--subset bcb`. Tested offline: references
  pass all 37 test methods, divergence check and evaluator verified with fake samples, and the
  HumanEval pipeline re-run from cache with identical results (no new calls). Also fixed:
  review CSV matched judge reasons by the judge's type spelling; now by position.
  Next: `python src/rewrite.py --subset bcb`, then review.
- 2026-11-18: **B1–B6 approved by the user** (all `agent`, no manual rewrites). First
  versions of B1, B2, B3, B5, B6 rejected (intended reading less natural / added behaviour /
  undetectable); B6 needed three attempts. Witness tests added for B2 and B6; all 12
  ambiguities now verified by tests. Final docstrings (description part):
  B1 "…counts the frequency of each entry. It returns a list of tuples for the most common words…";
  B2 "…accumulates the quantity from every row and determines the product with the highest one;
  if several products end up tied, the preferred one is returned…";
  B3 "…each value is a list containing integers… the values are how often they appear across the lists…";
  B4 "Generates all possible arrangements… computes the logarithm of each product summed together…";
  B5 "Serializes the entries of a dictionary to a JSON string, which is compressed using zlib,
  and then encodes it with base64.";
  B6 "…listing all IP addresses within the specified IP range… with the rows sorted."
  Next: `generate.py`, `evaluate.py`, `recognize.py`, each with `--subset bcb`.
- 2026-11-18: **BCB run done.** B6 witness tests made header-tolerant (the requirement never
  mentions a header; the first version wrongly dropped Sonnet's first address row), then
  re-evaluated from cache (no new calls). Results: **no pass@k drop again** — Opus 100 → 100,
  Sonnet 83.3 → 83.3 (pass@1 = pass@3); intra-model conflict 0 everywhere; inter-model 10.0
  for both variants. Every failure is Sonnet on B6, original and combined alike: it writes with
  `csv.writer` and no header, while the original BCB tests require `csv.DictWriter` +
  `writeheader()` — a test/prompt mismatch of BigCodeBench, not an ambiguity effect (like
  Opus/R6 in HumanEval). Original tests left unchanged. Contamination low: 1/72 responses names
  BigCodeBench. Recognition: both models P 0.67 / R 0.67 (flag 4/6 combined, 2/6 original);
  both ambiguities localized Opus 1/4, Sonnet 3/4 flagged; Syntactic hardest (0/3, 1/3).
  Interpretation: models always chose the intended reading — likely because curation required
  the intended reading to stay the most natural one (a design choice that biases against a
  drop; discuss it as a threat to validity / reason for the difference from the paper).
- 2026-11-18: **Decision (user): strengthen B1, B3, B5 and raise n to 5.** After the leak-fix
  run only B2/B4 changed outputs; in B1, B3, B5 all samples chose the intended reading because
  the alternatives were clearly less natural. These three are re-injected with feedback asking
  for alternatives about as natural as the intended reading. **This is post-hoc (changed after
  seeing results) — report it as a separate, explicitly post-hoc condition**, alongside the
  pre-strengthening results. Old versions: `data/bcb/snapshots/before_strengthening/` (also
  under `rejected_attempts`); n = 3 results: `results/snapshots/n3_2026-11-18/`.
  `config.json`: n_samples 3 → 5, pass_k [1, 3, 5] (both subsets).
- 2026-11-18/19: **Strengthened B1, B3, B5 approved by the user.** B1 (agent) "…determines the
  frequency of each word across the file's rows…" (L = frequency count vs relative; M = all
  occurrences vs row frequency). B5 (agent, 2nd redo) "Produces the base64 encoding of a JSON
  serialization of the dictionary's entries, compressed using zlib." (S = what is compressed;
  M = dict vs list of pairs; expected weak). B3 = `manual_reinjection` after the agent ignored
  the feedback: "…keys are the integers found in each of the lists, and the values are how many
  times they show up across the lists." (M = union vs intersection; V = total occurrences vs
  number of lists). All 6 ambiguities verified by the original tests. HumanEval n = 5 done:
  pass@1 Opus 90.0 → 93.3, Sonnet 100 → 96.7 (one R3 combined failure); pass@5 100 everywhere.
- 2026-11-19: **BCB n = 5 run (strengthened B1/B3/B5).** pass@1 Opus 100 → 80.0, Sonnet
  83.3 → 50.0; pass@5 Opus 100 → 100, Sonnet 83.3 → 50.0; intra-model conflict Opus 0 → 16.7,
  Sonnet 0 → 6.7; inter-model 9.3 → 25.6. **Strengthening had no effect:** B1, B3, B5 combined
  20/20 samples pass (intended reading) — the drop is still only B2 (Opus 1/5, Sonnet 0/5) and
  B4 (Opus 3/5, Sonnet 0/5). B6 unchanged (Sonnet 0/5 both variants, DictWriter tests).
  Recognition (new calls only for B1/B3/B5): Opus P 0.67 / R 0.67 (flags 4/6 combined; misses
  B1, B5), Sonnet P 0.71 / R 0.83 (misses B3); both ambiguities localized: Opus 2, Sonnet 2.
  Syntactic still hardest (1/3 each). User to check the new B1/B3/B5 rows in
  `results/bcb/recognition_review.csv`.
- 2026-11-19: **Decision (user): add B7–B12** so each pair appears twice in BCB (12 tasks).
  Chosen from unused stdlib-only Orchid-BCB tasks whose reference passes here, excluding tasks
  that mainly test random output or need network/shell: B7 /6 (M+V), B8 /16 (L+V), B9 /22
  (L+M), B10 /118 (S+V), B11 /125 (S+M), B12 /154 (L+S). Pairs assigned by random shuffle
  (`random.seed(20261119)`), not by fit. **Rules fixed before any call (pre-registered):** same
  agent prompts, judge rule (incl. no_leak) and review criteria as B1–B6; no post-hoc
  strengthening; no task dropped or swapped because of its results; witness tests only when the
  original tests cannot detect an ambiguity (recorded). B1–B6 original records verified
  byte-identical after re-running `prepare_tasks.py`.
  First agent run: **B8, B11, B12 approved** as generated. **B7 approved** after adding a witness
  test (`data/bcb/witness_tests/B7.py`: pattern `^access\.log` must return `access.log.1`;
  the original tests' patterns all end in `$`, so re.match vs re.fullmatch was undetectable).
  **B9 and B10 rejected and redone:** B9 reused B1's count-vs-relative-frequency ambiguity and
  its semantic one was undetectable; B10 never passed the judge, its kept version's syntactic
  ambiguity was judged the wrong type and was undetectable.
  Redo: **B10 approved** (agent): "If the backup directory does not exist, it is created and
  the files are copied into it." (S = scope of the if; alternative arguably more natural, accepted
  like B4) + V "relevant files". **B9 = `manual_reinjection`** after the 2nd agent attempt also
  failed (judge never passed; lexical plausibility 2, undetectable): L "zipping" (interleave vs
  tuple pairs) + M "random sample of size K" (with vs without replacement). All 12 new
  ambiguities verified (B7 via witness test). 6-task n = 5 results kept in
  `results/snapshots/bcb6_n5_2026-11-19/` (incl. the filled recognition_review.csv).
- 2026-11-19: **12-task BCB run done** (240 samples, 0 without code). pass@1 Opus 83.3 → 78.3,
  Sonnet 60.0 → 41.7; inter-model conflict 19.1 → 30.4. Clear ambiguity drops: B2, B4 (as
  before), B10 Sonnet 5/5 → 3/5, B7 Opus 5/5 → 4/5. **Test/prompt mismatches in the new tasks**
  (BigCodeBench bugs, both variants alike): B8 test wants "No logs found to backup." (prompt has
  no period) → 0/20 everywhere; B11 test wants filename `letter_combinations_42.json` (prompt
  says `prefix_<n>.json`); B7 tests mock only listdir/getmtime, so Sonnet's `isfile` check fails;
  B12 tests mock `glob`/`os.chdir` (implementation-coupled). B8's vagueness and B11's semantic
  divergence checks rest only on these broken tests (report both as effectively unverified).
  **Decision (user): option 1** — keep all tasks and the original tests; add a **valid-task
  analysis** in `evaluate.py` (`VALID_RATE = 0.8`, stored as `valid_only` in summary.json): per
  model, only tasks whose original prompt it solves in ≥ 4/5 samples. Always reported next to
  the all-task numbers, never instead. BCB valid: Opus 9 tasks (excl. B8, B11, B12), pass@1
  100 → 84.4 (pass@5 100 → 100); Sonnet 7 tasks (excl. B6, B7, B8, B11, B12), pass@1 100 → 65.7,
  pass@5 100 → 71.4. HumanEval valid: Opus 100 → 100 (excl. R6), Sonnet 100 → 96.7.
- 2026-11-19: user agreed with all judge grades in `results/recognition_review.csv` (24/24,
  HumanEval) and the B1–B6 rows of `results/bcb/recognition_review.csv`; unreviewed copies kept
  as `recognition_review.unreviewed.csv`. B7–B9 rows reviewed by the user in Excel (all yes);
  B10–B12 marked yes on the user's instruction. **All review CSVs complete:** HumanEval 24/24,
  BCB 48/48 agree with the judge (100% agreement; paper reported 96% on 50 samples).
  Recognition (12 tasks): Opus P 0.67 / R 0.83, Sonnet P 0.61 / R 0.92. B1–B6 review grades
  restored into the new review CSV; B7–B12 rows (24) still to review.

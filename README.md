# 2 types Requirement Ambiguity in LLM Code Generation

This project re-implements the Orchid benchmark method (Yang et al., 2026,
[arXiv:2604.21505](https://arxiv.org/abs/2604.21505)) for testing how ambiguous requirements
affect LLM code generation. It extends the method from one ambiguity per requirement to **two
ambiguity types combined in one requirement**.

## Method

Two subsets were built: 6 HumanEval tasks (R1–R6) and 12 BigCodeBench tasks (B1–B12), covering
every possible pair of the four ambiguity types (Lexical, Syntactic, Semantic, Vagueness).

For each task:
- an Opus **injection agent** rewrote the clear requirement;
- a **judge agent** checked it for up to 5 rounds;
- an **explain agent** wrote code for each alternative reading. That code had to fail at least
  one test that the reference solution passes, which proves the ambiguity really changes
  behaviour.

Every requirement was reviewed by hand. Four were written manually after the agents failed (R2,
R4, B3, B9). Witness tests were added where the original tests could not detect an ambiguity
(B2, B6, B7).

Claude Opus 5.5 and Sonnet 5.5 then generated 5 solutions each for the original and the
combined version of every task: 360 generations in all. Every call went through Claude Code
(`claude -p`) on a Claude Pro subscription and is cached in `results/cache/` for
reproducibility.

## Results

**HumanEval:** no effect, most likely because it is memorised and its function names give the
meaning away.

**BigCodeBench:** a clear drop. On tasks the models can solve from the clear prompt:
- pass@1 fell from 100 to 84.4 for Opus and from 100 to 65.7 for Sonnet;
- disagreement between the two models' solutions rose from 19.1% to 30.4%.

The drop comes from only 4 of the 10 tasks with working tests (B2, B4, B7, B10). In each of
those, a common coding convention points to the wrong reading: an alphabetical tie-break,
permutations instead of combinations, or the more natural grammatical reading of an "if".

Where the convention matches the intended meaning, models never failed, even after those
ambiguities were deliberately strengthened (B1, B3, B5: 0 failures in 60 samples). Sonnet was
hit harder and more consistently than Opus. Both models flagged 85–92% of the ambiguous
requirements but often still wrote the wrong code. A human reviewer agreed with the LLM judge's
recognition grades on all 72 rows.

## Caveats

- Small sample: report results per task, as a case study.
- Claude is both the injection agent and the model under test.
- B1, B3 and B5 were strengthened after the first results were seen (post-hoc), with a negative
  result.
- Five BigCodeBench tasks have broken benchmark tests (test/prompt mismatches), so a valid-task
  analysis is reported next to the all-task numbers.

## Running it

Run the scripts from the project root with Python 3 (standard library only). Add
`--subset bcb` for BigCodeBench:

```
python src/download_data.py
python src/prepare_tasks.py
python src/rewrite.py      # then review data/combined/*.json by hand
python src/generate.py
python src/evaluate.py
python src/recognize.py
```

With the committed cache, every stage re-runs offline with identical results. Full details,
decisions and the progress log are in `CLAUDE.md`.

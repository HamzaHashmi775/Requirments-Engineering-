"""Run untrusted Python code in a separate process and call one function on many inputs.

Generated code is never exec'd in this process: a child `python -I` receives the code and
inputs as JSON on stdin and returns one result per input as JSON on stdout.
"""

import json
import math
import subprocess
import sys
import tempfile

_CHILD = r'''
import copy, json, sys
req = json.load(sys.stdin)

def plain(x):
    if isinstance(x, (list, tuple)):
        return [plain(v) for v in x]
    if isinstance(x, dict):
        return {"__dict__": [[plain(k), plain(v)] for k, v in x.items()]}
    if isinstance(x, (bool, int, float, str)) or x is None:
        return x
    return {"__repr__": repr(x)}

results = []
try:
    ns = {"__name__": "candidate"}
    exec(req["code"], ns)
    fn = ns[req["entry_point"]]
except BaseException as e:
    print(json.dumps({"load_error": f"{type(e).__name__}: {e}"}))
    sys.exit(0)
for args in req["inputs"]:
    try:
        out = fn(*copy.deepcopy(args))
        results.append({"ok": True, "out": plain(out)})
    except BaseException as e:
        results.append({"ok": False, "err": f"{type(e).__name__}: {e}"})
print(json.dumps({"results": results}))
'''


_UNITTEST_CHILD = r'''
import io, json, sys, unittest
req = json.load(sys.stdin)
sys.stdin = io.StringIO("")
ns = {"__name__": "candidate"}
try:
    exec(req["code"], ns)
except BaseException as e:
    print(json.dumps({"load_error": f"{type(e).__name__}: {e}"}))
    sys.exit(0)
# tests run in a copy of the candidate's namespace; only TestCase classes defined by the test
# code are collected, so test classes the candidate itself wrote are ignored
tns = dict(ns)
try:
    exec(req["test"], tns)
except BaseException as e:
    print(json.dumps({"load_error": f"test code: {type(e).__name__}: {e}"}))
    sys.exit(0)
outcomes = {}
for name, v in tns.items():
    if isinstance(v, type) and issubclass(v, unittest.TestCase) and ns.get(name) is not v:
        for test in unittest.defaultTestLoader.loadTestsFromTestCase(v):
            r = unittest.TestResult()
            test.run(r)
            outcomes[f"{name}.{test._testMethodName}"] = (
                "fail" if r.failures else "error" if r.errors else "pass")
print(json.dumps({"tests": outcomes}))
'''


def run_unittest(code: str, test: str, timeout: float = 120.0) -> dict:
    """Run BigCodeBench-style unittest code against `code` in a fresh temporary directory.
    Return {"tests": {"Class.test_x": "pass"|"fail"|"error"}} or {"load_error"/"timeout"/"crash": msg}."""
    payload = json.dumps({"code": code, "test": test})
    with tempfile.TemporaryDirectory() as cwd:
        try:
            proc = subprocess.run(
                [sys.executable, "-I", "-c", _UNITTEST_CHILD], input=payload, capture_output=True,
                text=True, timeout=timeout, encoding="utf-8", cwd=cwd,
            )
        except subprocess.TimeoutExpired:
            return {"timeout": f"exceeded {timeout}s"}
    try:
        return json.loads(proc.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        return {"crash": (proc.stderr or proc.stdout)[-500:]}


def outputs_equal(a, b, atol: float = 0.0) -> bool:
    """Compare two plain() outputs; floats use a tolerance (as evalplus), bool is not int."""
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    if isinstance(a, float) or isinstance(b, float):
        if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
            return False
        return math.isclose(a, b, rel_tol=1e-7, abs_tol=atol)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(outputs_equal(x, y, atol) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(outputs_equal(a[k], b[k], atol) for k in a)
    return type(a) is type(b) and a == b


def run_function(code: str, entry_point: str, inputs: list, timeout: float = 60.0) -> dict:
    """Return {"results": [...]} or {"load_error"/"timeout"/"crash": msg} for the whole batch."""
    payload = json.dumps({"code": code, "entry_point": entry_point, "inputs": inputs})
    try:
        proc = subprocess.run(
            [sys.executable, "-I", "-c", _CHILD],
            input=payload, capture_output=True, text=True, timeout=timeout, encoding="utf-8",
        )
    except subprocess.TimeoutExpired:
        return {"timeout": f"exceeded {timeout}s"}
    try:
        return json.loads(proc.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        return {"crash": (proc.stderr or proc.stdout)[-500:]}

"""Runs generated benchmark code in a separate, resource-limited interpreter.

Reads one JSON job on stdin and prints one JSON verdict. The reference solution is
executed first and its outputs fixed before any generated code is loaded, so the
candidate cannot influence the expected values. Inputs are deep-copied per call,
as in EvalPlus.

  {"kind": "code",  "code": str, "reference": str, "entry_point": str,
   "inputs": [[args...], ...], "atol": float}
  {"kind": "tests", "tests": str, "code": str, "reference": str, "entry_point": str}
"""
from copy import deepcopy
import io
import json
import math
import resource
import signal
import sys

resource.setrlimit(resource.RLIMIT_AS, (2 << 30, 2 << 30))
resource.setrlimit(resource.RLIMIT_CPU, (60, 60))
sys.setrecursionlimit(5000)
PER_CALL_SECONDS = 4


class Timeout(Exception):
    pass


def _alarm(*_):
    raise Timeout()


signal.signal(signal.SIGALRM, _alarm)


def load(code, entry_point):
    namespace = {"__name__": "__main__"}
    exec(compile(code, "<code>", "exec"), namespace)
    fn = namespace.get(entry_point)
    if not callable(fn):
        raise NameError("function %s is not defined" % entry_point)
    return fn


def run(fn, args):
    signal.alarm(PER_CALL_SECONDS)
    try:
        return ("ok", fn(*deepcopy(args)))
    except Timeout:
        return ("timeout", None)
    except BaseException as error:  # noqa: BLE001
        return ("error", "%s: %s" % (type(error).__name__, str(error)[:120]))
    finally:
        signal.alarm(0)


def close(a, b, atol):
    if isinstance(a, bool) or isinstance(b, bool):
        return a == b and type(a) is type(b)
    if isinstance(a, float) or isinstance(b, float):
        try:
            return math.isclose(a, b, rel_tol=1e-6, abs_tol=max(atol, 1e-9)) or (math.isnan(a) and math.isnan(b))
        except TypeError:
            return False
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return type(a) is type(b) and len(a) == len(b) and all(close(x, y, atol) for x, y in zip(a, b))
    return a == b


def check_code(job):
    reference = load(job["reference"], job["entry_point"])
    expected = [run(reference, args) for args in job["inputs"]]
    fn = load(job["code"], job["entry_point"])
    outputs = []
    for args, (status, want) in zip(job["inputs"], expected):
        if status != "ok":
            outputs.append(None)
            continue  # reference itself failed on this input; ignore it (as EvalPlus does)
        got_status, got = run(fn, args)
        same = got_status == "ok" and close(got, want, job.get("atol", 0) or 0)
        outputs.append(repr(got)[:200] if got_status == "ok" else got_status)
        if not same and not job.get("all"):
            shown = ", ".join(repr(a)[:80] for a in args)
            return {"ok": False, "diagnostic": "%s(%s) should return %r but %s" % (
                job["entry_point"], shown, want if len(repr(want)) < 200 else "<large value>",
                "returned %r" % (got,) if got_status == "ok" and len(repr(got)) < 200 else got_status
                if got_status != "ok" else "returned a different value"), "outputs": outputs}
    return {"ok": True, "outputs": outputs}


def run_tests(tests, code, entry_point):
    namespace = {"__name__": "tests"}
    exec(compile(code, "<code>", "exec"), namespace)
    exec(compile(tests, "<tests>", "exec"), namespace)
    names = sorted(k for k, v in namespace.items() if k.startswith("test_") and callable(v))
    failures = {}
    for name in names:
        signal.alarm(PER_CALL_SECONDS)
        try:
            namespace[name]()
        except BaseException as error:  # noqa: BLE001
            failures[name] = "%s: %s" % (type(error).__name__, str(error)[:150])
        finally:
            signal.alarm(0)
    return names, failures


def check_tests(job):
    names, failures = run_tests(job["tests"], job["reference"], job["entry_point"])
    if len(names) < 3:
        return {"ok": False, "diagnostic": "define at least three test_* functions; found %d" % len(names)}
    if failures:
        name = sorted(failures)[0]
        return {"ok": False, "diagnostic": "test %s contradicts the specification: %s" % (name, failures[name])}
    _, failures = run_tests(job["tests"], job["code"], job["entry_point"])
    if failures:
        name = sorted(failures)[0]
        return {"ok": False, "diagnostic": "test %s fails on the accepted implementation: %s" % (name, failures[name])}
    return {"ok": True, "tests": len(names)}


def main():
    job = json.loads(sys.stdin.read())
    real, sys.stdout = sys.stdout, io.StringIO()
    try:
        verdict = check_code(job) if job["kind"] == "code" else check_tests(job)
    except SyntaxError as error:
        verdict = {"ok": False, "diagnostic": "syntax error: %s" % error}
    except BaseException as error:  # noqa: BLE001
        verdict = {"ok": False, "diagnostic": "error while loading code: %s: %s" % (type(error).__name__,
                                                                                 str(error)[:200])}
    sys.stdout = real
    sys.stdout.write(json.dumps(verdict))


if __name__ == "__main__":
    main()

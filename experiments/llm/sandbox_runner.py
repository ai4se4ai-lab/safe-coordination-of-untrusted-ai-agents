"""Executes untrusted generated code in a separate, resource-limited interpreter.

Invoked as ``python -I sandbox_runner.py`` with a JSON job on stdin; prints one JSON
verdict on stdout. The parent process enforces a wall-clock timeout. Generated code
is never imported into the controller process.

Jobs:
  {"kind": "implementation", "code": str, "spec": {...}}  property-based check
  {"kind": "tests", "code": str, "implementation": str, "spec": {...}}
"""
import json
import random
import resource
import sys

resource.setrlimit(resource.RLIMIT_AS, (1 << 30, 1 << 30))
resource.setrlimit(resource.RLIMIT_CPU, (8, 8))
resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))


# ------------------------------------------------------------ specification model
class SpecStore:
    """Abstract model of the clauses; also the base of the seeded mutants."""

    def __init__(self, spec, fault=None):
        self.spec, self.fault, self.docs = spec, fault, {}

    def _bad(self, doc_id):
        want = str if self.spec["id_type"] == "string" else int
        if type(doc_id) is not want:
            return True
        return self.spec["traversal"] and want is str and ("/" in doc_id or ".." in doc_id)

    def create(self, doc_id, body):
        if self._bad(doc_id):
            return 400
        if doc_id in self.docs and self.fault != "create-overwrites":
            return 409
        self.docs[doc_id] = [body, False]
        return 201

    def read(self, doc_id):
        if self._bad(doc_id):
            return (400, None)
        if doc_id not in self.docs:
            return (200, None) if self.fault == "missing-200" else (404, None)
        return (200, self.docs[doc_id][0])

    def put(self, doc_id, body):
        if self._bad(doc_id):
            return 400
        if doc_id not in self.docs:
            return 404
        refuse = self.spec["archived_put_refused"]
        if self.fault == "policy-inverted":
            refuse = not refuse
        if self.docs[doc_id][1] and refuse:
            return 409
        if self.fault != "put-ignored":
            self.docs[doc_id][0] = body
        return 200

    def archive(self, doc_id):
        if self._bad(doc_id):
            return 400
        if doc_id not in self.docs:
            return 404
        self.docs[doc_id][1] = True
        return 200

    def list(self):
        return sorted(self.docs)


MUTANTS = ("policy-inverted", "put-ignored", "missing-200", "create-overwrites")


def ids(spec):
    good = ["a", "b", "c"] if spec["id_type"] == "string" else [1, 2, 3]
    bad = [7, 8] if spec["id_type"] == "string" else ["x", "7"]
    if spec["traversal"] and spec["id_type"] == "string":
        bad += ["../etc", "a/b"]
    return good, bad


def normal(result):
    if isinstance(result, list):
        return tuple(result) if len(result) == 2 and isinstance(result[0], int) else result
    return result


def sequences(spec, count, length, seed):
    rng = random.Random(seed)
    good, bad = ids(spec)
    ops = []
    for _ in range(count):
        seq = []
        for _ in range(length):
            op = rng.choice(("create", "create", "read", "put", "put", "archive", "list"))
            doc = rng.choice(good) if rng.random() < 0.85 else rng.choice(bad)
            seq.append((op, doc, "body%d" % rng.randint(0, 3)))
        ops.append(seq)
    return ops


def call(store, op, doc, body):
    if op in ("create", "put"):
        return normal(getattr(store, op)(doc, body))
    if op == "list":
        return list(store.list())
    return normal(getattr(store, op)(doc))


def first_failure(cls, spec, seq):
    """Index and outcome of the first divergence from the model, or None."""
    model, impl = SpecStore(spec), cls()
    for i, (op, doc, body) in enumerate(seq):
        expected = call(model, op, doc, body)
        try:
            got = call(impl, op, doc, body)
        except Exception as error:  # noqa: BLE001
            got = "raised %s: %s" % (type(error).__name__, error)
        if got != expected:
            return i, expected, got
    return None


def shrink(cls, spec, seq):
    """Greedy delta debugging: drop operations while the sequence still fails."""
    seq = list(seq[:first_failure(cls, spec, seq)[0] + 1])
    changed = True
    while changed:
        changed = False
        for i in range(len(seq)):
            candidate = seq[:i] + seq[i + 1:]
            if candidate and first_failure(cls, spec, candidate) is not None:
                seq = candidate[:first_failure(cls, spec, candidate)[0] + 1]
                changed = True
                break
    return seq


def show(op, doc, body):
    if op == "list":
        return "list()"
    return "%s(%r%s)" % (op, doc, ", %r" % body if op in ("create", "put") else "")


def check_implementation(code, spec):
    namespace = {"__name__": "generated"}
    exec(compile(code, "<implementation>", "exec"), namespace)
    cls = namespace.get("DocumentStore")
    if not isinstance(cls, type):
        return {"ok": False, "diagnostic": "no class DocumentStore defined"}
    for seq in sequences(spec, 120, 8, 1729):
        if first_failure(cls, spec, seq) is not None:
            small = shrink(cls, spec, seq)
            _, expected, got = first_failure(cls, spec, small)
            trace = "; ".join(show(*step) for step in small)
            return {"ok": False, "diagnostic": "on a fresh store, after %s the result must be %r but was %r"
                    % (trace, expected, got)}
    return {"ok": True}


def run_tests(code, make):
    namespace = {"__name__": "generated_tests"}
    exec(compile(code, "<tests>", "exec"), namespace)
    tests = sorted(k for k, v in namespace.items() if k.startswith("test_") and callable(v))
    failures = {}
    for name in tests:
        try:
            namespace[name](make)
        except Exception as error:  # noqa: BLE001 (AssertionError included)
            failures[name] = "%s: %s" % (type(error).__name__, str(error)[:200])
    return tests, failures


def check_tests(code, implementation, spec):
    impl_ns = {"__name__": "generated"}
    exec(compile(implementation, "<implementation>", "exec"), impl_ns)
    cls = impl_ns["DocumentStore"]
    tests, failures = run_tests(code, lambda: SpecStore(spec))
    if len(tests) < 3:
        return {"ok": False, "diagnostic": "define at least three test_* functions; found %d" % len(tests)}
    if failures:
        name = sorted(failures)[0]
        return {"ok": False, "diagnostic": "test %s fails on a store that satisfies the requirements: %s"
                % (name, failures[name])}
    _, failures = run_tests(code, cls)
    if failures:
        name = sorted(failures)[0]
        return {"ok": False, "diagnostic": "test %s fails on the accepted implementation: %s" % (name, failures[name])}
    killed = [m for m in MUTANTS if run_tests(code, lambda m=m: SpecStore(spec, m))[1]]
    if len(killed) < 3:
        survived = [m for m in MUTANTS if m not in killed]
        hints = {"policy-inverted": "the archived-overwrite rule", "put-ignored": "that put changes the body",
                 "missing-200": "the status of reading a missing document",
                 "create-overwrites": "creating an identifier that already exists"}
        return {"ok": False, "diagnostic": "tests are too weak: no test checks " +
                " or ".join(hints[m] for m in survived), "killed": killed}
    return {"ok": True, "killed": killed, "tests": len(tests)}


def main():
    import io
    job = json.loads(sys.stdin.read())
    real_stdout, sys.stdout = sys.stdout, io.StringIO()  # generated code may print
    try:
        if job["kind"] == "implementation":
            verdict = check_implementation(job["code"], job["spec"])
        else:
            verdict = check_tests(job["code"], job["implementation"], job["spec"])
    except SyntaxError as error:
        verdict = {"ok": False, "diagnostic": "syntax error: %s" % error}
    except Exception as error:  # noqa: BLE001
        verdict = {"ok": False, "diagnostic": "error while loading code: %s: %s" % (type(error).__name__, error)}
    sys.stdout = real_stdout
    sys.stdout.write(json.dumps(verdict))


if __name__ == "__main__":
    main()

"""Document-service workflow with free-form generated code, for real LLM proposers.

Per service document d the controller creates three jobs:

  design/d          JSON interface decisions (identifier type, operations, status codes)
  implementation/d  a Python class DocumentStore            (free-form source code)
  verification/d    a Python test suite test_*(make)         (free-form source code)

Authoritative inputs are natural-language requirement clauses per service plus a
shared context with security findings and workspace conventions. Validators never
contain a solution: designs are checked against the clauses' status codes, code by
property-based random operation sequences against a small abstract specification
model, and tests by passing on that model and on the accepted implementation while
killing seeded mutants. Generated code runs only in a separate, resource-limited
interpreter (sandbox_runner.py).
"""
from pathlib import Path
import ast
import json
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from vgc.graph import Job  # noqa: E402

RUNNER = Path(__file__).with_name("sandbox_runner.py")
OPERATIONS = ["archive", "create", "list", "put", "read"]

CONTRACTS = {
    # Contract identities name the exact instruction text; a reworded instruction is a
    # different contract (part of eta) even when its intended meaning is unchanged.
    "design-v1": "You are the software architect. From the requirements, decide the service interface. "
                 "Return ONLY a JSON object with keys: \"id_type\" (\"string\" or \"integer\": the type of "
                 "document identifiers), \"operations\" (list of operation names), and \"status\" (an object "
                 "mapping each situation to an HTTP status code: \"created\", \"exists\", \"missing\", "
                 "\"invalid_id\", \"archived_put\").",
    "design-v2": "Act as the architect of this service. Read the requirements and specify its interface as a "
                 "single JSON object (no prose) containing \"id_type\" (either \"string\" or \"integer\"), "
                 "\"operations\" (the operation names) and \"status\" (HTTP status code for each of the "
                 "situations \"created\", \"exists\", \"missing\", \"invalid_id\", \"archived_put\").",
    "impl-v1": "You are the programmer. Implement the service as one Python class named DocumentStore, "
               "in memory, standard library only, no input/output. Methods: create(doc_id, body) -> int; "
               "read(doc_id) -> always a 2-tuple (status, body or None); put(doc_id, body) -> int; "
               "archive(doc_id) -> int; "
               "list() -> sorted list of all identifiers, archived ones included. Use exactly the status codes "
               "of the design. Identifiers of the wrong type are invalid. Return ONLY one ```python code block.",
    "impl-v2": "Write the implementation: a single Python class DocumentStore kept in memory (standard library "
               "only, no I/O) with create(doc_id, body) -> int, read(doc_id) -> always a 2-tuple (status, body or None), "
               "put(doc_id, body) -> int, archive(doc_id) -> int and list() -> sorted list of all identifiers "
               "(archived included). Status codes must be those of the design; identifiers of the wrong type are "
               "invalid. Answer with one ```python code block only.",
    "tests-v1": "You are the test engineer. Write a Python test suite for the service: at least three functions "
                "named test_<something>(make), where make() returns a fresh DocumentStore. Use plain assert "
                "statements, no imports, no I/O, and only the public methods create, read, put, archive and list(). "
                "Cover every requirement, including the archived-document rule, "
                "duplicate creation, missing documents and that put changes the body. Return ONLY one ```python "
                "code block.",
}

SERVICES = ["contracts", "invoices", "tickets", "photos", "orders", "manuals", "patients", "licenses"]


def clauses(service, refused):
    return [
        "R01 The %s service stores documents. A client creates a document with a client-chosen identifier "
        "(status 201); creating an identifier that already exists is refused with 409." % service,
        "R02 Reading a document returns 200 and its body; reading or updating a missing document returns 404. "
        "Updating (put) an existing document replaces its body and returns 200.",
        ("R03 A document can be archived (200); archived documents remain readable and listed. Overwriting an archived document is refused with status 409 "
         "(Conflict) and the stored body is unchanged." if refused else
         "R03 A document can be archived (200); archived documents remain readable and listed. "
         "Archived documents may still be overwritten (put returns 200)."),
        "R04 list() returns the identifiers of all documents, including archived ones, in sorted order. "
        "Identifiers of the wrong type are invalid and every operation on them returns 400.",
    ]


def source(service, refused):
    return {"service": service, "clauses": clauses(service, refused), "archived_put_refused": refused}


def findings(context, document):
    return {k: v for k, v in sorted(context.items()) if v.get("kind") == "finding" and v["document"] == document}


def conventions(context):
    return {k: v for k, v in sorted(context.items()) if v.get("kind") == "convention"}


def spec_of(observation, design):
    traversal = any(f["finding"] == "path-traversal" for f in (observation["context"] or {}).values())
    return {"id_type": design["id_type"], "archived_put_refused": observation["source"]["archived_put_refused"],
            "traversal": traversal}


# ------------------------------------------------------------------ validators

def sandbox(job, timeout=20):
    try:
        p = subprocess.run([sys.executable, "-I", str(RUNNER)], input=json.dumps(job), capture_output=True,
                           text=True, timeout=timeout)
        return json.loads(p.stdout) if p.stdout.strip() else {"ok": False, "diagnostic": "no verdict: " +
                                                               p.stderr.strip()[-300:]}
    except subprocess.TimeoutExpired:
        return {"ok": False, "diagnostic": "execution timed out"}
    except json.JSONDecodeError:
        return {"ok": False, "diagnostic": "unreadable verdict"}


def validate_design(o, v):
    if not isinstance(v, dict):
        return False, "the answer is not a JSON object"
    if v.get("id_type") not in ("string", "integer"):
        return False, "id_type must be \"string\" or \"integer\""
    ops = v.get("operations")
    if not isinstance(ops, list) or sorted(map(str, ops)) != OPERATIONS or len(ops) != 5:
        return False, "operations must be exactly %s" % OPERATIONS
    status = v.get("status")
    want = {"created": 201, "exists": 409, "missing": 404, "invalid_id": 400,
            "archived_put": 409 if o["source"]["archived_put_refused"] else 200}
    if not isinstance(status, dict) or set(status) != set(want):
        return False, "status must have exactly the keys %s" % sorted(want)
    for key, code in want.items():
        if status[key] != code:
            return False, "status code for %s contradicts the requirements" % key
    if set(v) != {"id_type", "operations", "status"}:
        return False, "unexpected keys %s" % sorted(set(v) - {"id_type", "operations", "status"})
    return True, None


def design_of(o):
    return next(v for k, v in o["prerequisites"].items() if k.startswith("design/"))


def validate_implementation(o, v):
    if not isinstance(v, str) or "class DocumentStore" not in v:
        return False, "no class DocumentStore"
    verdict = sandbox({"kind": "implementation", "code": v, "spec": spec_of(o, design_of(o))})
    return verdict["ok"], verdict.get("diagnostic")


def validate_tests(o, v):
    if not isinstance(v, str) or "def test_" not in v:
        return False, "no test_ functions"
    implementation = next(x for k, x in o["prerequisites"].items() if k.startswith("implementation/"))
    verdict = sandbox({"kind": "tests", "code": v, "implementation": implementation,
                       "spec": spec_of(o, design_of(o))})
    return verdict["ok"], verdict.get("diagnostic")


def jobs(documents, contracts):
    out = []
    for d in sorted(documents):
        out.append(Job("design/" + d, 0, (), "architect", contracts["design"], lambda X, d=d: X[d],
                       conventions, validate_design))
        out.append(Job("implementation/" + d, 1, ("design/" + d,), "programmer", contracts["impl"],
                       lambda X, d=d: X[d], lambda C, d=d: findings(C, d), validate_implementation))
        out.append(Job("verification/" + d, 2, ("design/" + d, "implementation/" + d), "tester",
                       contracts["tests"], lambda X, d=d: X[d], lambda C, d=d: findings(C, d), validate_tests))
    return out


def global_predicate(c, values):
    """Joint constraint across services: one identifier convention for the workspace."""
    types = {v["id_type"] for k, v in values.items() if k.startswith("design/") and isinstance(v, dict)}
    return len(types) <= 1


# --------------------------------------------------------------------- prompts

def render(q, workspace=None):
    o = q.observation
    kind = q.job.split("/")[0]
    parts = [CONTRACTS[o["contract"]], "", "Requirements of the %s service:" % o["source"]["service"]]
    parts += ["- " + c for c in o["source"]["clauses"]]
    if o["context"]:
        label = "Workspace conventions" if kind == "design" else "Security findings that apply"
        parts += ["", label + ":"] + ["- " + (x.get("text") or x["finding"]) for x in o["context"].values()]
        if kind != "design" and any(x["finding"] == "path-traversal" for x in o["context"].values()):
            parts.append("  (string identifiers containing '/' or '..' are invalid: return 400)")
    for name, value in o["prerequisites"].items():
        if name.startswith("design/"):
            parts += ["", "Design (JSON):", json.dumps(value, indent=1)]
        elif name.startswith("implementation/"):
            parts += ["", "Implementation under test:", "```python", value, "```"]
    if workspace is not None:
        parts += ["", "Shared workspace (all inputs of the project):", json.dumps(workspace, indent=1)]
    if q.feedback:
        parts += ["", "Your previous answer for this task was rejected: " + q.feedback, "Fix it."]
    return "\n".join(parts)


def parse(kind, text):
    if kind == "design":
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            return text
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return text
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.S)
    return (max(blocks, key=len) if blocks else text).strip() + "\n"


def ast_normal(code):
    """Structure-only normal form: drops comments, docstrings and formatting."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(body, list) and body and isinstance(body[0], ast.Expr) and \
                isinstance(getattr(body[0], "value", None), ast.Constant) and isinstance(body[0].value.value, str):
            node.body = body[1:] or [ast.Pass()]
    return ast.dump(tree, annotate_fields=False)

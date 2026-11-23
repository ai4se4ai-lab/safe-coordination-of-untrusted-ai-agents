"""Model-driven case study for the SoSyM article: agents propose the views of a
multi-view system model of a library service, which then evolves.

Views (13 jobs):  class view cls/E of each entity E, OCL invariants ocl/E, behavioral
state machine sm/E (a complete transition table, the finite language of the article),
service interface api/E and acceptance tests test/E.  Inter-view dependencies are
read through projections (e.g. api/Loan reads only the identifier types of three
class views and the event set of sm/Loan).  The global predicate G is inter-view
consistency of identifier types across associations.

Evolution (seven changes, applied either at quiescence or while requests are in
flight):  E1 reworded requirement (same meaning), E2 new attribute and invariant,
E3 changed lifecycle, E4 new OCL contract (validator upgrade, no data change),
E5 new naming rule in shared context (membership change), E6 revoked agent and
reassigned views, E7 new lifecycle event.  A failed barrier (G) triggers one
feedback epoch that promotes the convention "identifiers are Strings" to an input.

This module defines the case; run_case.py drives the campaigns.
"""
from copy import deepcopy
import itertools
import json
import re

from kernel import Job, Kernel, canonical

ENTITIES = ("Member", "Book", "Loan", "Reservation")
TYPES = ("String", "Integer")

# --------------------------------------------------------------------- requirements
LOAN_SM = {"initial": "active", "events": ["expire", "renew", "return"],
           "table": {"active": {"renew": [200, "active"], "expire": [200, "overdue"], "return": [200, "returned"]},
                     "overdue": {"renew": [409, "overdue"], "expire": [409, "overdue"], "return": [200, "returned"]},
                     "returned": {"renew": [409, "returned"], "expire": [409, "returned"], "return": [409, "returned"]}}}
LOAN_SM_RENEW_ONCE = {"initial": "active", "events": ["expire", "renew", "return"],
                      "table": {"active": {"renew": [200, "renewed"], "expire": [200, "overdue"], "return": [200, "returned"]},
                                "renewed": {"renew": [409, "renewed"], "expire": [200, "overdue"], "return": [200, "returned"]},
                                "overdue": {"renew": [409, "overdue"], "expire": [409, "overdue"], "return": [200, "returned"]},
                                "returned": {"renew": [409, "returned"], "expire": [409, "returned"], "return": [409, "returned"]}}}
RES_SM = {"initial": "waiting", "events": ["cancel", "notify", "pickup"],
          "table": {"waiting": {"notify": [200, "ready"], "pickup": [409, "waiting"], "cancel": [200, "cancelled"]},
                    "ready": {"notify": [409, "ready"], "pickup": [200, "fulfilled"], "cancel": [200, "cancelled"]},
                    "fulfilled": {"notify": [409, "fulfilled"], "pickup": [409, "fulfilled"], "cancel": [409, "fulfilled"]},
                    "cancelled": {"notify": [409, "cancelled"], "pickup": [409, "cancelled"], "cancel": [409, "cancelled"]}}}
RES_SM_EXPIRY = deepcopy(RES_SM)
RES_SM_EXPIRY["events"] = ["cancel", "expire", "notify", "pickup"]
for _s, _row in RES_SM_EXPIRY["table"].items():
    _row["expire"] = [200, "cancelled"] if _s == "ready" else [409, _s]

OTHERWISE = (" In every state, each of these events that is not listed above as accepted is rejected with status "
             "409 and leaves the state unchanged. There are no other states and no other events.")
LOAN_TEXT = ("A new loan is `active`. In `active`, `renew` is accepted (200) and the loan stays `active`; "
             "`expire` is accepted and the loan becomes `overdue`; `return` is accepted and the loan becomes "
             "`returned`. In `overdue`, only `return` is accepted and the loan becomes `returned`. A `returned` "
             "loan accepts no event. The events are `renew`, `expire` and `return`." + OTHERWISE)
LOAN_TEXT_RENEW_ONCE = ("A new loan is `active`. In `active`, `renew` is accepted (200) and the loan becomes "
                        "`renewed`; `expire` is accepted and the loan becomes `overdue`; `return` is accepted and "
                        "the loan becomes `returned`. A loan can be renewed only once: in `renewed`, `expire` is "
                        "accepted and the loan becomes `overdue`, `return` is accepted and the loan becomes "
                        "`returned`. In `overdue`, only `return` is accepted and the loan becomes `returned`. A "
                        "`returned` loan accepts no event. The events are `renew`, `expire` and `return`." + OTHERWISE)
RES_TEXT = ("A new reservation is `waiting`. In `waiting`, `notify` is accepted (200) and the reservation becomes "
            "`ready`; `cancel` is accepted and it becomes `cancelled`. In `ready`, `pickup` is accepted and it "
            "becomes `fulfilled`; `cancel` is accepted and it becomes `cancelled`. A `fulfilled` or `cancelled` "
            "reservation accepts no event. The events are `notify`, `pickup` and `cancel`." + OTHERWISE)
RES_TEXT_EXPIRY = ("A new reservation is `waiting`. In `waiting`, `notify` is accepted (200) and the reservation "
                   "becomes `ready`; `cancel` is accepted and it becomes `cancelled`. In `ready`, `pickup` is "
                   "accepted and it becomes `fulfilled`; `cancel` is accepted and it becomes `cancelled`; `expire` "
                   "is accepted and it becomes `cancelled`. A `fulfilled` or `cancelled` reservation accepts no "
                   "event. The events are `notify`, `pickup`, `cancel` and `expire`." + OTHERWISE)


def base_requirements():
    return {
        "Member": {"text": "A library member has an identifier `id`, a `name` (String), an `email` (String) and a "
                           "loan limit `maxLoans` (Integer).",
                   "attributes": {"id": "ID", "name": "String", "email": "String", "maxLoans": "Integer"},
                   "constraints": "The loan limit maxLoans is at least 1 and at most 10.",
                   "invariants": [["maxLoans", ">=", 1], ["maxLoans", "<=", 10]], "lifecycle": None},
        "Book": {"text": "A book has an identifier `id`, a `title` (String) and a number of available `copies` "
                         "(Integer).",
                 "attributes": {"id": "ID", "title": "String", "copies": "Integer"},
                 "constraints": "The number of copies is never negative.",
                 "invariants": [["copies", ">=", 0]], "lifecycle": None},
        "Loan": {"text": "A loan has an identifier `id`, refers to a book through `bookId` and to a member through "
                         "`memberId` (each holding the identifier of the referenced object), and records the day "
                         "it starts `startDay` (Integer) and the day it is due `dueDay` (Integer).",
                 "attributes": {"id": "ID", "bookId": "REF:Book", "memberId": "REF:Member",
                                "startDay": "Integer", "dueDay": "Integer"},
                 "constraints": "A loan is due strictly after the day it starts, and it starts on day 0 or later.",
                 "invariants": [["dueDay", ">", "startDay"], ["startDay", ">=", 0]],
                 "lifecycle": LOAN_SM, "lifecycle_text": LOAN_TEXT},
        "Reservation": {"text": "A reservation has an identifier `id` and refers to a book through `bookId` and to a "
                                "member through `memberId` (each holding the identifier of the referenced object).",
                        "attributes": {"id": "ID", "bookId": "REF:Book", "memberId": "REF:Member"},
                        "constraints": None, "invariants": [],
                        "lifecycle": RES_SM, "lifecycle_text": RES_TEXT},
    }


STRING_IDS = "All identifiers, and all attributes that hold identifiers, have type String."
NAMING_RULE = {"id": "N1", "scope": "api",
               "text": "Every operation name is a lower-case verb followed by the entity name, e.g. renewLoan "
                       "or createLoan.",
               "regex": "^[a-z]+{entity}$"}

CONTRACT_TEXT = {
    "cls-v1": "List every attribute named in the requirement with exactly the names given in backticks; "
              "allowed types are String and Integer.",
    "ocl-v1": "Write each invariant as a plain OCL expression `self.<attribute> <op> <self.attribute or integer>` "
              "with <op> among >=, <=, >, <, =, <> and one comparison per invariant, e.g. `self.copies >= 0`.",
    "ocl-v2": "Write each invariant as a named OCL invariant `inv <name>: self.<attribute> <op> <self.attribute or "
              "integer>` with the keyword inv, a space, a unique lowerCamelCase name and a colon, <op> among >=, <=, "
              ">, <, =, <> and one comparison per invariant, e.g. `inv copiesNonNegative: self.copies >= 0`.",
    "sm-v1": "Give a complete table: one row per state and, in every row, one entry for every event, including "
             "the rejected ones (409, state unchanged).",
    "api-v1": "Operation names are lowerCamelCase.",
    "test-v1": "Compute every expected code by following the table call by call from the initial state; a rejected call (409) leaves the state unchanged.",
}

BASE_CONTRACTS = {"cls": "cls-v1", "ocl": "ocl-v1", "sm": "sm-v1", "api": "api-v1", "test": "test-v1"}
BASE_OWNERS = {"cls": "modeler-A", "ocl": "modeler-A", "sm": "modeler-B", "api": "modeler-C", "test": "modeler-C"}


def initial_state():
    return {"inputs": {"req": base_requirements(), "conventions": []},
            "context": {"rules": []},
            "contracts": dict(BASE_CONTRACTS), "owners": dict(BASE_OWNERS), "revoked": set(), "epochs": 0}


# --------------------------------------------------------------------- edits
def _e1(s):
    s["inputs"]["req"]["Member"]["text"] = ("Each member of the library is described by an identifier `id`, a "
                                            "`name` and an `email` address, both of type String, and by "
                                            "`maxLoans` (Integer), the number of loans the member may hold.")


def _e2(s):
    b = s["inputs"]["req"]["Book"]
    b["text"] = ("A book has an identifier `id`, a `title` (String), a number of available `copies` (Integer) and "
                 "a publication `year` (Integer).")
    b["attributes"]["year"] = "Integer"
    b["constraints"] = "The number of copies is never negative, and the year is 1450 or later."
    b["invariants"] = [["copies", ">=", 0], ["year", ">=", 1450]]


def _e3(s):
    s["inputs"]["req"]["Loan"]["lifecycle"] = LOAN_SM_RENEW_ONCE
    s["inputs"]["req"]["Loan"]["lifecycle_text"] = LOAN_TEXT_RENEW_ONCE


def _e4(s):
    s["contracts"]["ocl"] = "ocl-v2"


def _e5(s):
    s["context"]["rules"] = [NAMING_RULE]


def _e6(s):
    s["revoked"] = {"modeler-B"}
    s["owners"]["sm"] = "modeler-D"


def _e7(s):
    s["inputs"]["req"]["Reservation"]["lifecycle"] = RES_SM_EXPIRY
    s["inputs"]["req"]["Reservation"]["lifecycle_text"] = RES_TEXT_EXPIRY


EDITS = [("E1", "reworded requirement (Member)", _e1), ("E2", "new attribute and invariant (Book)", _e2),
         ("E3", "changed lifecycle (Loan)", _e3), ("E4", "new OCL contract", _e4),
         ("E5", "naming rule added to shared context", _e5), ("E6", "agent revoked, views reassigned", _e6),
         ("E7", "new lifecycle event (Reservation)", _e7)]


def feedback_epoch(s):
    """Deterministic policy: an identifier-type conflict at the barrier is promoted to an input convention."""
    s["inputs"]["conventions"] = [STRING_IDS]
    s["epochs"] += 1


# --------------------------------------------------------------------- validators
def _types_ok(spec, t, conventions):
    if spec in TYPES:
        return t == spec
    if t not in TYPES:
        return False
    return t == "String" if STRING_IDS in conventions else True


def validate_cls(o, v):
    src = o["source"]
    if not isinstance(v, dict) or not isinstance(v.get("attributes"), dict):
        return False, "expected {\"attributes\": {name: type}}"
    got, spec = v["attributes"], src["attributes"]
    missing, extra = sorted(set(spec) - set(got)), sorted(set(got) - set(spec))
    if missing or extra:
        return False, "missing attributes %s, unexpected attributes %s" % (missing, extra)
    bad = [a for a in spec if not _types_ok(spec[a], got[a], src["conventions"])]
    if bad:
        return False, "wrong or disallowed types for %s" % bad
    return True, None


OCL = re.compile(r"^\s*(?:inv\s+([a-z][A-Za-z0-9]*)\s*:\s*)?self\.([A-Za-z]\w*)\s*(>=|<=|<>|=|>|<)\s*"
                 r"(self\.([A-Za-z]\w*)|-?\d+)\s*$")
OPS = {">=": lambda a, b: a >= b, "<=": lambda a, b: a <= b, ">": lambda a, b: a > b, "<": lambda a, b: a < b,
       "=": lambda a, b: a == b, "<>": lambda a, b: a != b}
SAMPLES = (-1, 0, 1, 5, 10, 11, 28, 1449, 1450, 2000)


def _holds(invs, env):
    for lhs, op, rhs in invs:
        b = env[rhs] if isinstance(rhs, str) else rhs
        if not OPS[op](env[lhs], b):
            return False
    return True


def validate_ocl(o, v):
    src, attrs = o["source"], o["prerequisites"]["cls/" + o["source"]["entity"]]
    named = o["contract"] == "ocl-v2"
    if not isinstance(v, dict) or not isinstance(v.get("invariants"), list) or not v["invariants"]:
        return False, "expected {\"invariants\": [\"...\"]}"
    parsed, names = [], set()
    for text in v["invariants"]:
        m = OCL.match(text) if isinstance(text, str) else None
        if not m:
            return False, "cannot parse invariant %r" % (text,)
        if named != bool(m.group(1)):
            return False, ("invariant %r must be named (inv <name>: ...)" if named else
                           "invariant %r must be a plain expression without a name") % text
        if m.group(1):
            if m.group(1) in names:
                return False, "duplicate invariant name %s" % m.group(1)
            names.add(m.group(1))
        lhs, rhs = m.group(2), (m.group(5) if m.group(5) else int(m.group(4)))
        for a in [lhs] + ([rhs] if isinstance(rhs, str) else []):
            if attrs.get(a) != "Integer":
                return False, "invariant refers to %s, which is not an Integer attribute of the class view" % a
        parsed.append((lhs, m.group(3), rhs))
    ref = [tuple(x) for x in src["invariants"]]
    names_used = sorted({a for i in parsed + ref for a in (i[0], i[2]) if isinstance(a, str)})
    for combo in itertools.product(SAMPLES, repeat=len(names_used)):
        env = dict(zip(names_used, combo))
        if _holds(parsed, env) != _holds(ref, env):
            return False, "invariants disagree with the requirement, e.g. for %s" % env
    return True, None


def validate_sm(o, v):
    ref = o["source"]["lifecycle"]
    if not isinstance(v, dict) or not isinstance(v.get("table"), dict):
        return False, "expected {\"initial\": state, \"table\": {state: {event: [code, state]}}}"
    if v.get("initial") != ref["initial"]:
        return False, "wrong initial state"
    if set(v["table"]) != set(ref["table"]):
        return False, "states must be exactly %s" % sorted(ref["table"])
    for s, row in ref["table"].items():
        got = v["table"][s]
        if not isinstance(got, dict) or set(got) != set(row):
            got_keys = set(got) if isinstance(got, dict) else set()
            return False, "row %s must have exactly the events %s (missing %s, unexpected %s)" % (
                s, sorted(row), sorted(set(row) - got_keys), sorted(got_keys - set(row)))
        for e, (code, nxt) in row.items():
            g = got[e]
            if not isinstance(g, (list, tuple)) or len(g) != 2 or [g[0], g[1]] != [code, nxt]:
                return False, "entry (%s, %s) contradicts the lifecycle requirement" % (s, e)
    return True, None


def validate_api(o, v):
    e = o["source"]["entity"]
    p = o["prerequisites"]
    own, tb, tm, events = p["cls/" + e], p["cls/Book"], p["cls/Member"], p["sm/" + e]
    if not isinstance(v, dict) or not isinstance(v.get("operations"), list):
        return False, "expected {\"operations\": [...]}"
    seen, names = {}, set()
    for op in v["operations"]:
        if not isinstance(op, dict) or not isinstance(op.get("name"), str) or not isinstance(op.get("params"), dict):
            return False, "malformed operation %r" % (op,)
        n = op["name"]
        if n in names:
            return False, "duplicate operation name %s" % n
        names.add(n)
        if not re.match(r"^[a-z][A-Za-z0-9]*$", n):
            return False, "operation name %s is not lowerCamelCase" % n
        for rule in o["context"] or []:
            if not re.match(rule["regex"].replace("{entity}", e), n):
                return False, "operation name %s violates rule %s: %s" % (n, rule["id"], rule["text"])
        ev = op.get("event")
        if ev in seen:
            return False, "two operations for event %s" % ev
        seen[ev] = op
        expected = {"bookId": tb, "memberId": tm} if ev is None else {"id": own}
        if ev is not None and ev not in events:
            return False, "operation %s handles unknown event %s" % (n, ev)
        if op["params"] != expected:
            return False, "operation %s must have parameters %s" % (n, expected)
    if set(seen) != set(events) | {None}:
        return False, "need one creation operation (event null) and one operation per event %s" % events
    return True, None


def validate_test(o, v):
    e = o["source"]["entity"]
    sm, ops = o["prerequisites"]["sm/" + e], o["prerequisites"]["api/" + e]
    if not isinstance(v, dict) or not isinstance(v.get("scenarios"), list) or not 1 <= len(v["scenarios"]) <= 10:
        return False, "expected 1 to 10 scenarios"
    by_name = {n: ev for ev, n in ops.items()}
    used, codes = set(), set()
    for sc in v["scenarios"]:
        if (not isinstance(sc, dict) or not isinstance(sc.get("calls"), list) or not isinstance(sc.get("expect"), list)
                or len(sc["calls"]) != len(sc["expect"]) or not 1 <= len(sc["calls"]) <= 8):
            return False, "each scenario needs equally long calls and expect lists (1 to 8 calls)"
        state = sm["initial"]
        for call, code in zip(sc["calls"], sc["expect"]):
            if call not in by_name:
                return False, "unknown operation %r (operations: %s)" % (call, sorted(by_name))
            want, state = sm["table"][state][by_name[call]]
            if code != want:
                return False, "scenario %s expects %s for %s but the state machine answers %s" % (
                    sc["calls"], code, call, want)
            used.add(call)
            codes.add(code)
    if used != set(by_name) or 409 not in codes or 200 not in codes:
        return False, "scenarios must call every operation and expect both 200 and 409"
    return True, None


VALIDATORS = {"cls": validate_cls, "ocl": validate_ocl, "sm": validate_sm, "api": validate_api, "test": validate_test}


def global_predicate(values):
    """G: identifier types agree across associations (inter-view consistency)."""
    try:
        ids = {e: values["cls/" + e]["attributes"]["id"] for e in ("Book", "Member")}
        for e in ("Loan", "Reservation"):
            a = values["cls/" + e]["attributes"]
            if a["bookId"] != ids["Book"] or a["memberId"] != ids["Member"]:
                return False
        return True
    except (KeyError, TypeError):
        return False


# --------------------------------------------------------------------- jobs
def _events(v):
    return sorted({ev for row in v["table"].values() for ev in row})


def _op_map(v):
    return {op["event"]: op["name"] for op in v["operations"] if op.get("event") is not None}


def make_jobs(state):
    jobs, ct, ow = [], state["contracts"], state["owners"]
    for e in ENTITIES:
        def cls_reads(x, e=e):
            r = x["req"][e]
            return {"entity": e, "text": r["text"], "attributes": r["attributes"], "conventions": x["conventions"]}
        jobs.append(Job("cls/" + e, 1, (), ow["cls"], ct["cls"], cls_reads, None, {}, validate_cls))
        if base_requirements()[e]["invariants"]:
            def ocl_reads(x, e=e):
                r = x["req"][e]
                return {"entity": e, "text": r["constraints"], "invariants": r["invariants"]}
            jobs.append(Job("ocl/" + e, 2, ("cls/" + e,), ow["ocl"], ct["ocl"], ocl_reads, None,
                            {"cls/" + e: lambda v: v["attributes"]}, validate_ocl))
        if base_requirements()[e]["lifecycle"]:
            def sm_reads(x, e=e):
                r = x["req"][e]
                return {"entity": e, "text": r["lifecycle_text"], "lifecycle": r["lifecycle"]}
            jobs.append(Job("sm/" + e, 1, (), ow["sm"], ct["sm"], sm_reads, None, {}, validate_sm))
            pre = tuple(sorted({"cls/" + e, "cls/Book", "cls/Member", "sm/" + e}))
            proj = {p: (lambda v: v["attributes"]["id"]) for p in pre if p.startswith("cls/")}
            proj["sm/" + e] = _events
            jobs.append(Job("api/" + e, 3, pre, ow["api"], ct["api"], lambda x, e=e: {"entity": e},
                            lambda c: [r for r in c["rules"] if r["scope"] == "api"], proj, validate_api))
            jobs.append(Job("test/" + e, 4, ("sm/" + e, "api/" + e), ow["test"], ct["test"],
                            lambda x, e=e: {"entity": e}, None,
                            {"sm/" + e: lambda v: {"initial": v["initial"], "table": v["table"]}, "api/" + e: _op_map},
                            validate_test))
    return jobs


def make_kernel(state, strategy, budget):
    return Kernel(make_jobs(state), state["inputs"], state["context"], budget=budget, strategy=strategy,
                  global_predicate=global_predicate)


def apply(kernel, state):
    kernel.edit(inputs=state["inputs"], context=state["context"], jobs=make_jobs(state), revoked=state["revoked"])


# --------------------------------------------------------------------- oracle
def oracle(kernel, state):
    """Judge a released snapshot against the *current* model: every view must satisfy the
    current validator on its current exact observation, have been produced by its current
    authorised owner, and the snapshot must satisfy G."""
    values = kernel.values()
    issues = []
    for jid in kernel.jobs:
        v = values.get(jid)
        if v is None:
            issues.append((jid, "missing"))
            continue
        o = kernel.full_observation(jid, values=values)
        if o is None:
            issues.append((jid, "unobservable"))
            continue
        ok, why = kernel.jobs[jid].validator(o, v)
        if not ok:
            issues.append((jid, "invalid for the current model: " + str(why)))
        ev = kernel.records[jid].evidence
        if ev is None or ev.owner != kernel.jobs[jid].owner or ev.owner in state["revoked"]:
            issues.append((jid, "produced by an unauthorised or replaced agent"))
    if not global_predicate(values):
        issues.append(("G", "identifier types disagree across views"))
    return issues


# --------------------------------------------------------------------- reference agent
def reference_value(q, rng):
    """A correct answer to the question q was asked (not necessarily the current one)."""
    kind, o = q.job.split("/")[0], q.observation
    src, e = o["source"], o["source"]["entity"]
    if kind == "cls":
        attrs = {}
        for a, t in src["attributes"].items():
            attrs[a] = t if t in TYPES else ("String" if STRING_IDS in src["conventions"] else rng.choice(TYPES))
        return {"attributes": attrs}
    if kind == "ocl":
        out = []
        for i, (l, op, r) in enumerate(src["invariants"]):
            expr = "self.%s %s %s" % (l, op, "self." + r if isinstance(r, str) else r)
            out.append("inv %s%d: %s" % (l, i, expr) if o["contract"] == "ocl-v2" else expr)
        return {"invariants": out}
    if kind == "sm":
        lc = src["lifecycle"]
        return {"initial": lc["initial"], "table": deepcopy(lc["table"])}
    if kind == "api":
        p = o["prerequisites"]
        suffix = e if o["context"] else ""
        ops = [{"name": "create" + suffix, "event": None, "params": {"bookId": p["cls/Book"], "memberId": p["cls/Member"]}}]
        ops += [{"name": ev + suffix, "event": ev, "params": {"id": p["cls/" + e]}} for ev in p["sm/" + e]]
        return {"operations": ops}
    if kind == "test":
        sm, ops = o["prerequisites"]["sm/" + e], o["prerequisites"]["api/" + e]
        scenarios = []
        for ev in sorted(ops):
            state, expect = sm["initial"], []
            for _ in range(2):
                code, state = sm["table"][state][ev]
                expect.append(code)
            scenarios.append({"calls": [ops[ev]] * 2, "expect": expect})
        return {"scenarios": scenarios}
    raise ValueError(kind)


def corrupt(kind, v, rng):
    """A plausible wrong answer (what a generative agent gets wrong)."""
    v = deepcopy(v)
    if kind == "cls":
        a = rng.choice(sorted(v["attributes"]))
        if rng.random() < 0.5:
            del v["attributes"][a]
        else:
            v["attributes"][a] = "Integer" if v["attributes"][a] == "String" else "String"
    elif kind == "ocl":
        i = rng.randrange(len(v["invariants"]))
        v["invariants"][i] = re.sub(r"(-?\d+)\s*$", lambda m: str(int(m.group(1)) + 1), v["invariants"][i]) \
            if re.search(r"\d\s*$", v["invariants"][i]) else v["invariants"][i].replace(">", ">=", 1)
    elif kind == "sm":
        s = rng.choice(sorted(v["table"]))
        ev = rng.choice(sorted(v["table"][s]))
        code, nxt = v["table"][s][ev]
        v["table"][s][ev] = [409 if code == 200 else 200, nxt]
    elif kind == "api":
        v["operations"].pop(rng.randrange(len(v["operations"])))
    elif kind == "test":
        sc = rng.choice(v["scenarios"])
        sc["expect"][0] = 409 if sc["expect"][0] == 200 else 200
    return v


class SimulatedAgent:
    """Stochastic proposer: correct for the question asked with probability 1 - p_err."""

    def __init__(self, rng, p_err=0.25):
        self.rng, self.p_err = rng, p_err
        self.calls = 0

    def __call__(self, q):
        self.calls += 1
        v = reference_value(q, self.rng)
        return corrupt(q.job.split("/")[0], v, self.rng) if self.rng.random() < self.p_err else v


# --------------------------------------------------------------------- prompts (LLM agents)
def render(q):
    """The prompt is rendered from the request's observation (and validator feedback) only."""
    kind, o = q.job.split("/")[0], q.observation
    src, e, p = o["source"], o["source"]["entity"], o["prerequisites"]
    head = ("You are a modeling agent in a model-driven development project for a library service. "
            "Answer with a single JSON object and nothing else.\n\n")
    if kind == "cls":
        conv = ("\nModeling convention: " + " ".join(src["conventions"])) if src["conventions"] else ""
        body = ("Produce the class view of the entity %s.\nRequirement: %s%s\n%s\n"
                "Output format: {\"attributes\": {\"<attribute name>\": \"<String or Integer>\"}}"
                % (e, src["text"], conv, CONTRACT_TEXT[o["contract"]]))
    elif kind == "ocl":
        body = ("Produce the OCL invariants of the class %s.\nClass attributes and types: %s\n"
                "Constraint requirement: %s\n%s\nOutput format: {\"invariants\": [\"<invariant>\", ...]}"
                % (e, json.dumps(p["cls/" + e], sort_keys=True), src["text"], CONTRACT_TEXT[o["contract"]]))
    elif kind == "sm":
        body = ("Produce the behavioral state machine of %s as a transition table.\nLifecycle requirement: %s\n"
                "Each entry is [status code, next state], where 200 means the event is accepted and 409 means "
                "it is rejected. %s\nOutput format: {\"initial\": \"<state>\", \"table\": {\"<state>\": "
                "{\"<event>\": [<code>, \"<next state>\"]}}}" % (e, src["text"], CONTRACT_TEXT[o["contract"]]))
    elif kind == "api":
        rules = "".join("\nNaming rule %s: %s" % (r["id"], r["text"]) for r in (o["context"] or []))
        body = ("Produce the service interface of %s.\nLifecycle events: %s\nIdentifier types: %s.id is %s, "
                "Book.id is %s, Member.id is %s.\nThere is exactly one creation operation, with \"event\": null and "
                "the parameters bookId and memberId typed as the identifiers of Book and Member, and exactly one "
                "operation per lifecycle event, with the single parameter id typed as %s.id. %s%s\n"
                "Output format: {\"operations\": [{\"name\": \"<name>\", \"event\": <event name or null>, "
                "\"params\": {\"<parameter>\": \"<type>\"}}]}"
                % (e, ", ".join(p["sm/" + e]), e, p["cls/" + e], p["cls/Book"], p["cls/Member"], e,
                   CONTRACT_TEXT[o["contract"]], rules))
    elif kind == "test":
        sm, ops = p["sm/" + e], p["api/" + e]
        body = ("Produce acceptance test scenarios for %s.\nState machine (initial state %s), entries are "
                "[status code, next state]: %s\nOperation for each event: %s\nEach scenario starts from a newly "
                "created %s in the initial state and lists operation calls together with the expected status "
                "code of each call. Together the scenarios must call every operation at least once and expect "
                "both 200 and 409 at least once. Use at most 10 scenarios with at most 8 calls each. %s\n"
                "Output format: {\"scenarios\": [{\"calls\": [\"<operation>\", ...], \"expect\": [<code>, ...]}]}"
                % (e, sm["initial"], json.dumps(sm["table"], sort_keys=True), json.dumps(ops, sort_keys=True), e,
                   CONTRACT_TEXT[o["contract"]]))
    else:
        raise ValueError(kind)
    if q.feedback:
        body += "\n\nYour previous answer was rejected: %s. Correct it." % q.feedback
    return head + body


def parse(text):
    text = (text or "").strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1)
    start = text.find("{")
    if start < 0:
        return None
    try:
        return json.JSONDecoder().raw_decode(text[start:])[0]
    except ValueError:
        return None


__all__ = ["EDITS", "initial_state", "make_kernel", "apply", "oracle", "feedback_epoch", "SimulatedAgent",
           "render", "parse", "reference_value", "canonical"]

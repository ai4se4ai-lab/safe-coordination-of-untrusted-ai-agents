"""Coordination kernel for the SoSyM model-driven case study.

This is the generic kernel of src/vgc/graph.py (same admission discipline) with two
additions needed by a multi-view model:

* per-prerequisite *projections*: a view reads only the part of another view it
  depends on (e.g. the API view reads the identifier type of the Book class, not the
  whole class), which is the query F_j of the article;
* a configurable *strategy* that reproduces the coordination disciplines compared in
  the case study:

  exact     observation-relative keys (data, selected context, contract, owner),
            cancellation + recheck, upstream gate                       (the article)
  ungated   exact keys, but a view is dispatched on the *stored* values of its
            prerequisites whether or not they are usable              (Prop. eager)
  datakey   keys over data only (inputs and prerequisite values), as in build
            systems and read-set validation (OCC); cancellation + recheck, gate
  lww       datakey without cancellation and recheck: a reply is installed if it is
            valid for the question it was asked (typical agent pipeline, last writer
            wins)
  full      every change regenerates every view (key includes the input revision)
  coarse    exact keys, but a view reads whole prerequisite views (no projections):
            view-level instead of element-level dependencies (impact analysis only)

The kernel is deterministic and single-threaded; asynchrony is produced by the
discrete-event driver in mde_case.py, which decides when replies, duplicates,
timeouts and edits arrive.
"""
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Callable
import json

STRATEGIES = ("exact", "ungated", "datakey", "lww", "full", "coarse")
CAMPAIGN = ("exact", "ungated", "datakey", "lww", "full")   # compared in the asynchronous campaigns


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


@dataclass(frozen=True)
class Job:
    id: str
    rank: int
    prereqs: tuple = ()
    owner: str = "modeler-A"
    contract: str = "v1"
    reads: Callable[[dict], Any] = None                 # F_j over the authoritative inputs
    selects: Callable[[dict], Any] = None               # sel_j over shared context
    project: dict = field(default_factory=dict)         # prereq -> projection of its value
    validator: Callable[[dict, Any], Any] = None        # V_j(o, v) -> (bool, diagnostic)


@dataclass
class Record:
    episode: int
    key: str
    attempts: int = 0
    failed: bool = False
    value: Any = None
    stamp: str | None = None          # validated key
    evidence: Any = None              # the producing request
    feedback: str | None = None


@dataclass(frozen=True)
class Request:
    identity: str
    job: str
    episode: int
    attempt: int
    key: str
    observation: Any
    owner: str
    feedback: str | None = None


class Kernel:
    def __init__(self, jobs, inputs, context, budget=3, strategy="exact", global_predicate=None):
        if strategy not in STRATEGIES:
            raise ValueError(strategy)
        self.strategy = strategy
        self.gate = strategy != "ungated"
        self.guards = strategy != "lww"                 # cancellation and recheck
        self.budget, self.global_predicate = budget, global_predicate
        self.inputs, self.context = deepcopy(inputs), deepcopy(context)
        self.revoked, self.revision = set(), 0
        self._install_jobs(jobs)
        self.records, self.active, self.suspended = {}, set(), set()
        self.pending, self.history = {}, {}
        self.nonce = 0
        self.metrics = {"dispatched": 0, "committed": 0, "rejected": 0, "discarded": 0, "timeouts": 0,
                        "obsolete_installed": 0, "episodes": 0, "work_episodes": 0}
        self.work_log = []        # (revision, job) for every stale episode started
        self.dispatch_log = []    # (revision, job)
        self._reconcile()

    def _install_jobs(self, jobs):
        new = {j.id: j for j in sorted(jobs, key=lambda j: (j.rank, j.id))}
        for j in new.values():
            if any(p not in new or new[p].rank >= j.rank for p in j.prereqs):
                raise ValueError("unranked or missing prerequisite of " + j.id)
        self.jobs = new

    # ------------------------------------------------------------ observations
    def usable(self, jid):
        r = self.records.get(jid)
        if jid not in self.active or r is None or r.value is None or r.stamp != r.key:
            return False
        if self.strategy in ("datakey", "lww"):
            return True                    # owner is not part of the key
        return r.evidence.owner == self.jobs[jid].owner and r.evidence.owner not in self.revoked

    def full_observation(self, jid, values=None, gate=True):
        """The exact observation o_j (data, context, contract, owner, projected prerequisites)."""
        j = self.jobs[jid]
        preds = {}
        for p in j.prereqs:
            if values is not None:
                v = values.get(p)
            else:
                r = self.records.get(p)
                if gate and not self.usable(p):
                    return None
                v = None if r is None else r.value
            if v is None:
                return None
            fn = j.project.get(p)
            try:
                preds[p] = fn(v) if fn else v
            except Exception:                         # malformed upstream value
                preds[p] = None
        return {"job": jid, "source": j.reads(self.inputs) if j.reads else None,
                "context": j.selects(self.context) if j.selects else None,
                "prerequisites": preds, "contract": j.contract, "owner": j.owner}

    def observation(self, jid):
        j = self.jobs[jid]
        if j.owner in self.revoked and self.strategy not in ("datakey", "lww"):
            return None
        return self.full_observation(jid, gate=self.gate)

    def key_of(self, o):
        if self.strategy in ("datakey", "lww"):
            return canonical({"job": o["job"], "source": o["source"], "prerequisites": o["prerequisites"]})
        if self.strategy == "full":
            return canonical(dict(o, revision=self.revision))
        if self.strategy == "coarse":
            raw = {p: self.records[p].value for p in self.jobs[o["job"]].prereqs}
            return canonical(dict(o, whole_prerequisites=raw))
        return canonical(o)

    def _reconcile(self):
        previous = self.active
        self.active, self.suspended = set(), set()
        self.observations = {}
        for jid in self.jobs:
            o = self.observation(jid)
            if o is None:
                self.suspended.add(jid)
                continue
            self.active.add(jid)
            self.observations[jid] = o
            key = self.key_of(o)
            old = self.records.get(jid)
            if old is None or old.key != key or jid not in previous:
                self.nonce += 1
                rec = Record(self.nonce, key)
                if old is not None:
                    rec.value, rec.stamp, rec.evidence = old.value, old.stamp, old.evidence
                self.records[jid] = rec
                self.metrics["episodes"] += 1
                if rec.stamp != key:
                    self.metrics["work_episodes"] += 1
                    self.work_log.append((self.revision, jid))
        if self.guards:
            for identity, q in list(self.pending.items()):
                if not self._current(q):
                    del self.pending[identity]

    # ------------------------------------------------------------- transitions
    def edit(self, inputs=None, context=None, jobs=None, revoked=None):
        if inputs is not None:
            self.inputs = deepcopy(inputs)
        if context is not None:
            self.context = deepcopy(context)
        if jobs is not None:
            self._install_jobs(jobs)
        if revoked is not None:
            self.revoked = set(revoked)
        self.revision += 1
        self._reconcile()

    def eligible(self):
        busy = {q.job for q in self.pending.values()}
        return [j for j in self.jobs if j in self.active and not self.usable(j)
                and not self.records[j].failed and self.records[j].attempts < self.budget and j not in busy]

    def dispatch(self, jid):
        if jid not in self.eligible():
            return None
        r = self.records[jid]
        r.attempts += 1
        identity = canonical([jid, r.episode, r.attempts])
        assert identity not in self.history, "request identity reused"
        q = Request(identity, jid, r.episode, r.attempts, r.key, deepcopy(self.observations[jid]),
                    self.jobs[jid].owner, r.feedback)
        self.pending[identity] = self.history[identity] = q
        self.metrics["dispatched"] += 1
        self.dispatch_log.append((self.revision, jid))
        return q

    def _current(self, q):
        r = self.records.get(q.job)
        if q.job not in self.active or r is None or r.episode != q.episode or r.key != q.key:
            return False
        if self.strategy in ("datakey", "lww"):
            return True
        return q.owner not in self.revoked and q.owner == self.jobs[q.job].owner

    def resolve(self, identity, value=None, timeout=False):
        """Validate on the immutable dispatched observation, then recheck and write."""
        q = self.pending.get(identity) if self.guards else self.history.get(identity)
        if q is None or (self.guards and not self._current(q)):
            self.pending.pop(identity, None)
            self.metrics["discarded"] += 1
            return "discarded", None
        if q.job not in self.jobs or q.job not in self.records:
            self.pending.pop(identity, None)
            self.metrics["discarded"] += 1
            return "discarded", None
        if timeout:
            ok, diagnostic = False, "timeout"
            self.metrics["timeouts"] += 1
        else:
            try:
                verdict = self.jobs[q.job].validator(q.observation, value)
            except Exception as error:  # noqa: BLE001 a crashing validator rejects
                verdict = (False, "validator error: %r" % error)
            ok, diagnostic = verdict if isinstance(verdict, tuple) else (bool(verdict), None)
        current = self._current(q)
        r = self.records[q.job]
        self.pending.pop(identity, None)
        if ok:
            if not current:
                self.metrics["obsolete_installed"] += 1
            # A last-writer-wins pipeline marks the view up to date when a reply
            # arrives, whatever question it answered.
            stamp = r.key if self.strategy == "lww" else q.key
            r.value, r.stamp, r.evidence = deepcopy(value), stamp, q
            r.failed, r.feedback = False, None
            self.metrics["committed"] += 1
            self._reconcile()
            return "committed", None
        if current:
            r.feedback = diagnostic
            r.failed = r.attempts >= self.budget
        self.metrics["rejected"] += 1
        return "rejected", diagnostic

    # ------------------------------------------------------------- completion
    def quiescent(self):
        return not self.pending and not self.eligible()

    def publishable(self):
        if self.suspended or self.pending or not all(self.usable(j) for j in self.active):
            return False
        return self.global_predicate is None or bool(self.global_predicate(self.values()))

    def values(self):
        return {j: self.records[j].value for j in sorted(self.active)}

"""Generic guarded coordination kernel over an arbitrary acyclic job graph.

The reference controller in controller.py is specialised to the document-service
case study. This module implements the same admission discipline for any finite
ranked DAG of jobs so that the semantics can be exercised on coupled workspaces,
on deep and wide dependency lattices, and with real language-model proposers:

* exact observations (source footprint, selected context, contract, owner and the
  *values* of usable prerequisites) with canonical-JSON signatures;
* per-job episodes, never-reused request identities (job, episode, attempt) and a
  persistent per-episode budget k;
* the upstream usability gate (a job is suspended while a prerequisite is unusable);
* cancellation of obsolete requests on every reconciliation, and an optimistic
  commit: validation runs *outside* the lock on the immutable dispatched
  observation, and the currentness/authority guard is rechecked atomically with the
  write;
* candidate structural admissibility over *configured* consumers;
* a publication barrier (nothing suspended, dirty or pending, global predicate G).

Ablation switches reproduce the coarser strategies of the paper (``mode``) and the
eager, ungated scheduler (``gate=False``). Diagnostics returned by a validator are
attached to the next request of the same episode as *feedback*; they are not part of
the observation, so they never affect signatures or validity.
"""
from copy import deepcopy
from dataclasses import dataclass, field
from threading import RLock
from typing import Any, Callable
import json


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


@dataclass(frozen=True)
class Job:
    id: str
    rank: int
    prereqs: tuple = ()
    owner: str = "worker"
    contract: str = "v1"
    reads: Callable[[dict], Any] = None          # source footprint F_j(X)
    selects: Callable[[dict], Any] = None        # selected shared context
    validator: Callable[[dict, Any], Any] = None  # V_j(o, v) -> bool | (bool, diagnostic)


@dataclass
class Record:
    episode: int
    signature: str
    attempts: int = 0
    failed: bool = False
    value: Any = None
    stamp: str | None = None
    evidence_owner: str | None = None
    evidence_request: str | None = None
    feedback: str | None = None


@dataclass(frozen=True)
class Request:
    identity: str
    job: str
    episode: int
    attempt: int
    signature: str
    observation: Any
    owner: str
    feedback: str | None = None


MODES = ("exact", "no-cutoff", "version", "workspace", "full")


class GraphController:
    def __init__(self, jobs, inputs, context=None, budget=2, mode="exact", gate=True,
                 admissible=None, global_predicate=None):
        if mode not in MODES:
            raise ValueError(mode)
        self.lock = RLock()
        self.jobs = {j.id: j for j in sorted(jobs, key=lambda j: (j.rank, j.id))}
        for j in self.jobs.values():
            if any(p not in self.jobs or self.jobs[p].rank >= j.rank for p in j.prereqs):
                raise ValueError("unranked or missing prerequisite of " + j.id)
        self.inputs, self.context = deepcopy(inputs), deepcopy(context or {})
        self.context_version, self.input_revision = 0, 0
        self.budget, self.mode, self.gate = budget, mode, gate
        self.admissible = admissible            # structural check over configured consumers
        self.global_predicate = global_predicate
        self.revoked = set()
        self.records, self.active, self.suspended = {}, set(), set()
        self.pending, self.history = {}, {}
        self.nonce = 0
        # Metrics.
        self.sent_requests = self.sent_bytes = 0
        self.episodes = {j: 0 for j in self.jobs}         # all episodes started
        self.work_episodes = {j: 0 for j in self.jobs}    # episodes whose stamp was stale
        self.discarded = self.rejected = self.committed = 0
        self.log = []
        self._reconcile()

    # ------------------------------------------------------------ observations
    def usable(self, jid):
        r = self.records.get(jid)
        return (jid in self.active and r is not None and r.value is not None and r.stamp == r.signature
                and r.evidence_owner == self.jobs[jid].owner and r.evidence_owner not in self.revoked)

    def observation(self, jid):
        j = self.jobs[jid]
        if j.owner in self.revoked:
            return None
        preds = {}
        for p in j.prereqs:
            r = self.records.get(p)
            if self.gate:
                if not self.usable(p):
                    return None
            elif r is None or r.value is None:
                return None
            preds[p] = r.value
        o = {"job": jid, "source": j.reads(self.inputs) if j.reads else None,
             "context": j.selects(self.context) if j.selects else None,
             "prerequisites": preds, "contract": j.contract, "owner": j.owner}
        if self.mode in ("no-cutoff", "full"):
            # No early cutoff: also depend on the identity of each upstream acceptance,
            # as timestamp- or version-based build tools do.
            o["acceptances"] = {p: self.records[p].evidence_request for p in j.prereqs}
        if self.mode == "version" and j.selects:
            o["context_version"] = self.context_version
        if self.mode == "workspace":
            o["workspace"] = {"inputs": self.inputs, "context": self.context}
        if self.mode == "full":
            o["input_revision"] = self.input_revision
        return deepcopy(o)

    def _reconcile(self):
        previous = self.active
        self.active, self.suspended = set(), set()
        for jid in self.jobs:
            o = self.observation(jid)
            if o is None:
                self.suspended.add(jid)
                continue
            self.active.add(jid)
            signature = canonical(o)
            old = self.records.get(jid)
            if old is None or old.signature != signature or jid not in previous:
                self.nonce += 1
                rec = Record(self.nonce, signature)
                if old is not None:
                    rec.value, rec.stamp = old.value, old.stamp
                    rec.evidence_owner, rec.evidence_request = old.evidence_owner, old.evidence_request
                self.records[jid] = rec
                self.episodes[jid] += 1
                if rec.stamp != signature:
                    self.work_episodes[jid] += 1
        for identity, q in list(self.pending.items()):
            r = self.records.get(q.job)
            if (q.job not in self.active or r.episode != q.episode or r.signature != q.signature
                    or q.owner in self.revoked or q.owner != self.jobs[q.job].owner):
                del self.pending[identity]

    # ------------------------------------------------------------- transitions
    def edit(self, inputs=None, context=None, jobs=None, revoked=None):
        """One atomic input/context/configuration transaction."""
        with self.lock:
            if inputs is not None:
                self.inputs = deepcopy(inputs)
            if context is not None:
                self.context = deepcopy(context)
                self.context_version += 1
            if jobs is not None:
                new = {j.id: j for j in sorted(jobs, key=lambda j: (j.rank, j.id))}
                for j in new.values():
                    if any(p not in new or new[p].rank >= j.rank for p in j.prereqs):
                        raise ValueError("unranked or missing prerequisite of " + j.id)
                self.jobs = new
                for jid in new:
                    self.episodes.setdefault(jid, 0)
                    self.work_episodes.setdefault(jid, 0)
            if revoked is not None:
                self.revoked = set(revoked)
            self.input_revision += 1
            self._reconcile()
            return "committed"

    def eligible(self):
        with self.lock:
            busy = {q.job for q in self.pending.values()}
            return [j for j in self.jobs if j in self.active and not self.usable(j)
                    and not self.records[j].failed and self.records[j].attempts < self.budget and j not in busy]

    def dispatch(self, jid):
        with self.lock:
            if jid not in self.eligible():
                return None
            r = self.records[jid]
            r.attempts += 1
            identity = canonical([jid, r.episode, r.attempts])
            if identity in self.history:
                raise AssertionError("request identity reused")
            q = Request(identity, jid, r.episode, r.attempts, r.signature, json.loads(r.signature),
                        self.jobs[jid].owner, r.feedback)
            self.pending[identity] = self.history[identity] = q
            self.sent_requests += 1
            self.sent_bytes += len(r.signature)
            return q

    def _current(self, q):
        r = self.records.get(q.job)
        return (q.identity in self.pending and q.job in self.active and r is not None and r.episode == q.episode
                and r.signature == q.signature and q.owner not in self.revoked and q.owner == self.jobs[q.job].owner)

    def resolve(self, identity, value=None, timeout=False):
        """Optimistic commit: validate outside the lock, recheck and write atomically."""
        with self.lock:
            q = self.pending.get(identity)
            if q is None or not self._current(q):
                self.pending.pop(identity, None)
                self.discarded += 1
                self.log.append(("discarded", identity))
                return "discarded", None
            validator = self.jobs[q.job].validator
        # Validation reads only the immutable dispatched observation (may be slow).
        if timeout:
            ok, diagnostic = False, "timeout"
        else:
            try:
                verdict = validator(q.observation, value)
            except Exception as error:  # a validator crash rejects the proposal
                verdict = (False, "validator error: %r" % error)
            ok, diagnostic = verdict if isinstance(verdict, tuple) else (bool(verdict), None)
        with self.lock:
            if not self._current(q):
                # The observation changed while we were validating: the reply is obsolete.
                self.pending.pop(identity, None)
                self.discarded += 1
                self.log.append(("discarded-after-validation", identity))
                return "discarded", diagnostic
            r = self.records[q.job]
            if ok and self.admissible is not None:
                values = {j: rec.value for j, rec in self.records.items()}
                values[q.job] = value
                if not self.admissible(self, values):
                    ok, diagnostic = False, "structurally inadmissible for a configured consumer"
            del self.pending[identity]
            if ok:
                r.value, r.stamp = deepcopy(value), q.signature
                r.evidence_owner, r.evidence_request = q.owner, identity
                r.failed, r.feedback = False, None
                self.committed += 1
                self.log.append(("committed", identity))
                self._reconcile()
                return "committed", None
            r.feedback = diagnostic
            r.failed = r.attempts >= self.budget
            self.rejected += 1
            self.log.append(("rejected", identity, diagnostic))
            return "rejected", diagnostic

    # ------------------------------------------------------------- completion
    def status(self):
        with self.lock:
            failed = [j for j in self.active if not self.usable(j) and self.records[j].failed]
            blocked = [j for j in self.suspended if j not in self.records or True]
            return {"failed": sorted(failed), "suspended": sorted(blocked),
                    "pending": len(self.pending), "usable": sum(self.usable(j) for j in self.active)}

    def publishable(self):
        with self.lock:
            ready = (not self.suspended and not self.pending and all(self.usable(j) for j in self.active))
            if not ready:
                return False
            if self.global_predicate is None:
                return True
            return bool(self.global_predicate(self, {j: self.records[j].value for j in self.active}))

    def values(self):
        with self.lock:
            return {j: self.records[j].value for j in sorted(self.active)}


def repair(c, provider, max_rounds=10_000):
    """Topological repair with a synchronous provider: provider(request) -> value."""
    for _ in range(max_rounds):
        jobs = c.eligible()
        if not jobs:
            return c.publishable()
        for jid in jobs:
            q = c.dispatch(jid)
            if q is not None:
                c.resolve(q.identity, provider(q))
    raise RuntimeError("repair did not quiesce")

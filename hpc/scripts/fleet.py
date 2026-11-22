#!/usr/bin/env python3
"""HPC controller for this project's LLM experiments (Alliance: rorqual, narval, fir).

Uses ONLY the ControlMaster sockets in this repository's hpc/.ssh, opened by
hpc/scripts/ssh-session.sh; never handles credentials. Everything runs under the
project's own work directory on the cluster (hpc/config/clusters.json: "work").
Every submission is appended to hpc/fetched/jobs.jsonl.

  python3 hpc/scripts/fleet.py probe   [--sites rorqual,narval]
  python3 hpc/scripts/fleet.py setup   [--sites ...]   # copy Ollama runtime + models into <work>/ollama
  python3 hpc/scripts/fleet.py deploy  [--sites ...]   # rsync src/, experiments/, data/ into <work>/repo
  python3 hpc/scripts/fleet.py submit --site rorqual --model qwen2.5-coder:7b --study benchmark \
          --args="--benchmark;humaneval;--limit;10" --tag smoke --time 0:30:00
  python3 hpc/scripts/fleet.py status
  python3 hpc/scripts/fleet.py fetch  [--sites ...]
"""
from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CFG = json.loads((ROOT / "hpc/config/clusters.json").read_text())
FETCHED = ROOT / "hpc/fetched"
JOBS = FETCHED / "jobs.jsonl"
PAYLOAD = ["src", "experiments", "data", "hpc/slurm"]


def ssh_opts(site):
    return ["-o", f"ControlPath={ROOT}/hpc/.ssh/{site}", "-o", "ControlMaster=no",
            "-o", "BatchMode=yes", "-o", "ConnectTimeout=20"]


def target(site):
    return f"{CFG['username']}@{CFG['clusters'][site]['host']}"


def rsh(site, cmd, timeout=180):
    r = subprocess.run(["ssh", *ssh_opts(site), target(site), cmd], capture_output=True, text=True, timeout=timeout)
    return r.returncode, (r.stdout + r.stderr).strip()


def rsync(site, src, dst, timeout=1800, extra=()):
    e = "ssh " + " ".join(shlex.quote(x) for x in ssh_opts(site))
    return subprocess.run(["rsync", "-az", *extra, "-e", e, src, dst], timeout=timeout).returncode


def sites(arg):
    return arg.split(",") if arg else ["rorqual", "narval"]


def probe(a):
    out = {}
    for s in sites(a.sites):
        w = CFG["clusters"][s]["work"]
        code, txt = rsh(s, "hostname; "
                        f"ls -d {w} {w}/ollama/runtime/bin/ollama {w}/ollama/models 2>&1; "
                        f"[ -d {w}/ollama/models/manifests ] && find {w}/ollama/models/manifests -mindepth 3 "
                        "-maxdepth 4 -type f | sed 's|.*/library/||' | tr '\\n' ' '; echo; "
                        "sinfo -h -o '%P %G %a %D' 2>/dev/null | grep -i gpu | head -4; "
                        "squeue -u $USER -h 2>/dev/null | wc -l", timeout=90)
        out[s] = {"ok": code == 0, "report": txt}
        print(f"===== {s} (rc={code})\n{txt}\n")
    FETCHED.mkdir(parents=True, exist_ok=True)
    (FETCHED / "probe.json").write_text(json.dumps(out, indent=2))


def setup(a):
    """Copy (read-only source) an Ollama runtime and the configured models into <work>/ollama."""
    models = " ".join(m.replace(":", "/") for m in CFG["models"])
    for s in sites(a.sites):
        w = CFG["clusters"][s]["work"]
        runtimes = " ".join(CFG["ollama_runtime_candidates"])
        stores = " ".join(CFG["model_store_candidates"])
        script = f"""set -e
mkdir -p {w}/ollama/runtime {w}/ollama/models/manifests/registry.ollama.ai/library {w}/ollama/models/blobs {w}/repo {w}/outputs {w}/logs
if [ ! -x {w}/ollama/runtime/bin/ollama ]; then
  for r in {runtimes}; do if [ -x $r/bin/ollama ]; then rsync -a --exclude=vulkan $r/ {w}/ollama/runtime/; echo runtime:$r; break; fi; done
fi
for m in {models}; do
  name=${{m%/*}}; tag=${{m#*/}}
  dst={w}/ollama/models/manifests/registry.ollama.ai/library/$name/$tag
  [ -f $dst ] && {{ echo have:$m; continue; }}
  for st in {stores}; do
    src=$st/manifests/registry.ollama.ai/library/$name/$tag
    if [ -f $src ]; then
      mkdir -p $(dirname $dst); cp $src $dst
      for d in $(grep -o 'sha256:[0-9a-f]*' $src | sort -u); do
        b={w}/ollama/models/blobs/${{d/:/-}}; [ -f $b ] || cp $st/blobs/${{d/:/-}} $b
      done
      echo copied:$m:$st; break
    fi
  done
  [ -f $dst ] || echo missing:$m
done
du -sh {w}/ollama"""
        code, txt = rsh(s, script, timeout=3600)
        print(f"===== {s} (rc={code})\n{txt}\n")


def proofs(a):
    """Re-run the scoped TLAPS lemmas natively on an x86_64 login node (pinned tlapm 1.6.0-pre)."""
    lock = json.loads((ROOT / "environment/toolchain.lock.json").read_text())["tlapm"]
    for s in sites(a.sites):
        w = CFG["clusters"][s]["work"]
        rsync(s, f"{ROOT}/proofs/", f"{target(s)}:{w}/repo/proofs/")
        rsync(s, f"{ROOT}/specification/", f"{target(s)}:{w}/repo/specification/")
        script = f"""set -e
mkdir -p {w}/tools && cd {w}/tools
[ -f tlapm.tar.gz ] || curl -sSfL -o tlapm.tar.gz {lock['url']}
echo "{lock['sha256']}  tlapm.tar.gz" | sha256sum -c -
[ -x tlapm/bin/tlapm ] || tar xzf tlapm.tar.gz
cd {w}/repo/proofs
for m in Budget ControllerSafety StructuralKernelProofs DocumentPolicyProofs; do
  echo "== $m"; timeout 300 {w}/tools/tlapm/bin/tlapm --strict --cleanfp --timing -I {w}/repo/specification $m.tla 2>&1 | grep -E "obligations|proved|failed|error" | tail -5
done
{w}/tools/tlapm/bin/tlapm --version 2>&1 | head -2; uname -m"""
        code, txt = rsh(s, script, timeout=1800)
        FETCHED.mkdir(parents=True, exist_ok=True)
        (FETCHED / f"proofs-{s}.log").write_text(txt + "\n")
        print(f"===== {s} (rc={code})\n{txt}")


def deploy(a):
    for s in sites(a.sites):
        w = CFG["clusters"][s]["work"]
        rsh(s, f"mkdir -p {w}/repo/hpc {w}/outputs {w}/logs")
        rcs = [rsync(s, f"{ROOT}/{p}/", f"{target(s)}:{w}/repo/{p}/",
                     extra=("--exclude=__pycache__", "--delete")) for p in PAYLOAD]
        print(f"{s}: deploy rc={rcs}")


def submit(a):
    s, c = a.site, CFG["clusters"][a.site]
    w = c["work"]
    safe = a.model.replace(":", "_").replace("/", "_")
    out = f"{w}/outputs/{a.tag}/{a.study}/{safe}"
    env = {"VGC_ROOT": w, "MODEL": a.model, "STUDY": a.study, "ARGS": a.args, "OUT": out,
           "PARALLEL": str(a.parallel)}
    if "," in a.args:
        sys.exit("use ';' to separate arguments (sbatch --export splits on commas)")
    exports = "ALL," + ",".join(f"{k}={v}" for k, v in env.items())
    cmd = (f"cd {w}/logs && sbatch --parsable --account={c['gpu_account']} --gres={c['gres']} --time={a.time} "
           f"--job-name=vgc-{a.tag}-{safe[:16]} --export={shlex.quote(exports)} {w}/repo/hpc/slurm/vgc_llm.sbatch")
    code, txt = rsh(s, cmd)
    rec = {"utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "site": s, "tag": a.tag, "model": a.model,
           "study": a.study, "args": a.args, "time": a.time, "rc": code, "reply": txt[-300:], "out": out}
    FETCHED.mkdir(parents=True, exist_ok=True)
    with JOBS.open("a") as fh:
        fh.write(json.dumps(rec) + "\n")
    print(json.dumps(rec))


def status(a):
    for s in sites(a.sites):
        code, txt = rsh(s, "squeue -u $USER -h -o '%i %j %T %M %l %R' | grep vgc || true; "
                        "sacct -u $USER -S now-2days -n -X -o JobID,JobName%34,State,Elapsed | grep vgc | tail -40")
        print(f"===== {s}\n{txt}\n")


def fetch(a):
    for s in sites(a.sites):
        w = CFG["clusters"][s]["work"]
        dst = FETCHED / s
        (dst / "outputs").mkdir(parents=True, exist_ok=True)
        rc1 = rsync(s, f"{target(s)}:{w}/outputs/", f"{dst}/outputs/")
        rc2 = rsync(s, f"{target(s)}:{w}/logs/", f"{dst}/logs/")
        rc3 = rsync(s, f"{target(s)}:{w}/repo/results/raw/", f"{dst}/results-raw/")
        print(f"{s}: fetch rc={rc1},{rc2},{rc3}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("probe", "setup", "deploy", "status", "fetch", "proofs"):
        sub.add_parser(name).add_argument("--sites")
    p = sub.add_parser("submit")
    p.add_argument("--site", required=True)
    p.add_argument("--model", required=True)
    p.add_argument("--study", choices=["benchmark", "llm"], required=True)
    p.add_argument("--args", default="")
    p.add_argument("--tag", required=True)
    p.add_argument("--parallel", type=int, default=6)
    p.add_argument("--time", default="3:00:00")
    a = ap.parse_args()
    {"probe": probe, "setup": setup, "proofs": proofs, "deploy": deploy, "submit": submit, "status": status, "fetch": fetch}[a.cmd](a)
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env bash
# Persistent SSH ControlMaster sessions to the Alliance (Compute Canada) clusters for THIS project.
# Sockets live in this repository's hpc/.ssh (git-ignored). Interactive MFA is the only manual step;
# no credentials are stored.
#   bash hpc/scripts/ssh-session.sh connect rorqual   # or narval, fir, all
#   bash hpc/scripts/ssh-session.sh status all
#   bash hpc/scripts/ssh-session.sh close all
set -euo pipefail
root=$(cd "$(dirname "$0")/../.." && pwd)
usage() {
  cat <<'EOF'
Usage: bash hpc/scripts/ssh-session.sh connect|status|close [rorqual|narval|fir|all]

Open persistent SSH sessions first (complete MFA in your terminal):
  bash hpc/scripts/ssh-session.sh connect all
Check existing sessions:
  bash hpc/scripts/ssh-session.sh status all
Close sessions:
  bash hpc/scripts/ssh-session.sh close all

The cluster defaults to all. Set ALLIANCE_USER to override the default username.
EOF
}
if [[ $# -eq 0 || ${1:-} == --help || ${1:-} == -h ]]; then usage; exit 0; fi
if [[ $# -gt 2 ]]; then usage >&2; exit 2; fi
case "$1" in connect|status|close) ;; *) usage >&2; exit 2;; esac
cluster=${2:-all}
user=${ALLIANCE_USER:-mbabaei}
mkdir -p "$root/hpc/.ssh"; chmod 700 "$root/hpc/.ssh"
case "$cluster" in fir|narval|rorqual) clusters=("$cluster");; all) clusters=(rorqual narval fir);;
  *) echo 'cluster must be fir, narval, rorqual or all' >&2; exit 2;; esac
failed=0
for site in "${clusters[@]}"; do
  socket="$root/hpc/.ssh/$site"
  host="$user@$site.alliancecan.ca"
  opts=(-o StrictHostKeyChecking=accept-new -o ConnectTimeout=20 -o ServerAliveInterval=60
        -o ServerAliveCountMax=3 -o ControlPath="$socket")
  case "$1" in
    connect) echo "== $site"; ssh "${opts[@]}" -o ControlMaster=auto -o ControlPersist=24h -MNf "$host" || failed=1 ;;
    status)
      if [[ ! -S "$socket" ]]; then
        echo "$site: not connected; run: bash hpc/scripts/ssh-session.sh connect $site"
        failed=1
      else
        echo -n "$site: "; ssh "${opts[@]}" -O check "$host" 2>&1 || failed=1
      fi ;;
    close)   ssh "${opts[@]}" -O exit "$host" || failed=1 ;;
    *) echo 'usage: ssh-session.sh connect|status|close [fir|narval|rorqual|all]' >&2; exit 2 ;;
  esac
done
exit "$failed"

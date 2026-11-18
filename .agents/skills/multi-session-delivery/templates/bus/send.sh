#!/usr/bin/env bash
# usage: send.sh <to> <from> <one-line message>   (both names must be in lanes.txt next to this script, or pm)
# exit 0 sent; 2 usage or unknown name; 3 bus locked; 4 wrong weekday for a date; 6 missing ETA or evidence.
# START/BLOCKER/DONE lines are also recorded in open-items.tsv for overdue.py. When the check cannot run (no python3,
# a crash) or the record cannot be written, the line is still sent, with a warning: the bus must never stop.
set -euo pipefail
[ $# -eq 3 ] || { echo "usage: $0 <to> <from> <message>" >&2; exit 2; }
dir=$(cd "$(dirname "$0")" && pwd)
[ -f "$dir/lanes.txt" ] || { echo "missing lanes.txt next to $0: list the session names, one per line" >&2; exit 2; }
to=$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')
[[ "$to" =~ ^[a-z0-9][a-z0-9-]*$ ]] || { echo "bad name: $1" >&2; exit 2; }
from=$(printf '%s' "$2" | tr '[:upper:]' '[:lower:]')
known=$(printf 'pm\n'; tr -d '\r' < "$dir/lanes.txt" | tr '[:upper:]' '[:lower:]' | sed 's/[[:space:]]*$//')
for name in "$to" "$from"; do
  grep -qxF -- "$name" <<< "$known" \
    || { echo "unknown session: $name (known: $(tr '\n' ' ' <<< "$known"))" >&2; exit 2; }
done
[ -n "$3" ] || { echo "empty message" >&2; exit 2; }
[[ "$from" =~ ^[a-z0-9][a-z0-9-]*$ ]] || { echo "bad name: $2" >&2; exit 2; }
msg=$(printf '%s' "$3" | tr '\r\n' '  ')
# One line per attempt in events.jsonl, never the message text (it may hold what the guards refuse):
# sent | refused-weekday | refused-eta | unchecked (the check could not run) | untracked (the record failed).
# overdue.py --health counts them. Usage errors (exit 2) and a locked bus (exit 3) are not logged.
bus_event() {
  printf '{"time":"%s","from":"%s","to":"%s","outcome":"%s"}\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$from" "$to" "$1" \
    >> "${BUS_EVENTS:-$dir/events.jsonl}" 2>/dev/null || echo "send.sh: warning: event not logged" >&2
}
# ETA on everything (send_check.py): exit 4 for a weekday that does not match its date, exit 6 for a START or
# BLOCKER without a valid ETA, a DONE or CLEARED without key and evidence, or the old words started/blocked.
# A check that cannot run (no python3) warns and lets the line through untracked: the bus must never stop.
rc=0; record=$(python3 -I "$dir/send_check.py" "$msg" "$from") || rc=$?
outcome=sent
case $rc in
  0) ;;
  4) bus_event refused-weekday; exit 4 ;;
  6) bus_event refused-eta; exit 6 ;;
  *) echo "send.sh: warning: send_check.py failed (exit $rc); line sent unchecked and not tracked" >&2
     record=""; outcome=unchecked ;;
esac
. "$dir/lock.sh"
printf '%s | from %s | %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$from" "$msg" >> "$dir/inbox-$to.md"
# The line is delivered: a failed record must not make the sender retry it (a second copy in the inbox).
if [ -n "$record" ] && ! printf '%s\n' "$record" >> "$dir/open-items.tsv"; then
  echo "send.sh: warning: line sent but not tracked in open-items.tsv" >&2; outcome=untracked
fi
bus_event "$outcome"
echo "ok inbox-$to"

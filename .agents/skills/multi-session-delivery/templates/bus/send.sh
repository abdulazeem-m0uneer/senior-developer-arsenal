#!/usr/bin/env bash
# usage: send.sh <to> <from> <one-line message>   (both names must be in lanes.txt next to this script, or pm)
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
msg=$(printf '%s' "$3" | tr '\r\n' '  ')
. "$dir/lock.sh"
printf '%s | from %s | %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$from" "$msg" >> "$dir/inbox-$to.md"
echo "ok inbox-$to"

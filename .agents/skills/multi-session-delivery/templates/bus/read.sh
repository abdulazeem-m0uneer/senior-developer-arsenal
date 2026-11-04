#!/usr/bin/env bash
# usage: read.sh <name>   prints the unread lines of inbox-<name>.md and moves the read mark
set -euo pipefail
[ $# -eq 1 ] || { echo "usage: $0 <name>" >&2; exit 2; }
dir=$(cd "$(dirname "$0")" && pwd)
name=$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')
[[ "$name" =~ ^[a-z0-9][a-z0-9-]*$ ]] || { echo "bad name: $1" >&2; exit 2; }
inbox="$dir/inbox-$name.md"; mark="$dir/read-mark-$name.txt"
[ -f "$inbox" ] || { echo "(no unread messages)"; exit 0; }
. "$dir/lock.sh"
last=$(cat "$mark" 2>/dev/null || echo 0)
[[ "$last" =~ ^[0-9]+$ ]] || { echo "warning: unreadable $mark, reading the whole inbox" >&2; last=0; }
total=$(wc -l < "$inbox" | tr -d ' ')
if (( last > total )); then
  echo "warning: read mark $last is past the inbox end ($total lines): reading the whole inbox" >&2
  last=0
fi
if (( last < total )); then sed -n "$((last + 1)),${total}p" "$inbox"; else echo "(no unread messages)"; fi
printf '%s\n' "$total" > "$mark.tmp" && mv "$mark.tmp" "$mark"

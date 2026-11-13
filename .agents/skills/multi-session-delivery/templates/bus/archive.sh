#!/usr/bin/env bash
# usage: archive.sh [days=7]   moves inbox lines that are older than <days> AND acknowledged to archive/ and
# shifts the read mark, under the bus lock. Unacknowledged lines always stay. Run by the coordinator once a week.
set -euo pipefail
days=${1:-7}
[[ "$days" =~ ^[0-9]+$ ]] || { echo "usage: $0 [days]" >&2; exit 2; }
dir=$(cd "$(dirname "$0")" && pwd)
cutoff=$(date -u -d "-$days days" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -v-"$days"d +%Y-%m-%dT%H:%M:%SZ)
. "$dir/lock.sh"
mkdir -p "$dir/archive"
for inbox in "$dir"/inbox-*.md; do
  [ -f "$inbox" ] || continue
  name=$(basename "$inbox" .md); name=${name#inbox-}
  # Lines are appended in time order and start with a UTC ISO time, so a text compare finds the old prefix.
  old=$(awk -v c="$cutoff" '{ if (substr($0, 1, 20) < c) n = NR; else exit } END { print n + 0 }' "$inbox")
  mark="$dir/read-mark-$name.txt"
  last=$(cat "$mark" 2>/dev/null || echo 0); [[ "$last" =~ ^[0-9]+$ ]] || last=0
  (( old < last )) || old=$last   # never archive a line its reader has not acknowledged
  (( old > 0 )) || continue
  head -n "$old" "$inbox" >> "$dir/archive/inbox-$name-$(date -u +%Y-%m-%d).md"
  # Mark first: a crash between the two steps repeats lines instead of losing them.
  printf '%s\n' "$((last - old))" > "$mark.tmp" && mv "$mark.tmp" "$mark"
  tail -n +"$((old + 1))" "$inbox" > "$inbox.tmp" && mv "$inbox.tmp" "$inbox"
  echo "archived $old line(s) of inbox-$name"
done

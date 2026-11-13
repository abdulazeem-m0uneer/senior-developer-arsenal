#!/usr/bin/env bash
# usage: read.sh <name>                prints the unread lines of inbox-<name>.md; the read mark does not move
#        read.sh <name> --ack <line>   moves the read mark to <line>, once the lines up to it were acted on
# Delivery is at least once: a session that stops before it acknowledges sees the same lines again.
set -euo pipefail
usage() { echo "usage: $0 <name> [--ack <line>]" >&2; exit 2; }
ack=""
case $# in
  1) ;;
  3) if [ "$2" != "--ack" ] || ! [[ "$3" =~ ^[0-9]+$ ]]; then usage; fi; ack=$((10#$3)) ;;
  *) usage ;;
esac
dir=$(cd "$(dirname "$0")" && pwd)
name=$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')
[[ "$name" =~ ^[a-z0-9][a-z0-9-]*$ ]] || { echo "bad name: $1" >&2; exit 2; }
inbox="$dir/inbox-$name.md"; mark="$dir/read-mark-$name.txt"
if [ ! -f "$inbox" ]; then
  [ -z "$ack" ] || { echo "nothing to acknowledge: $name has no inbox" >&2; exit 2; }
  echo "(no unread messages)"; exit 0
fi
. "$dir/lock.sh"
last=$(cat "$mark" 2>/dev/null || echo 0)
[[ "$last" =~ ^[0-9]+$ ]] || { echo "warning: unreadable $mark, reading the whole inbox" >&2; last=0; }
total=$(wc -l < "$inbox" | tr -d ' ')
if (( last > total )); then
  echo "warning: read mark $last is past the inbox end ($total lines): reading the whole inbox" >&2
  last=0
fi
if [ -n "$ack" ]; then
  (( ack <= total )) \
    || { echo "cannot acknowledge line $ack: the inbox has $total line(s); read it again" >&2; exit 2; }
  if (( ack <= last )); then echo "ok read-mark-$name $last (line $ack was already acknowledged)"; exit 0; fi
  printf '%s\n' "$ack" > "$mark.tmp" && mv "$mark.tmp" "$mark"
  echo "ok read-mark-$name $ack"
elif (( last < total )); then
  sed -n "$((last + 1)),${total}p" "$inbox"
  echo "($((total - last)) unread; after acting on them: bash $0 $name --ack $total)" >&2
else
  echo "(no unread messages)"
fi

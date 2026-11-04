#!/usr/bin/env bash
# Sourced by send.sh, read.sh and archive.sh: one bus-wide lock (mkdir is atomic on Linux and macOS).
# The owner's pid sits in the lock so a lock left by a killed process can be identified and removed by hand
# (an automatic takeover would let two waiting scripts both take the lock).
bus_lock="$dir/.lock"
tries=${BUS_LOCK_TRIES:-100}   # 0.1 s apart: 10 s by default
[[ "$tries" =~ ^[1-9][0-9]*$ ]] || { echo "BUS_LOCK_TRIES must be a positive integer" >&2; exit 2; }
got_lock=0; i=0
while (( i++ < tries )); do
  if mkdir "$bus_lock" 2>/dev/null; then
    trap 'rm -rf "$bus_lock"' EXIT
    echo $$ > "$bus_lock/pid"
    got_lock=1; break
  fi
  sleep 0.1
done
if [ "$got_lock" != 1 ]; then
  owner=$(cat "$bus_lock/pid" 2>/dev/null || echo unknown)
  state="still running"   # kill -0 also fails for another user's process; a pid can be reused
  { [[ "$owner" =~ ^[0-9]+$ ]] && kill -0 "$owner" 2>/dev/null; } \
    || state="probably not running: remove the lock if no bus script is running"
  echo "bus is locked ($bus_lock, owner pid $owner $state)" >&2
  exit 3
fi

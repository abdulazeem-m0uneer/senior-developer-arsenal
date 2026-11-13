#!/usr/bin/env bash
# Sourced by send.sh, read.sh and archive.sh: one bus-wide lock file holding "<owner pid> <start epoch> <host>".
# It is created with noclobber, which opens with O_EXCL: atomic on Linux, macOS and Git-Bash, and needs no
# flock. (mkdir, used before, let several racing processes win on some systems.)
# A lock is stale when its owner's pid is gone (judged only on the host that wrote it), or when it is older
# than BUS_LOCK_STALE seconds (default 60; a bus script holds it for milliseconds). A lock with no owner written
# (killed between create and write) is aged in whole minutes by find -mmin, so it goes stale after 2 minutes by default. The next script takes a
# stale lock over. The takeover itself runs under a second lock file, so two waiting scripts cannot both
# remove the lock and both enter.
bus_lock="${dir:?lock.sh is sourced by the bus scripts, which set dir}/.lock"
bus_host=${HOSTNAME:-$(uname -n)}
bus_epoch=$(( $(date +%s) - SECONDS ))   # now is bus_epoch + SECONDS
tries=${BUS_LOCK_TRIES:-100}   # 0.1 s apart: 10 s by default
stale_after=${BUS_LOCK_STALE:-60}
[[ "$tries" =~ ^[1-9][0-9]*$ ]] || { echo "BUS_LOCK_TRIES must be a positive integer" >&2; exit 2; }
[[ "$stale_after" =~ ^[0-9]+$ ]] || { echo "BUS_LOCK_STALE must be a number of seconds" >&2; exit 2; }

bus_create() {   # $1 = lock file; fails when it already exists. No process per try: waiters try ten times a second
  local made=1
  set -C
  { printf '%s %s %s\n' "$$" "$(( bus_epoch + SECONDS ))" "$bus_host" > "$1"; } 2>/dev/null && made=0
  set +C
  return "$made"
}

bus_owner() {   # sets owner_pid, owner_started, owner_host from lock file $1; all empty without a readable owner
  owner_pid=""; owner_started=""; owner_host=""
  read -r owner_pid owner_started owner_host 2>/dev/null < "$1" || true
  if ! [[ "$owner_pid" =~ ^[0-9]+$ && "$owner_started" =~ ^[0-9]+$ ]]; then
    owner_pid=""; owner_started=""; owner_host=""
  fi
}

bus_stale() {   # $1 = lock file; succeeds when it may be taken over
  bus_owner "$1"
  if [ -z "$owner_pid" ]; then
    # No owner inside: written this instant, or left by a killed script or an older bus. Judge by file age.
    [ -n "$(find "$1" -maxdepth 0 -mmin +"$(( stale_after / 60 + 1 ))" 2>/dev/null)" ]
    return
  fi
  # kill -0 also fails for another user's live process, so ask ps as well. A pid means nothing on another host.
  [ "$owner_host" != "$bus_host" ] || kill -0 "$owner_pid" 2>/dev/null || ps -p "$owner_pid" > /dev/null 2>&1 \
    || return 0
  (( bus_epoch + SECONDS - owner_started > stale_after ))
}

bus_take_over() {   # removes a stale lock; succeeds when it removed one
  local guard="$bus_lock.takeover" removed=1
  if ! [ -e "$bus_lock" ] || ! bus_stale "$bus_lock"; then return 1; fi   # the usual case, and it costs no process
  if [ -e "$guard" ] && bus_stale "$guard"; then rm -rf "$guard"; fi
  bus_create "$guard" || return 1
  if [ -e "$bus_lock" ] && bus_stale "$bus_lock"; then
    rm -rf "$bus_lock" && removed=0
  fi
  rm -f "$guard"
  return "$removed"
}

bus_unlock() {   # removes the lock only when this process owns it
  bus_owner "$bus_lock"
  if [ "$owner_pid" = "$$" ] && [ "$owner_host" = "$bus_host" ]; then rm -f "$bus_lock"; fi
}

trap bus_unlock EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
got_lock=0; i=0
while (( i++ < tries )); do
  if bus_create "$bus_lock"; then got_lock=1; break; fi
  bus_take_over || sleep 0.1
done
if [ "$got_lock" != 1 ]; then
  bus_owner "$bus_lock"
  echo "bus is locked ($bus_lock, owner pid ${owner_pid:-unknown}); it is taken over once that process is gone" \
    "or the lock is older than $stale_after s" >&2
  exit 3
fi

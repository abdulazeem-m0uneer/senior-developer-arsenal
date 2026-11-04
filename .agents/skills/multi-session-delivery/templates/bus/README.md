# Session message bus

Durable copy of the messages between the sessions. Copy this folder to `<workspace>/.agents/bus/` and list the session names in `lanes.txt`, one per line (`pm` is always accepted). `lanes.txt`, `.agents/pm/lanes.json` and the lane table in the rules must name the same sessions.

- **Send:** `bash send.sh <to> <from> "<one line>"` appends `<ISO time> | from <sender> | <message>` to `inbox-<to>.md` (newlines become spaces), then send the live message.
- **Receive:** `bash read.sh <me>` prints the lines after your read mark (`read-mark-<me>.txt`, 0 when missing) and moves the mark. Act on each line.
- **Never** edit or delete lines by hand. Each week the coordinator runs `bash archive.sh 7`: under the bus lock it moves lines that are older than 7 days and already read to `archive/` and shifts the read mark. Unread lines always stay.
- All three scripts share one lock (`.lock`, a directory). The lock holds its owner's pid; when a script reports the owner as not running, remove the lock directory. Session names are lowercase letters, digits and hyphens.
- **No secrets** (tokens, keys, passwords, personal data) in any line.
- Renaming a session: add the new name to `lanes.txt`, test `send.sh` and `read.sh` with it, then update the rules files in the same step.

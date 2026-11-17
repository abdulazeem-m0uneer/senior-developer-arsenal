"""A fake `gh` for tests: a PATH-injected script that answers from recorded rules (not a test module itself)."""
import json
import os
import shutil
import stat
from pathlib import Path

STUB = '''#!/usr/bin/env python3
import json, os, sys, time
here = os.path.dirname(os.path.abspath(__file__))
args = " ".join(sys.argv[1:])
with open(os.path.join(here, "calls.log"), "a", encoding="utf-8") as log:
    log.write(args + "\\n")
for rule in json.load(open(os.path.join(here, "rules.json"), encoding="utf-8")):
    if all(part in args for part in rule["match"]) and not any(part in args for part in rule.get("unless", [])):
        time.sleep(rule.get("sleep", 0))
        sys.stdout.write(rule.get("stdout", ""))
        sys.stderr.write(rule.get("stderr", ""))
        sys.exit(rule.get("rc", 0))
sys.stderr.write("fake gh: no rule for: " + args)
sys.exit(97)
'''


class FakeGh:
    """`rules`: [{"match": [substrings], "unless": [...], "stdout": str|obj, "stderr": str, "rc": int, "sleep": s}]."""

    def __init__(self, directory):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        script = self.dir / "gh"
        script.write_text(STUB, encoding="utf-8")
        script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        self.rules([])

    def rules(self, rules):
        for rule in rules:
            if not isinstance(rule.get("stdout", ""), str):
                rule["stdout"] = json.dumps(rule["stdout"])
        (self.dir / "rules.json").write_text(json.dumps(rules), encoding="utf-8")

    def calls(self):
        log = self.dir / "calls.log"
        return log.read_text(encoding="utf-8").splitlines() if log.exists() else []

    def env(self):
        return {**os.environ, "PATH": f"{self.dir}{os.pathsep}{os.environ.get('PATH', '')}"}


def path_without_gh(directory):
    """A PATH holding git (and python3) but no gh at all."""
    bin_dir = Path(directory)
    bin_dir.mkdir(parents=True, exist_ok=True)
    for tool in ("git", "python3"):
        found = shutil.which(tool)
        if found and not (bin_dir / tool).exists():
            os.symlink(found, bin_dir / tool)
    return {**os.environ, "PATH": str(bin_dir)}

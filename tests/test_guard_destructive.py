import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "hooks" / "guard.py"

sys.dont_write_bytecode = True  # importing the hook module must not leave __pycache__ in the plugin
sys.path.insert(0, str(SCRIPT.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import hook_env  # noqa: E402
import guard_destructive  # noqa: E402

DANGEROUS = [
    "git push --force", "git push -f origin feature/x", "git push origin +feature/x", "git push --mirror backup",
    "git push -uf origin work", "git push --force-with-lease origin main", "git push --force-with-lease origin HEAD:release/2.1",
    "git push --force-with-lease", "git push --force-with-lease origin stable", "git push origin --delete main",
    "git push origin :master", "git -C repo -c user.name=x push --force", "sudo -u deploy git push -f",
    "git reset --hard", "git reset --hard HEAD~3", "cd api && git reset --hard origin/main", "FOO=1 git reset --hard",
    "git clean -fd", "git clean -fdx", "git clean -f -d", "git clean --force", "timeout 30 git clean -xfd",
    "git checkout .", "git checkout -- .", "git checkout HEAD -- .", "git checkout -f", "git checkout --force main",
    "git restore .", "git restore --staged --worktree .", "git restore -SW :/", "git branch -D feature/x",
    "git branch -d -f old", "git branch --delete --force old",
    "rm -rf /", "rm -rf /*", "rm -fr ~", "rm -rf ~/", "rm -rf ~/*", 'rm -rf "$HOME"', "rm -rf ${HOME}/", "rm -rf .",
    "rm -rf ..", "rm -rf ../..", "rm -rf ./*", "rm -rf *", "rm -r -f /usr", "rm --recursive --force /etc/",
    "rm -R /", "rm -rf --no-preserve-root /", "rm -rf build /", "sudo rm -rf /var", "rm -rf -- .",
    "rm -rf {repo}", "rm -rf .git", "rm -rf sub/../.git/", "rm -rf {repo}/", "rm -rf {repo}/*", "rm -rf {home}",
    'psql -c "DROP TABLE users"', "psql -d app -c 'drop database app;'", 'mysql -e "TRUNCATE TABLE orders"',
    'sqlcmd -Q "DROP TABLE dbo.Users"', 'sqlite3 app.db "drop table users;"', 'echo "DROP TABLE users;" | psql app',
    "psql app <<EOF\nTRUNCATE users;\nEOF", 'docker exec db psql -U app -c "DROP SCHEMA public CASCADE"',
    "dropdb app", "mysqladmin -f drop app", 'mariadb -e "truncate orders"',
    "terraform destroy", "terraform -chdir=infra destroy -auto-approve", "terraform apply -destroy", "tofu destroy",
    "kubectl delete namespace prod", "kubectl delete ns/prod", "kubectl -n prod delete pods --all",
    "kubectl delete deployments --all-namespaces --all", "docker system prune -a --volumes", "docker system prune -af --volumes",
    "dd if=/dev/zero of=/dev/sda bs=1M", "sudo dd if=image.iso of=/dev/nvme0n1", "mkfs.ext4 /dev/sdb1", "mkfs -t ext4 /dev/sdb1",
    "chmod -R 777 /", "chmod -R 777 .", "chmod -R 0777 ~", "chmod --recursive a+rwx {repo}",
    'bash -c "git reset --hard"', "sh -lc 'rm -rf /'", 'eval "git clean -fd"', "echo $(git reset --hard)",
    "ls; git reset --hard", "true && rm -rf ~", "if true; then git clean -fd; fi", "x=`git reset --hard`",
    "cat > notes.md <<'EOF'\nit's fine\nEOF\ngit push --force origin main", "python3 - <<'EOF'\n# don't\nEOF\ngit push --force",
    "cat > a.md <<'EOF'\nit's fine\nEOF\nrm -rf ~", "cat <<EOF && git reset --hard\nbody\nEOF",
    "git switch -f main", "git switch --discard-changes main", "git reset --har", "git clean --forc",
    "git push --del origin main", ">out git push -f", "2>/dev/null git push -f", "2>&1 git push -f",
    'rm -rf "$UNSET_DIR"/*', "rm -rf $UNSET_DIR/", 'rm -rf "${DIR}"/*', "rm -rf $PWD", 'rm -rf "$(pwd)"',
    "cd / && rm -rf etc", "git -C .. push --force-with-lease origin main",
    "(cd sub && git checkout .)", "ls\ngit reset --hard", "git status |\\\n  cat; git reset \\\n  --hard",
]

SAFE = [
    'echo "git push --force"', "echo 'git reset --hard'", 'grep -rn "git reset --hard" docs/', 'grep -n "rm -rf /" README.md',
    "git log --grep 'reset --hard'", 'git commit -m "never run rm -rf / or git push --force"', "rg 'DROP TABLE' migrations/",
    "git push", "git push origin feature/x", "git push -u origin HEAD", "git push --force-with-lease origin feature/x",
    "git push --force-with-lease origin HEAD:feature/x", "git push --force --dry-run", "git push origin --delete old-topic",
    "git push --follow-tags", "git reset --soft HEAD~1", "git reset HEAD file.py", "git reset --keep HEAD~1",
    "git clean -n", "git clean -nfd", "git clean --dry-run -fd", "git checkout main", "git checkout -b fix/x",
    "git checkout -- src/app.py", "git checkout HEAD~1 -- docs/a.md", "git restore src/app.py", "git restore --staged .",
    "git branch -d merged", "git branch --list -a", "git branch -m old new", "git stash",
    "git switch main", "git switch -c topic", "git push --force-with-lease --dry-run", "2>/dev/null git status",
    "rm -rf $BUILD_DIR", 'rm -rf "$BUILD_DIR/cache"', "cd build && rm -rf cache",
    "rm -rf build", "rm -rf ./dist", "rm -rf node_modules/.cache", "rm -rf /tmp/work/x", "rm -f *.pyc", "rm notes.txt",
    "rm -rf src/*", "rm -rf $HOME/.cache/pip", "rm -rf ~/project/build", "rm -rf {repo}/dist", "rm -rf .github", "rm .git/index.lock", "rm -i .",
    'psql -c "SELECT 1"', 'psql -c "select date_trunc(\'day\', now())"', "psql -f migrations/001.sql",
    'sqlite3 app.db ".schema" | grep -i "drop table"', 'echo "DROP TABLE users"', "cat drop_table.sql", "mysql -e 'show tables'",
    "terraform plan", "terraform plan -destroy", "terraform apply", "kubectl delete pod web-1", "kubectl delete pod web -n ns", "kubectl delete pod ns", "kubectl get namespace",
    "kubectl delete pods --all --dry-run=client", "kubectl apply -f ns.yaml", "docker system prune", "docker system prune -a",
    "docker volume ls", "dd if=/dev/zero of=disk.img bs=1M count=10", "dd if=in of=/dev/null", "mkfs.ext4 disk.img",
    "chmod -R 755 .", "chmod 777 run.sh", "chmod -R 777 build/cache", "chmod +x scripts/build.py",
    'bash -c "echo git reset --hard"', "sh -c 'ls -la'", "echo rm -rf /", "ls -la", "pytest -q", "",
    "cat > docs/notes.md <<'EOF'\n# Rules\ngit push --force is banned\nEOF", "cat <<'EOF' > s.sh\nrm -rf /\nEOF",
    "cat > x.md <<EOF\nit's rm -rf ~ and git reset --hard\nEOF\nls", "echo $((1 << 2))\ngit status",
    "printf '%s\\n' \"it's\" 'git reset --hard", "# git reset --hard", "git", "rm", "sudo", "timeout 5",
]


class Sandbox(unittest.TestCase):
    """A directory that looks like a repository on branch feature/x whose origin default branch is 'stable'."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(os.path.realpath(self.tmp.name)) / "repo"
        (self.repo / ".git" / "refs" / "remotes" / "origin").mkdir(parents=True)
        (self.repo / ".git" / "HEAD").write_text("ref: refs/heads/feature/x\n")
        (self.repo / ".git" / "refs" / "remotes" / "origin" / "HEAD").write_text("ref: refs/remotes/origin/stable\n")
        (self.repo / "sub").mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def fill(self, command):
        return command.replace("{repo}", str(self.repo)).replace("{home}", os.path.expanduser("~"))

    def set_branch(self, name):
        (self.repo / ".git" / "HEAD").write_text(f"ref: refs/heads/{name}\n")


class DetectionTest(Sandbox):
    def test_dangerous_commands_are_named_with_an_alternative(self):
        self.set_branch("stable")  # a bare --force-with-lease pushes the current branch
        for command in DANGEROUS:
            reason = guard_destructive.destructive(self.fill(command), str(self.repo))
            self.assertTrue(reason, command)
            self.assertNotIn("\n", reason)
            self.assertLess(len(reason), 140, command)

    def test_look_alikes_are_left_alone(self):
        for command in SAFE:
            self.assertEqual(guard_destructive.destructive(self.fill(command), str(self.repo)), "", command)

    def test_lease_is_judged_by_the_branch_it_would_push(self):
        lease = "git push --force-with-lease"
        self.assertEqual(guard_destructive.destructive(lease, str(self.repo)), "")  # on feature/x
        self.assertEqual(guard_destructive.destructive(lease, str(self.repo / "sub")), "")
        for branch in ("stable", "main", "release/1.2"):  # origin's default, a protected name, a release line
            self.set_branch(branch)
            self.assertTrue(guard_destructive.destructive(lease, str(self.repo / "sub")), branch)
        (self.repo / ".git" / "HEAD").write_text("0123456789abcdef\n")  # detached: unknown is not a hit
        self.assertEqual(guard_destructive.destructive(lease, str(self.repo)), "")

    def test_a_linked_worktree_reads_its_own_head_and_the_shared_default_branch(self):
        private = self.repo / ".git" / "worktrees" / "wt"
        private.mkdir(parents=True)
        (private / "HEAD").write_text("ref: refs/heads/stable\n")
        (private / "commondir").write_text("../..\n")
        tree = self.repo.parent / "wt"
        tree.mkdir()
        (tree / ".git").write_text(f"gitdir: {private}\n")
        self.assertTrue(guard_destructive.destructive("git push --force-with-lease", str(tree)))
        self.assertTrue(guard_destructive.destructive(f"rm -rf {tree}", str(tree)))

    def test_relative_targets_resolve_against_the_working_directory(self):
        outside = str(self.repo.parent)
        self.assertTrue(guard_destructive.destructive("rm -rf repo", outside))  # the repository root, named from above
        self.assertEqual(guard_destructive.destructive("rm -rf repo/dist", outside), "")
        self.assertEqual(guard_destructive.destructive("rm -rf sub", str(self.repo)), "")

    def test_the_top_level_of_the_shared_session_scratchpad_is_refused(self):
        sid = "/tmp/claude-1000/-srv-repo/0b6c2f1e-9d4a-4c1b-8e2f-3a5d7c9b1e04"
        pad = sid + "/scratchpad"
        refused = [
            f"rm -rf {pad}/*", f"rm -rf {pad}/.*", f"rm -rf {pad}/*.log", f"rm -r {pad}/x*", f"rm -fr {pad}/[ab]*",
            f"rm -R {pad}", f"rm --recursive {pad}/", f"rm -rf {pad}/agent-a/..", f"rm -rf {pad}/./*",
            f"rm -f {pad}/*.log", f"rm {pad}/?", f'rm -rf "{pad}"/*', f"sh -c 'rm -rf {pad}/*'",
            f"cd {pad} && rm -rf *.md", f"cd {pad} && rm -f *", f"cd {sid} && rm -f scratchpad/*.log",
            "rm -rf /private/tmp/claude-501/-Users-me-repo/abc/scratchpad/*",
            "rm -rf /var/folders/zz/x1y2/T/claude-501/-Users-me-repo/abc/scratchpad/*",
            f"rm -fr {pad}/[ab]", f"rm -rf {pad}/agent-a {pad}/*", f"rm -rf {pad}/*/*", f"rm -f {pad}/*/*.log",
            "rm -f /tmp/claude-1000/-p/*/scratchpad/*.log", "rm -rf /tmp/claude-1000/-p/*/scratchpad",
            "rm -rf /tmp/claude-*/-srv-repo/*/scratchpad/*", "rm -rf /tmp/claude-[0-9]*/-p/s/scratchpad",
            "rm -rf /private/var/folders/zz/x1/T/claude-501/-U/abc/scratchpad/*"]
        for command in refused:
            reason = guard_destructive.destructive(command, str(self.repo))
            self.assertIn("scratchpad", reason, command)
            self.assertNotIn("\n", reason)
            self.assertLess(len(reason), 140, command)
        passed = [
            f"rm -rf {pad}/agent-a/*", f"rm -rf {pad}/agent-a", f"rm -f {pad}/file.txt", f"rm -f {pad}",
            f"cd {pad} && rm -rf agent-a", f"cd {pad} && rm -f notes.md", f"rm -rf {pad}2/*", f"echo rm -rf {pad}/*",
            "rm -rf ~/notes/scratchpad/*", "rm -rf /tmp/notes/scratchpad/*", "rm -rf /srv/claude-1000/a/b/scratchpad/*",
            "rm -f /tmp/claude-1000/-srv-repo/scratchpad/*", "rm -rf /tmp/claude-1000/a/b/c/scratchpad/*",
            f"rm -f {sid}/*.log", f"rm -rf {pad}/agent-a/*/*", f"rm -f {sid}/notes.md",
            "rm -rf /tmp/claude-x/a/b/scratchpad/*", "rm -rf /tmp/xclaude-1000/a/b/scratchpad/*",
            "rm -rf /tmp/claude-1000/-srv-repo/$SESSION/scratchpad/*", 'rm -rf "$TMPDIR"/claude-1000/a/b/scratchpad/*',
            f"rm -f {pad}/agent-a/*.log", "rm -f /tmp/xclaude-1000/a/b/scratchpad/*", f"rm -rf {pad}/agent-a/claude-3/out",
            f"rm -rf {pad}/agent-a/claude-3", f"rm -rf {pad}/claude-2", f"rm -rf {pad}/agent-a/claude-3/x/y/scratchpad/*",
            "rm -rf /tmp/build/claude-1/dist", "rm -rf /tmp/pytest-of-u/claude-0/x", "rm -rf /tmp/claude-1000/tmp-xyz",
            "rm -rf /tmp/claude-1000/-p/somefile.json", f"rm -rf {sid}", f"rm -rf {sid}/*", f"rm -rf {pad}/..", f"rm -rf {sid}/scratch*",
            "rm -rf /tmp/claude-1000/-srv-repo/*", "rm -rf /tmp/claude-1000", "rm -f /tmp/claude-1000/-p/*/scratchpad/a.md",
            "rm -rf /tmp/build/claude-1000/-srv-repo/abc/scratchpad/*",
            "rm -rf /var/folders/zz/x1/T/a/T/claude-5/-U/a/scratchpad/*"]
        with mock.patch.dict(os.environ, clear=False) as environ:
            environ.pop("TMPDIR", None)
            for command in passed:
                self.assertEqual(guard_destructive.destructive(command, str(self.repo)), "", command)

    def test_tmpdir_is_a_temp_root_for_the_scratchpad(self):
        with mock.patch.dict(os.environ, {"TMPDIR": "/srv/tmpdir/"}):
            for command in ("rm -rf /srv/tmpdir/claude-1000/-srv-repo/abc/scratchpad/*",
                            'rm -rf "$TMPDIR"/claude-1000/-srv-repo/abc/scratchpad/*',
                            "rm -rf ${TMPDIR}claude-1000/-srv-repo/abc/scratchpad/*.log"):
                self.assertIn("scratchpad", guard_destructive.destructive(command, str(self.repo)), command)
            for command in ("rm -rf /srv/tmpdir/claude-1000/-srv-repo/abc/scratchpad/agent-a/*",
                            "rm -rf $TMPDIRX/claude-1000/-srv-repo/abc/scratchpad/*"):  # another variable
                self.assertEqual(guard_destructive.destructive(command, str(self.repo)), "", command)
        with mock.patch.dict(os.environ, {"TMPDIR": "/srv/tmp"}):  # no trailing slash, and a sibling of it
            self.assertIn("scratchpad", guard_destructive.destructive(
                "rm -rf ${TMPDIR:-/tmp}/claude-1000/-srv-repo/abc/scratchpad/*", str(self.repo)))
            self.assertIn("scratchpad", guard_destructive.destructive(
                "rm -rf /srv/tmp/claude-1000/a/b/scratchpad/*", str(self.repo)))
            self.assertEqual(guard_destructive.destructive(
                "rm -rf /srv/tmpx/claude-1000/a/b/scratchpad/*", str(self.repo)), "")

    def test_a_tmpdir_default_and_home_are_expanded_for_the_scratchpad(self):
        with mock.patch.dict(os.environ, {"HOME": "/tmp/h"}) as environ:
            environ.pop("TMPDIR", None)
            for command in ('rm -rf "${TMPDIR:-/tmp}"/claude-1000/-srv/abc/scratchpad/*',
                            "rm -f ${TMPDIR-/tmp}/claude-1000/-srv/abc/scratchpad/*.log",
                            "rm -rf ~/../claude-1000/a/b/scratchpad/*"):
                self.assertIn("scratchpad", guard_destructive.destructive(command, "/srv"), command)
            for command in ("rm -rf ${TMPDIR:-/srv}/claude-1000/-srv/abc/scratchpad/*",
                            "rm -rf ${TMPDIR:-$X}/claude-1000/-srv/abc/scratchpad/*"):
                self.assertEqual(guard_destructive.destructive(command, str(self.repo)), "", command)

    def test_long_and_hostile_input_is_handled_in_linear_time(self):
        started = time.monotonic()
        for command in ("echo " + "a " * 50000, "rm " + "-" * 50000, "git push " + "'" * 9999, ";" * 50000,
                        "sudo " * 20000 + "ls", 'bash -c "bash -c \\"bash -c \'git reset --hard\'\\""', "\x00\xff(`"):
            guard_destructive.destructive(command, str(self.repo))
        self.assertLess(time.monotonic() - started, 5)


class HookTest(Sandbox):
    def run_hook(self, payload, env=None):
        stdin = payload if isinstance(payload, str) else json.dumps(payload)
        base = {key: value for key, value in os.environ.items()
                if key not in ("ARSENAL_GUARD", "ARSENAL_GUARD_DESTRUCTIVE", "ARSENAL_RUN_LIMITS", "CLAUDE_PROJECT_DIR")}
        base["HANDOFF_SNAPSHOT"] = str(Path(self.tmp.name) / "snap.md")
        base.update(hook_env.lesson_guard_files(self.tmp.name))
        result = subprocess.run([sys.executable, str(SCRIPT), "pre"], cwd=self.repo, input=stdin, capture_output=True,
                                text=True, env={**base, **(env or {})})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        return result.stdout

    def bash(self, command, mode="default", **kwargs):
        payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": command},
                   "cwd": str(self.repo), "session_id": "s1"}
        if mode is not None:
            payload["permission_mode"] = mode
        out = self.run_hook(payload, **kwargs)
        return json.loads(out)["hookSpecificOutput"] if out else None

    def test_unattended_modes_deny_with_the_alternative(self):
        for mode in ("bypassPermissions", "dontAsk", "auto"):
            out = self.bash("git reset --hard", mode)
            self.assertEqual(out["hookEventName"], "PreToolUse")
            self.assertEqual(out["permissionDecision"], "deny", mode)
            self.assertIn("git stash", out["permissionDecisionReason"])
            self.assertEqual(set(out), {"hookEventName", "permissionDecision", "permissionDecisionReason"})
            self.assertLess(len(out["permissionDecisionReason"]), 300)

    def test_interactive_and_unknown_modes_ask_the_human(self):
        for mode in ("default", "acceptEdits", "plan", None, "somethingNew", 7):
            out = self.bash("rm -rf ~", mode)
            self.assertEqual(out["permissionDecision"], "ask", mode)
            self.assertIn("name the exact directories", out["permissionDecisionReason"])

    def test_every_other_call_prints_nothing(self):
        for command in ("ls -la", 'echo "git push --force"', "git status", "rm -rf build"):
            self.assertIsNone(self.bash(command, "bypassPermissions"), command)
        other_tool = {"tool_name": "Write", "tool_input": {"file_path": "a.py", "content": "git reset --hard"},
                      "permission_mode": "bypassPermissions"}
        self.assertEqual(self.run_hook(other_tool), "")
        self.assertEqual(list(Path(self.tmp.name).glob("snap*")), [])  # and writes nothing without a limits file

    def test_opt_outs(self):
        self.assertIsNone(self.bash("git reset --hard", "auto", env={"ARSENAL_GUARD": "off"}))
        self.assertIsNone(self.bash("git reset --hard", "auto", env={"ARSENAL_GUARD_DESTRUCTIVE": "allow"}))
        self.assertIsNotNone(self.bash("git reset --hard", "auto", env={"ARSENAL_GUARD_DESTRUCTIVE": "deny"}))

    def test_garbage_input_fails_open(self):
        for stdin in ("", "not json", "[]", "null", '{"tool_name": "Bash"}', '{"tool_name": "Bash", "tool_input": 5}',
                      '{"tool_name": "Bash", "tool_input": {"command": ["git", "reset", "--hard"]}}',
                      '{"tool_name": "Bash", "tool_input": {"command": null}, "cwd": 3}'):
            self.assertEqual(self.run_hook(stdin), "", stdin)

    def test_a_missing_working_directory_still_decides(self):
        payload = {"tool_name": "Bash", "tool_input": {"command": "git clean -fdx"}, "cwd": "/no/such/dir/anywhere"}
        self.assertEqual(json.loads(self.run_hook(payload))["hookSpecificOutput"]["permissionDecision"], "ask")

    def test_no_subprocess_and_a_small_wall_time(self):
        source = "".join((SCRIPT.parent / name).read_text(encoding="utf-8") for name in ("guard_destructive.py", "guard_limits.py"))
        self.assertNotIn("subprocess", source.replace("no subprocess", ""))
        started = time.monotonic()
        for _ in range(5):
            self.bash("pytest -q && git status", "bypassPermissions")
        self.assertLess((time.monotonic() - started) / 5, 1.0)  # generous: a loaded CI runner must not flake


if __name__ == "__main__":
    unittest.main()

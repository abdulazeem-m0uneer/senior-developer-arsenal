"""Tests for the opt-in container-limits lesson guard (hooks/guard_container_limits.py, wired in guard_lessons)."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HOOKS = Path(__file__).resolve().parent.parent / "hooks"
sys.path.insert(0, str(HOOKS))

import guard_container_limits  # noqa: E402
import guard_lessons  # noqa: E402

ENTRY = {"rule": "container-limits", "lesson": "G052", "min_version": "1.38.0"}
LIMITS = "-m 512m --cpus 1"


class LimitsCase(unittest.TestCase):
    """A project whose registry names container-limits, and a 1.38.0 hook."""

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.dir = Path(folder.name)
        self.project = self.dir / "project"
        (self.project / ".agents").mkdir(parents=True)
        env = {"LESSONS_GUARDS_GLOBAL_FILE": str(self.dir / "home" / "lesson-guards.json"),
               "LESSONS_GUARD_HITS_FILE": str(self.dir / "home" / "hits.jsonl")}
        for patch in (mock.patch.dict(os.environ, env), mock.patch.object(guard_lessons, "HOOK_VERSION", (1, 38, 0))):
            patch.start()
            self.addCleanup(patch.stop)
        os.environ.pop("CLAUDE_PROJECT_DIR", None)
        self.registry(ENTRY)

    def registry(self, *guards):
        (self.project / ".agents" / "lesson-guards.json").write_text(json.dumps({"guards": list(guards)}),
                                                                     encoding="utf-8")

    def judge(self, command):
        return guard_lessons.judge(command, str(self.project))

    def refused(self, command):
        hit = self.judge(command)
        self.assertIsNotNone(hit, command)
        self.assertEqual((hit.rule, hit.lesson), ("container-limits", "G052"), command)
        return hit

    def passes(self, command):
        self.assertIsNone(self.judge(command), command)


class RunTests(LimitsCase):
    def test_run_without_any_limit_is_refused(self):
        for command in ("docker run alpine", "podman run alpine", "docker container run alpine",
                        "docker run --rm -it -e A=b -v /a:/b alpine sh", "sudo docker run alpine",
                        "bash -c 'docker run alpine'", "docker ps && docker run alpine"):
            self.refused(command)

    def test_a_short_option_with_an_equals_sign_is_read_as_its_value(self):
        self.passes("docker run -m=512m --cpus 1 alpine")
        self.refused("docker run -m=0 --cpus 1 alpine")
        self.refused("docker run -m=512m alpine")

    def test_podman_options_that_take_a_value_do_not_hide_the_limits(self):
        for options in ("--arch amd64", "--os linux", "--variant v8", "--cgroups disabled", "--pidfile /tmp/p",
                        "--conmon-pidfile /tmp/c", "--rdt-class gold", "--systemd always", "--health-on-failure kill",
                        "--health-log-destination local", "--health-max-log-count 5", "--health-max-log-size 100",
                        "--health-startup-cmd true", "--health-startup-interval 5s", "--health-startup-retries 3",
                        "--health-startup-success 1", "--health-startup-timeout 5s", "--hostuser root",
                        "--chrootdirs /x", "--group-entry x", "--exit-command-delay 5"):
            with self.subTest(options=options):
                self.passes(f"podman run {options} -m 1g --cpus 1 alpine")
                self.refused(f"podman run {options} alpine")

    def test_run_with_only_memory_is_refused_and_asks_for_cpu(self):
        for command in ("docker run -m 512m alpine", "docker run --memory=1g alpine", "docker run -m512m alpine",
                        "docker run --memory 1g --cpu-period 100000 alpine"):
            self.assertIn("--cpus", self.refused(command).reason, command)

    def test_run_with_only_cpu_is_refused_and_asks_for_memory(self):
        for command in ("docker run --cpus 1 alpine", "docker run --cpus=0.5 alpine", "docker run --cpu-quota 50000 alpine",
                        "docker run --cpuset-cpus 0-1 alpine", "docker run --memory-swap 2g --cpus 1 alpine"):
            self.assertIn("--memory", self.refused(command).reason, command)

    def test_zero_or_empty_limits_do_not_count(self):
        for command in ("docker run -m 0 --cpus 1 alpine", "docker run -m 512m --cpus 0 alpine",
                        "docker run -m 512m --cpu-quota -1 alpine", "docker run -m 512m --cpus=0.0 alpine",
                        "docker run --memory= --cpus 1 alpine", "docker run -m 0m --cpus 1 alpine"):
            self.refused(command)

    def test_run_with_both_limits_passes(self):
        for command in (f"docker run --rm {LIMITS} trivy:0.5", "docker run -m512m --cpu-quota 50000 alpine",
                        "docker run --memory=1g --cpuset-cpus 0-1 alpine", "docker run --memory 1g --cpus=2 alpine",
                        "podman run -m 1g --cpus 1 ghcr.io/x/scanner:1", "docker run -it -m 1g --cpus 1 alpine",
                        f"docker run -e A=b -v /a:/b -p 80:80 {LIMITS} alpine"):
            self.passes(command)

    def test_value_options_do_not_hide_the_limits_after_them(self):
        self.passes(f"docker run --network-alias foo {LIMITS} nginx")
        for option in ("--network-alias", "--net-alias", "--memory-swappiness", "--cpu-rt-runtime", "--cpu-rt-period",
                       "--device-cgroup-rule", "--link-local-ip", "--blkio-weight-device", "--cpu-count",
                       "--cpu-percent", "--device-read-iops", "--device-write-iops", "--health-start-interval",
                       "--volume-driver", "--secret", "--tz", "--pod", "--uidmap", "--gidmap", "--unsetenv",
                       "--authfile", "--env-merge", "--image-volume", "--timeout", "--sdnotify", "--umask"):
            with self.subTest(option=option):
                self.passes(f"docker run {option} value {LIMITS} nginx")

    def test_number_forms_docker_accepts_count(self):
        for command in ("docker run -m 1g --cpus .5 alpine", "docker run -m 1g --cpus 1. alpine",
                        "docker run -m 1g --cpus 1e0 alpine", "docker run -m 1g --cpus=.25 alpine"):
            self.passes(command)

    def test_a_variable_limit_value_is_not_seen_and_passes(self):
        for command in ("docker run -m $M --cpus 1 alpine", "docker run -m 1g --cpus $N alpine",
                        "docker run -m ${MEM} --cpus \"$N\" alpine"):
            self.passes(command)
        self.refused("docker run $IMG")

    def test_the_last_value_of_a_limit_wins(self):
        for command in ("docker run -m 1g --cpus 1 --memory 0 alpine", "docker run -m 1g --cpus 1 -m 0 alpine",
                        "docker run -m 1g --cpus 1 --cpus 0 alpine", "docker run -m 1g --cpus 1 --cpus=0 alpine"):
            self.refused(command)
        self.passes("docker run -m 0 --memory 1g --cpus 0 --cpus 1 alpine")

    def test_create_is_judged_like_run(self):
        for command in ("docker create alpine", "docker container create alpine", "podman create alpine"):
            self.refused(command)
        self.passes(f"docker create {LIMITS} alpine")
        self.passes("docker create --help")

    def test_other_docker_commands_pass(self):
        for command in ("docker ps", "docker stats --no-stream", "docker logs web", "docker exec web ls",
                        "docker run --help", "docker run --help alpine", "docker build -t x .", "echo docker run alpine", "ls"):
            self.passes(command)

    def test_allowed_image_passes_by_basename_before_the_tag(self):
        self.registry({**ENTRY, "allow": ["scanner", "nginx"]})
        for command in ("docker run ghcr.io/x/scanner:1.2 --scan", "docker run scanner", "docker run --name web nginx",
                        "docker run -v /a:/b -e A=b nginx@sha256:abc"):
            self.passes(command)

    def test_image_is_the_first_operand_not_an_option_value(self):
        self.registry({**ENTRY, "allow": ["web"]})
        self.refused("docker run --name web nginx")
        self.refused("docker run nginx web")  # an argument of the image is not the image

    def test_unlisted_image_is_refused_when_others_are_allowed(self):
        self.registry({**ENTRY, "allow": ["scanner"]})
        self.refused("docker run alpine")


class ComposeTests(LimitsCase):
    def test_compose_up_passes_unless_the_entry_asks_for_a_project_name(self):
        for command in ("docker compose up -d", "docker-compose up"):
            self.passes(command)

    def test_compose_up_without_a_name_is_refused(self):
        self.registry({**ENTRY, "compose_project": True})
        for command in ("docker compose up -d", "docker-compose up", "docker compose -f a.yml up",
                        "docker compose --profile x -f a.yml up --build", "docker -H tcp://h compose up",
                        "COMPOSE_PROJECT_NAME= docker compose up"):
            self.assertIn("--project-name", self.refused(command).reason, command)

    def test_compose_up_with_a_name_passes(self):
        self.registry({**ENTRY, "compose_project": True})
        for command in ("docker compose -p run1 up", "docker compose --project-name run1 up -d",
                        "docker-compose --project-name=run1 up", "docker compose -f a.yml -p x up",
                        "COMPOSE_PROJECT_NAME=run1 docker compose up", "docker compose -prun1 up"):
            self.passes(command)

    def test_a_name_from_a_compose_file_or_env_file_passes(self):
        self.registry({**ENTRY, "compose_project": True})
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        here = Path(folder.name)
        old = os.getcwd()
        os.chdir(here)
        self.addCleanup(os.chdir, old)
        self.refused("docker compose up")
        (here / "compose.yaml").write_text("services:\n  a: {}\n", encoding="utf-8")
        self.refused("docker compose up")
        (here / "compose.yaml").write_text("name: shared\nservices:\n  a: {}\n", encoding="utf-8")
        self.passes("docker compose up")
        self.passes("docker-compose up")
        (here / "compose.yaml").unlink()
        (here / ".env").write_text("A=1\nCOMPOSE_PROJECT_NAME=envname\n", encoding="utf-8")
        self.passes("docker compose up")
        (here / ".env").write_text("COMPOSE_PROJECT_NAME=\n", encoding="utf-8")
        self.refused("docker compose up")
        (here / "my.env").write_text("export COMPOSE_PROJECT_NAME=x\n", encoding="utf-8")
        self.passes("docker compose --env-file my.env up")
        (here / "other.yml").write_text("name: o\n", encoding="utf-8")
        self.passes("docker compose -f other.yml up")
        self.refused("docker compose -f missing.yml up")

    def test_other_compose_commands_pass(self):
        self.registry({**ENTRY, "compose_project": True})
        for command in ("docker compose down", "docker compose ps", "docker compose logs web",
                        "docker compose up --help", "docker-compose config"):
            self.passes(command)

    def test_compose_flag_does_not_turn_the_run_check_off(self):
        self.registry({**ENTRY, "compose_project": True})
        self.refused("docker run alpine")


class RegistryTests(LimitsCase):
    def problems(self, *guards):
        self.registry(*guards)
        return guard_lessons.registry_problems(str(self.project))

    def test_valid_entries_have_no_problem(self):
        self.assertEqual(self.problems({**ENTRY, "allow": ["scanner"], "compose_project": True}), [])

    def test_bad_values_are_reported(self):
        self.assertTrue(self.problems({**ENTRY, "compose_project": "yes"}))
        self.assertTrue(self.problems({**ENTRY, "allow": "scanner"}))
        self.assertTrue(self.problems({"rule": "help-probe", "compose_project": True, "min_version": "1.38.0"}))

    def test_entry_is_off_for_an_older_hook(self):
        with mock.patch.object(guard_lessons, "HOOK_VERSION", (1, 37, 1)):
            self.passes("docker run alpine")

    def test_no_entry_means_off(self):
        self.registry()
        self.passes("docker run alpine")

    def test_entry_reason_replaces_the_built_in_text(self):
        self.registry({**ENTRY, "reason": "Use the wrapper."})
        self.assertEqual(self.refused("docker run alpine").reason, "Use the wrapper.")


class NeverRaisesTests(unittest.TestCase):
    def test_bad_input_passes(self):
        for command, entry in ((None, {}), ("docker run alpine", None), ("", {}), (5, {})):
            self.assertIsNone(guard_container_limits.problem(command, entry))

    def test_a_failing_parser_passes(self):
        def broken(_command):
            raise ValueError("boom")
        self.assertIsNone(guard_container_limits.problem("docker run alpine", {}, broken))

    def test_text_without_a_container_tool_is_not_parsed(self):
        parsed = []
        self.assertIsNone(guard_container_limits.problem("ls -la", {}, lambda command: parsed.append(command) or []))
        self.assertEqual(parsed, [])


if __name__ == "__main__":
    unittest.main()

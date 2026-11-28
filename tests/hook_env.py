"""Environment for running the plugin's hooks in a test, away from the developer's own lesson-guard files."""
from pathlib import Path


def lesson_guard_files(folder):
    """The hit log and the global guard registry inside `folder`: a refusal in a test never reaches the developer's
    ~/.agents/lesson-guard-hits.jsonl, their ~/.agents/lesson-guards.json never changes a test's result, and the
    unseen-time cache of seen times stays out of ~/.cache."""
    folder = Path(folder)
    return {"LESSONS_GUARD_HITS_FILE": str(folder / "lesson-guard-hits.jsonl"),
            "LESSONS_GUARDS_GLOBAL_FILE": str(folder / "no-global-lesson-guards.json"),
            "ARSENAL_SEEN_TIMES_DIR": str(folder / "seen-times")}

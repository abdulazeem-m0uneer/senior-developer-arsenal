#!/usr/bin/env bash
set -euo pipefail
mkdir -p users
cat > users/__init__.py <<'SRC'
SRC
mkdir -p users
cat > users/repo.py <<'SRC'
_NAMES = {}
READS = {"count": 0}


def get_name(user_id):
    READS["count"] += 1
    return _NAMES.get(user_id)


def set_name(user_id, name):
    _NAMES[user_id] = name
SRC
mkdir -p users
cat > users/cache.py <<'SRC'
from functools import lru_cache

from users import repo


@lru_cache(maxsize=10_000)
def display_name(user_id):
    """The header calls this on every page view; the cache keeps it off the database."""
    return repo.get_name(user_id) or "Guest"
SRC
mkdir -p users
cat > users/service.py <<'SRC'
from users import repo


def rename(user_id, new_name):
    new_name = new_name.strip()
    if not new_name:
        raise ValueError("name must not be empty")
    repo.set_name(user_id, new_name)
SRC
mkdir -p web
cat > web/__init__.py <<'SRC'
SRC
mkdir -p web
cat > web/header.py <<'SRC'
from users.cache import display_name


def header(user_id):
    return f"Signed in as {display_name(user_id)}"
SRC

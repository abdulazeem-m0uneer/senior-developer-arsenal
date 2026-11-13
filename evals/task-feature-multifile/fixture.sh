#!/usr/bin/env bash
set -euo pipefail
mkdir -p app
cat > app/__init__.py <<'PY'
PY
cat > app/models.py <<'PY'
from dataclasses import dataclass


@dataclass
class User:
    id: int
    name: str
    role: str = "member"
    active: bool = True
PY
cat > app/repo.py <<'PY'
from app.models import User

_USERS = {}


def save(user: User) -> User:
    _USERS[user.id] = user
    return user


def get(user_id: int):
    return _USERS.get(user_id)


def all_users():
    return list(_USERS.values())
PY
cat > app/service.py <<'PY'
from app import repo
from app.models import User


class NotFound(Exception):
    pass


def create_user(user_id: int, name: str, role: str = "member") -> User:
    return repo.save(User(id=user_id, name=name, role=role))


def get_user(user_id: int) -> User:
    user = repo.get(user_id)
    if user is None:
        raise NotFound(user_id)
    return user
PY
cat > app/api.py <<'PY'
from app import service


def handle_get_user(user_id: int):
    try:
        user = service.get_user(user_id)
    except service.NotFound:
        return 404, {"error": "user not found"}
    return 200, {"id": user.id, "name": user.name, "role": user.role, "active": user.active}
PY

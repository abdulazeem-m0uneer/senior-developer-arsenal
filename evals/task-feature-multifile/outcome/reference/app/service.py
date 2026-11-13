from datetime import datetime, timezone

from app import repo
from app.models import User


class NotFound(Exception):
    pass


class LastAdmin(Exception):
    pass


def create_user(user_id: int, name: str, role: str = "member") -> User:
    return repo.save(User(id=user_id, name=name, role=role))


def get_user(user_id: int) -> User:
    user = repo.get(user_id)
    if user is None:
        raise NotFound(user_id)
    return user


def _is_last_active_admin(user: User) -> bool:
    if user.role != "admin" or not user.active:
        return False
    return not any(other.role == "admin" and other.active and other.id != user.id for other in repo.all_users())


def deactivate_user(user_id: int) -> User:
    user = get_user(user_id)
    if _is_last_active_admin(user):
        raise LastAdmin(user_id)
    user.active = False
    user.deactivated_at = datetime.now(timezone.utc)
    return repo.save(user)

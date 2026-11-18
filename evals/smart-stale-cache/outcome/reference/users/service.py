from users import repo
from users.cache import display_name


def rename(user_id, new_name):
    new_name = new_name.strip()
    if not new_name:
        raise ValueError("name must not be empty")
    repo.set_name(user_id, new_name)
    display_name.cache_clear()  # shortcut: clears every user's entry; a per-key cache would evict one

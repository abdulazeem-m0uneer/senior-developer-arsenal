def build_create_payload(title, due_date=None):
    payload = {"title": title}
    if due_date is not None:
        payload["due_date"] = due_date
    return payload


def format_task(task):
    mark = "x" if task["done"] else " "
    due = f" (due {task['due_date']})" if task.get("due_date") else ""
    return f"[{mark}] {task['title']}{due}"

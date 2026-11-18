from datetime import date


def format_display_date(value: date) -> str:
    return f"{value.day} {value.strftime('%b %Y')}"


def due_label(task: dict) -> str:
    """Text shown under each task on the task screen."""
    return "Due " + format_display_date(task["due"])

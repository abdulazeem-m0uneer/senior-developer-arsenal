from app import service


def handle_get_user(user_id: int):
    try:
        user = service.get_user(user_id)
    except service.NotFound:
        return 404, {"error": "user not found"}
    return 200, {"id": user.id, "name": user.name, "role": user.role, "active": user.active}


def handle_deactivate_user(user_id: int):
    try:
        user = service.deactivate_user(user_id)
    except service.NotFound:
        return 404, {"error": "user not found"}
    except service.LastAdmin:
        return 409, {"error": "cannot deactivate the last active admin"}
    return 200, {"id": user.id, "active": user.active, "deactivated_at": user.deactivated_at.isoformat()}

import json
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import get_password_hash
from app.db.models import Role, User


logger = logging.getLogger(__name__)


def _load_demo_users_from_env() -> list[dict[str, str]]:
    settings = get_settings()
    if not settings.demo_users_json:
        return []

    try:
        users = json.loads(settings.demo_users_json)
    except json.JSONDecodeError:
        logger.warning("DEMO_USERS_JSON is not valid JSON; skipping seeding demo users")
        return []

    if not isinstance(users, list):
        logger.warning(
            "DEMO_USERS_JSON must be a JSON array; skipping seeding demo users"
        )
        return []

    normalized_users: list[dict[str, str]] = []
    for user in users:
        if not isinstance(user, dict):
            continue
        email = user.get("email")
        full_name = user.get("full_name")
        role = user.get("role")
        password = user.get("password")
        if not all([email, full_name, role, password]):
            continue
        try:
            role_enum = Role(role)
        except ValueError:
            logger.warning("Skipping demo user %s due to invalid role: %s", email, role)
            continue

        normalized_users.append(
            {
                "email": email,
                "full_name": full_name,
                "role": role_enum,
                "password": password,
            }
        )

    return normalized_users


def seed_default_users(db: Session) -> None:
    demo_users = _load_demo_users_from_env()
    if not demo_users:
        logger.info("No demo users configured; skipping seeding")
        return

    for payload in demo_users:
        existing_user = db.scalar(select(User).where(User.email == payload["email"]))
        if existing_user:
            continue
        db.add(
            User(
                email=payload["email"],
                full_name=payload["full_name"],
                role=payload["role"],
                hashed_password=get_password_hash(payload["password"]),
            )
        )
    db.commit()

from fastapi import Request, Depends, HTTPException
from sqlalchemy.orm import Session
from passlib.context import CryptContext

from .db import get_db
from . import models

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def get_current_user(request: Request, db: Session = Depends(get_db)) -> models.User | None:
    """Reads the logged-in user's id from the signed session cookie.
    Returns None if nobody is logged in — pages decide what to do with that."""
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.query(models.User).get(user_id)


def get_membership(db: Session, project_id: int, user_id: int) -> models.ProjectMembership | None:
    return (
        db.query(models.ProjectMembership)
        .filter_by(project_id=project_id, user_id=user_id)
        .first()
    )


def require_admin(db: Session, project_id: int, user: models.User) -> models.ProjectMembership:
    """Raises 403 unless the user is an Admin on this specific project."""
    membership = get_membership(db, project_id, user.id)
    if not membership or membership.role != models.Role.ADMIN:
        raise HTTPException(status_code=403, detail="Admins only for this action")
    return membership

import hmac

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, status
from sqlalchemy.exc import IntegrityError

from core.config import Settings, get_settings
from core.dependencies import get_user_repository
from core.exceptions import EmailTaken, NotFound, PermissionDenied
from core.security import hash_password
from models.user import User, UserRole
from repositories.user_repository import UserRepository
from schemas.admin_signup import AdminSignUp
from schemas.auth import MessageResponse
from services.auth_service import normalize_email

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register-admin",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_admin(
    body: AdminSignUp,
    users: UserRepository = Depends(get_user_repository),
    settings: Settings = Depends(get_settings),
) -> MessageResponse:
    expected = settings.admin_invite_code
    if not expected:
        raise NotFound()
    if not hmac.compare_digest(body.invite_code.encode(), expected.encode()):
        raise PermissionDenied("The invite code is not correct.")

    email = normalize_email(body.email)
    if users.get_by_email(email) is not None:
        raise EmailTaken()

    first_name, last_name = body.full_name.split(" ", 1)
    users.add(
        User(
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone=body.phone_number,
            password_hash=hash_password(body.password),
            user_role=UserRole.ADMIN,
            email_verified_at=datetime.now(timezone.utc),
        )
    )
    try:
        users.commit()
    except IntegrityError:
        users.rollback()
        raise EmailTaken() from None
    return MessageResponse(detail="Staff account created. Sign in to continue.")
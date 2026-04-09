"""
I keep all data-access logic here so my views stay small and focused on HTTP
orchestration and template rendering. All operations use the Django ORM
directly — no HTTP self-calls.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.contrib.auth import authenticate
from django.contrib.auth.models import User


@dataclass(frozen=True)
class ServiceResult:
    """
    I use this small result object so my views can handle success and failure
    consistently without duplicating parsing logic.
    """

    ok: bool
    status_code: int
    data: Any
    error_message: str = ""


def _get_user_from_token(access_token: str) -> User | None:
    """
    I decode a simplejwt access token and return the matching User, or None
    if the token is invalid or the user no longer exists.
    """
    from rest_framework_simplejwt.tokens import AccessToken
    try:
        token_obj = AccessToken(access_token)  # type: ignore[arg-type]
        return User.objects.get(id=token_obj["user_id"])
    except Exception:
        return None


class ContactApiService:
    """
    I use this service as the single data layer between my Django template
    frontend and the database. All operations use the ORM directly.
    """

    def __init__(self, base_url: str) -> None:
        # base_url is kept for interface compatibility but is not used for
        # self-HTTP calls any more.
        self.base_url: str = base_url.rstrip("/")

    def login(self, username: str, password: str) -> ServiceResult:
        """
        I authenticate the user and return JWT tokens on success.
        """
        from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

        user = authenticate(username=username, password=password)
        if user is None:
            return ServiceResult(
                ok=False,
                status_code=401,
                data={},
                error_message="Invalid username or password.",
            )

        access = AccessToken.for_user(user)
        refresh = RefreshToken.for_user(user)
        return ServiceResult(
            ok=True,
            status_code=200,
            data={"access": str(access), "refresh": str(refresh)},
        )

    def register(self, username: str, password: str) -> ServiceResult:
        """
        I create a new user account if the username is not already taken.
        """
        if User.objects.filter(username=username).exists():
            return ServiceResult(
                ok=False,
                status_code=400,
                data={},
                error_message="Username already exists.",
            )
        user: User = User.objects.create_user(username=username, password=password)
        return ServiceResult(
            ok=True,
            status_code=201,
            data={"id": user.pk, "username": user.username},
        )

    def list_contacts(self, access_token: str) -> ServiceResult:
        """
        I fetch all contacts that belong to the authenticated user.
        """
        from .models import Contact

        user = _get_user_from_token(access_token)
        if user is None:
            return ServiceResult(
                ok=False,
                status_code=401,
                data=[],
                error_message="Invalid or expired token.",
            )

        contacts = list(
            Contact.objects.filter(owner=user).values("id", "name", "email", "phone", "address")
        )
        return ServiceResult(ok=True, status_code=200, data=contacts)

    def create_contact(self, access_token: str, payload: dict[str, Any]) -> ServiceResult:
        """
        I create a new contact for the authenticated user.
        """
        from .models import Contact

        user = _get_user_from_token(access_token)
        if user is None:
            return ServiceResult(
                ok=False,
                status_code=401,
                data={},
                error_message="Invalid or expired token.",
            )

        try:
            contact = Contact.objects.create(
                owner=user,
                name=payload.get("name", ""),
                phone=payload.get("phone", ""),
                email=payload.get("email") or None,
                address=payload.get("address") or None,
            )
            data = {
                "id": contact.pk,
                "name": contact.name,
                "phone": contact.phone,
                "email": contact.email,
                "address": contact.address,
            }
            return ServiceResult(ok=True, status_code=201, data=data)
        except Exception as exc:
            return ServiceResult(
                ok=False, status_code=400, data={}, error_message=str(exc)
            )

    def update_contact(self, access_token: str, contact_id: int, payload: dict[str, Any]) -> ServiceResult:
        """
        I update an existing contact owned by the authenticated user.
        """
        from .models import Contact

        user = _get_user_from_token(access_token)
        if user is None:
            return ServiceResult(
                ok=False,
                status_code=401,
                data={},
                error_message="Invalid or expired token.",
            )

        try:
            contact = Contact.objects.get(owner=user, id=contact_id)
        except Contact.DoesNotExist:
            return ServiceResult(
                ok=False, status_code=404, data={}, error_message="Contact not found."
            )

        for field in ("name", "phone", "email", "address"):
            if field in payload:
                setattr(contact, field, payload[field] or None if field in ("email", "address") else payload[field])
        contact.save()

        data = {
            "id": contact.pk,
            "name": contact.name,
            "phone": contact.phone,
            "email": contact.email,
            "address": contact.address,
        }
        return ServiceResult(ok=True, status_code=200, data=data)

    def delete_contact(self, access_token: str, contact_id: int) -> ServiceResult:
        """
        I delete a contact owned by the authenticated user.
        """
        from .models import Contact

        user = _get_user_from_token(access_token)
        if user is None:
            return ServiceResult(
                ok=False,
                status_code=401,
                data={},
                error_message="Invalid or expired token.",
            )

        try:
            contact = Contact.objects.get(owner=user, id=contact_id)
        except Contact.DoesNotExist:
            return ServiceResult(
                ok=False, status_code=404, data={}, error_message="Contact not found."
            )

        contact.delete()
        return ServiceResult(ok=True, status_code=204, data={})


def build_contact_api_service() -> ContactApiService:
    """
    I create the service from settings so construction logic lives in one place.
    """
    from django.conf import settings

    return ContactApiService(base_url=settings.SITE_API_BASE_URL)

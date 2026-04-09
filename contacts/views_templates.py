"""
I keep my template-based frontend views here so they remain clearly separated
from my DRF API views.
"""

from __future__ import annotations

from typing import Any

from django.contrib import messages
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.views import View

from .forms import (
    ContactCreateUpdateForm,
    ContactSearchForm,
    LoginForm,
    RegisterForm,
)
from .selectors import apply_contact_filters, build_suggestions
from .services import build_contact_api_service

class JwtSessionMixin:
    """
    I centralize session token access and authentication checks for my template
    views to avoid repeating the same logic.
    """

    session_access_key: str = "jwt_access"

    def get_access_token(self, request: HttpRequest) -> str | None:
        """
        I read the access token from the current session.
        """
        return request.session.get(self.session_access_key)

    def require_login(self, request: HttpRequest) -> str | HttpResponse:
        """
        I either return a valid access token or redirect the visitor to the
        login page if the session is unauthenticated.
        """
        token: str | None = self.get_access_token(request)
        if not token:
            return redirect("contacts:login")
        return token


class LoginPageView(View):
    """
    I render and process the login page for JWT-based authentication.
    """

    template_name: str = "contacts/auth/login.html"

    def get(self, request: HttpRequest) -> HttpResponse:
        """
        I render an empty login form for a new visitor session.
        """
        return render(request, self.template_name, {"form": LoginForm()})

    def post(self, request: HttpRequest) -> HttpResponse:
        """
        I validate the login form, request JWT tokens from the API, and save the
        access token in the session for later authenticated page requests.
        """
        form: LoginForm = LoginForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Please fix the highlighted fields.")
            return render(request, self.template_name, {"form": form})

        service = build_contact_api_service()
        result = service.login(
            username=form.cleaned_data["username"],
            password=form.cleaned_data["password"],
        )

        if not result.ok:
            messages.error(request, result.error_message or "Login failed.")
            return render(request, self.template_name, {"form": form})

        request.session["jwt_access"] = result.data["access"]
        request.session["jwt_refresh"] = result.data.get("refresh", "")
        messages.success(request, "Welcome back. You are now signed in.")
        return redirect("contacts:dashboard")


class RegisterPageView(View):
    """
    I render and process the registration page for new users.
    """

    template_name: str = "contacts/auth/register.html"

    def get(self, request: HttpRequest) -> HttpResponse:
        """
        I render an empty registration form.
        """
        return render(request, self.template_name, {"form": RegisterForm()})

    def post(self, request: HttpRequest) -> HttpResponse:
        """
        I validate the registration form and create a new user through the API.
        """
        form: RegisterForm = RegisterForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Please fix the highlighted fields.")
            return render(request, self.template_name, {"form": form})

        service = build_contact_api_service()
        result = service.register(
            username=form.cleaned_data["username"],
            password=form.cleaned_data["password"],
        )

        if not result.ok:
            messages.error(request, result.error_message or "Could not create your account.")
            return render(request, self.template_name, {"form": form})

        messages.success(request, "Account created successfully. Please sign in.")
        return redirect("contacts:login")


class LogoutPageView(View):
    """
    I clear session tokens and sign the visitor out of the template frontend.
    """

    def post(self, request: HttpRequest) -> HttpResponse:
        """
        I remove JWT values from the session and redirect the visitor to login.
        """
        request.session.pop("jwt_access", None)
        request.session.pop("jwt_refresh", None)
        messages.success(request, "You have been logged out.")
        return redirect("contacts:login")


class ContactDashboardView(JwtSessionMixin, View):
    """
    I render the main contact dashboard with modern search and filter support.
    """

    template_name: str = "contacts/dashboard/list.html"

    def get(self, request: HttpRequest) -> HttpResponse:
        """
        I load contacts from the API, apply local frontend filters, and render
        the portfolio-style dashboard.
        """
        token_or_response = self.require_login(request)
        if isinstance(token_or_response, HttpResponse):
            return token_or_response

        service = build_contact_api_service()
        result = service.list_contacts(token_or_response)
        if not result.ok:
            messages.error(request, result.error_message or "Could not load contacts.")
            return render(
                request,
                self.template_name,
                {
                    "contacts": [],
                    "search_form": ContactSearchForm(request.GET or None),
                },
            )

        search_form: ContactSearchForm = ContactSearchForm(request.GET or None)
        filters: dict[str, str] = {}
        if search_form.is_valid():
            filters = {
                key: str(value)
                for key, value in search_form.cleaned_data.items()
                if value is not None
            }

        contacts: list[dict[str, Any]] = apply_contact_filters(result.data, filters)
        return render(
            request,
            self.template_name,
            {
                "contacts": contacts,
                "search_form": search_form,
                "contact_count": len(contacts),
            },
        )


class ContactCreateView(JwtSessionMixin, View):
    """
    I render and process the contact creation form.
    """

    template_name: str = "contacts/dashboard/create.html"

    def get(self, request: HttpRequest) -> HttpResponse:
        """
        I render an empty contact creation form.
        """
        return render(request, self.template_name, {"form": ContactCreateUpdateForm()})

    def post(self, request: HttpRequest) -> HttpResponse:
        """
        I validate the form and create the contact through the existing DRF API.
        """
        token_or_response = self.require_login(request)
        if isinstance(token_or_response, HttpResponse):
            return token_or_response

        form: ContactCreateUpdateForm = ContactCreateUpdateForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Please correct the form fields.")
            return render(request, self.template_name, {"form": form})

        service = build_contact_api_service()
        result = service.create_contact(token_or_response, form.cleaned_data)
        if not result.ok:
            messages.error(request, result.error_message or "Could not create contact.")
            return render(request, self.template_name, {"form": form})

        messages.success(request, "Contact created successfully.")
        return redirect("contacts:dashboard")


class ContactUpdateView(JwtSessionMixin, View):
    """
    I render and process the contact update form.
    """

    template_name: str = "contacts/dashboard/update.html"

    def get_contact_by_id(self, contacts: list[dict[str, Any]], contact_id: int) -> dict[str, Any] | None:
        """
        I find a specific contact from the API response so I can prefill the
        update form without introducing a new model or repository layer.
        """
        for contact in contacts:
            if int(contact.get("id", 0)) == int(contact_id):
                return contact
        return None

    def get(self, request: HttpRequest, contact_id: int) -> HttpResponse:
        """
        I fetch contacts, locate the selected contact, and prefill the update
        form with existing values.
        """
        token_or_response = self.require_login(request)
        if isinstance(token_or_response, HttpResponse):
            return token_or_response

        service = build_contact_api_service()
        result = service.list_contacts(token_or_response)
        if not result.ok:
            messages.error(request, "Could not load the selected contact.")
            return redirect("contacts:dashboard")

        contact = self.get_contact_by_id(result.data, contact_id)
        if not contact:
            messages.error(request, "Contact not found.")
            return redirect("contacts:dashboard")

        form = ContactCreateUpdateForm(initial=contact)
        return render(request, self.template_name, {"form": form, "contact": contact})

    def post(self, request: HttpRequest, contact_id: int) -> HttpResponse:
        """
        I validate the form and update the selected contact through the API.
        """
        token_or_response = self.require_login(request)
        if isinstance(token_or_response, HttpResponse):
            return token_or_response

        form: ContactCreateUpdateForm = ContactCreateUpdateForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Please correct the form fields.")
            return render(request, self.template_name, {"form": form, "contact": {"id": contact_id}})

        service = build_contact_api_service()
        result = service.update_contact(token_or_response, contact_id, form.cleaned_data)
        if not result.ok:
            messages.error(request, result.error_message or "Could not update contact.")
            return render(request, self.template_name, {"form": form, "contact": {"id": contact_id}})

        messages.success(request, "Contact updated successfully.")
        return redirect("contacts:dashboard")


class ContactDeleteView(JwtSessionMixin, View):
    """
    I render a confirmation screen and delete the selected contact when the
    visitor confirms the action.
    """

    template_name: str = "contacts/dashboard/delete.html"

    def get(self, request: HttpRequest, contact_id: int) -> HttpResponse:
        """
        I render a simple confirmation page before deleting a contact.
        """
        return render(request, self.template_name, {"contact_id": contact_id})

    def post(self, request: HttpRequest, contact_id: int) -> HttpResponse:
        """
        I delete the contact through the API and redirect back to the dashboard.
        """
        token_or_response = self.require_login(request)
        if isinstance(token_or_response, HttpResponse):
            return token_or_response

        service = build_contact_api_service()
        result = service.delete_contact(token_or_response, contact_id)
        if not result.ok:
            messages.error(request, result.error_message or "Could not delete contact.")
            return redirect("contacts:dashboard")

        messages.success(request, "Contact deleted successfully.")
        return redirect("contacts:dashboard")


class LiveSearchSuggestionView(JwtSessionMixin, View):
    """
    I return contact suggestions as JSON so the search box can feel fast and
    recruiter-friendly while typing.
    """

    def get(self, request: HttpRequest) -> JsonResponse:
        """
        I fetch contacts, generate suggestions, and return them to the browser.
        """
        token_or_response = self.require_login(request)
        if isinstance(token_or_response, HttpResponse):
            return JsonResponse({"suggestions": []}, status=401)

        query: str = request.GET.get("q", "").strip()
        service = build_contact_api_service()
        result = service.list_contacts(token_or_response)

        if not result.ok:
            return JsonResponse({"suggestions": []}, status=400)

        suggestions: list[str] = build_suggestions(result.data, query)
        return JsonResponse({"suggestions": suggestions})
"""
I keep all HTML form validation here so my templates stay simple and my views
do not become bloated with validation logic.
"""

from __future__ import annotations

from typing import Any

from django import forms


class LoginForm(forms.Form):
    """
    I use this form to validate the login credentials entered by a visitor
    before I send them to my JWT login endpoint.
    """

    username: forms.CharField = forms.CharField(
        max_length=150,
        widget=forms.TextInput(
            attrs={
                "class": "input",
                "placeholder": "Enter your username",
                "autocomplete": "username",
            }
        ),
    )
    password: forms.CharField = forms.CharField(
        widget=forms.PasswordInput(
            attrs={
                "class": "input",
                "placeholder": "Enter your password",
                "autocomplete": "current-password",
            }
        )
    )


class RegisterForm(forms.Form):
    """
    I use this form to validate registration data before I send it to my
    backend registration endpoint.
    """

    username: forms.CharField = forms.CharField(
        max_length=150,
        widget=forms.TextInput(
            attrs={
                "class": "input",
                "placeholder": "Choose a username",
                "autocomplete": "username",
            }
        ),
    )
    password: forms.CharField = forms.CharField(
        min_length=8,
        widget=forms.PasswordInput(
            attrs={
                "class": "input",
                "placeholder": "Create a password",
                "autocomplete": "new-password",
            }
        ),
    )
    confirm_password: forms.CharField = forms.CharField(
        min_length=8,
        widget=forms.PasswordInput(
            attrs={
                "class": "input",
                "placeholder": "Confirm your password",
                "autocomplete": "new-password",
            }
        ),
    )

    def clean(self) -> dict[str, Any]:
        """
        I validate that both password fields match so I can stop invalid data
        before it reaches my API layer.
        """
        cleaned_data: dict[str, Any] = super().clean()
        password: str | None = cleaned_data.get("password")
        confirm_password: str | None = cleaned_data.get("confirm_password")

        if password and confirm_password and password != confirm_password:
            raise forms.ValidationError("Passwords do not match.")

        return cleaned_data


class ContactSearchForm(forms.Form):
    """
    I use this form to validate query string based filtering on the contact
    listing page.
    """

    q: forms.CharField = forms.CharField(required=False)
    email: forms.CharField = forms.CharField(required=False)
    address: forms.CharField = forms.CharField(required=False)
    ordering: forms.ChoiceField = forms.ChoiceField(
        required=False,
        choices=(
            ("name", "Name A-Z"),
            ("-name", "Name Z-A"),
            ("phone", "Phone A-Z"),
            ("-phone", "Phone Z-A"),
        ),
    )


class ContactCreateUpdateForm(forms.Form):
    """
    I use the same form for creating and updating contacts because both actions
    validate the same fields and this keeps my code DRY.
    """

    name: forms.CharField = forms.CharField(
        max_length=100,
        widget=forms.TextInput(
            attrs={
                "class": "input",
                "placeholder": "Full name",
            }
        ),
    )
    phone: forms.CharField = forms.CharField(
        max_length=20,
        widget=forms.TextInput(
            attrs={
                "class": "input",
                "placeholder": "Phone number",
            }
        ),
    )
    email: forms.EmailField = forms.EmailField(
        required=False,
        widget=forms.EmailInput(
            attrs={
                "class": "input",
                "placeholder": "Email address",
            }
        ),
    )
    address: forms.CharField = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "input textarea",
                "placeholder": "Address",
                "rows": 4,
            }
        ),
    )




    


class ContactForm(forms.Form):
    """
    This form represents the Contact input layer.
    I use it to validate user input before sending data to my API layer.
    """

    name = forms.CharField(max_length=100)
    phone = forms.CharField(max_length=20)
    email = forms.EmailField(required=False)
    address = forms.CharField(widget=forms.Textarea, required=False)

    def clean_phone(self):
        """
        I validate that phone contains only digits or '+'.
        This ensures consistent formatting before reaching backend.
        """
        phone = self.cleaned_data.get("phone")

        if not phone.replace("+", "").isdigit():
            raise forms.ValidationError("Invalid phone format")

        return phone
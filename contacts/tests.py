"""
Comprehensive test suite for the contacts application.

Covers: model, services, selectors, serializers, forms,
REST API views, template views, and JWT utilities.
"""
from __future__ import annotations

import json

from django.test import TestCase, override_settings
from django.contrib.auth.models import User
from django.urls import reverse

from rest_framework.test import APIClient, APIRequestFactory, force_authenticate
from rest_framework_simplejwt.tokens import AccessToken

from contacts.models import Contact
from contacts.services import ContactApiService, get_user_from_token
from contacts.selectors import apply_contact_filters, build_suggestions
from contacts.serializers import (
    CreateContactSerializer,
    ContactSerializer,
    UpdateContactSerializer,
    RegisterSerializer,
)
from contacts.forms import (
    LoginForm,
    RegisterForm,
    ContactSearchForm,
    ContactCreateUpdateForm,
    ContactForm,
)
from contacts.views import ContactView


# ─────────────────────────────────────────────────────────────────────────────
# Test helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_user(username: str = "testuser", password: str = "testpass123") -> User:
    return User.objects.create_user(username=username, password=password)


def _jwt_for(user: User) -> str:
    return str(AccessToken.for_user(user))


def _make_contact(user: User, **kwargs) -> Contact:
    defaults = {"name": "John Doe", "phone": "1234567890"}
    defaults.update(kwargs)
    return Contact.objects.create(owner=user, **defaults)


def _set_session_jwt(client, user: User) -> str:
    token = _jwt_for(user)
    session = client.session
    session["jwt_access"] = token
    session.save()
    return token


# ─────────────────────────────────────────────────────────────────────────────
# Model
# ─────────────────────────────────────────────────────────────────────────────

class ContactModelTest(TestCase):
    def setUp(self):
        self.user = _make_user()

    def test_str_returns_name(self):
        c = _make_contact(self.user, name="Alice")
        self.assertEqual(str(c), "Alice")

    def test_create_minimal_contact(self):
        c = _make_contact(self.user)
        self.assertEqual(c.owner, self.user)
        self.assertIsNone(c.email)
        self.assertIsNone(c.address)

    def test_create_full_contact(self):
        c = _make_contact(
            self.user, name="Bob", phone="555-0001",
            email="bob@example.com", address="123 Main St",
        )
        self.assertEqual(c.email, "bob@example.com")
        self.assertEqual(c.address, "123 Main St")

    def test_cascade_delete_on_user_delete(self):
        _make_contact(self.user)
        self.assertEqual(Contact.objects.count(), 1)
        self.user.delete()
        self.assertEqual(Contact.objects.count(), 0)

    def test_owner_isolation(self):
        user2 = _make_user(username="other")
        _make_contact(self.user)
        _make_contact(user2, name="Other")
        self.assertEqual(Contact.objects.filter(owner=self.user).count(), 1)
        self.assertEqual(Contact.objects.filter(owner=user2).count(), 1)


# ─────────────────────────────────────────────────────────────────────────────
# Services
# ─────────────────────────────────────────────────────────────────────────────

class ContactApiServiceTest(TestCase):
    def setUp(self):
        self.service = ContactApiService(base_url="http://localhost:8000")
        self.user = _make_user()

    # login
    def test_login_success(self):
        r = self.service.login("testuser", "testpass123")
        self.assertTrue(r.ok)
        self.assertEqual(r.status_code, 200)
        self.assertIn("access", r.data)
        self.assertIn("refresh", r.data)

    def test_login_wrong_password(self):
        r = self.service.login("testuser", "wrongpass")
        self.assertFalse(r.ok)
        self.assertEqual(r.status_code, 401)

    def test_login_unknown_user(self):
        r = self.service.login("nobody", "pass")
        self.assertFalse(r.ok)
        self.assertEqual(r.status_code, 401)

    # register
    def test_register_success(self):
        r = self.service.register("newuser", "securepass123")
        self.assertTrue(r.ok)
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data["username"], "newuser")
        self.assertTrue(User.objects.filter(username="newuser").exists())

    def test_register_duplicate_username(self):
        r = self.service.register("testuser", "password123")
        self.assertFalse(r.ok)
        self.assertEqual(r.status_code, 400)
        self.assertIn("already exists", r.error_message)

    # list contacts
    def test_list_contacts_empty(self):
        r = self.service.list_contacts(self.user)
        self.assertTrue(r.ok)
        self.assertEqual(r.data, [])

    def test_list_contacts_returns_only_own(self):
        _make_contact(self.user, name="Alice")
        _make_contact(self.user, name="Bob")
        user2 = _make_user(username="other")
        _make_contact(user2, name="Charlie")
        r = self.service.list_contacts(self.user)
        self.assertTrue(r.ok)
        self.assertEqual(len(r.data), 2)
        names = [c["name"] for c in r.data]
        self.assertIn("Alice", names)
        self.assertNotIn("Charlie", names)

    # create contact
    def test_create_contact_success(self):
        r = self.service.create_contact(self.user, {"name": "Alice", "phone": "555"})
        self.assertTrue(r.ok)
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data["name"], "Alice")
        self.assertTrue(Contact.objects.filter(owner=self.user, name="Alice").exists())

    def test_create_contact_with_optional_fields(self):
        r = self.service.create_contact(self.user, {
            "name": "Bob", "phone": "556",
            "email": "bob@test.com", "address": "123 St",
        })
        self.assertTrue(r.ok)
        self.assertEqual(r.data["email"], "bob@test.com")
        self.assertEqual(r.data["address"], "123 St")

    def test_create_contact_empty_email_stored_as_none(self):
        r = self.service.create_contact(self.user, {"name": "Carol", "phone": "557", "email": ""})
        self.assertTrue(r.ok)
        self.assertIsNone(r.data["email"])

    # update contact
    def test_update_contact_success(self):
        c = _make_contact(self.user, name="Old")
        r = self.service.update_contact(self.user, c.pk, {"name": "New"})
        self.assertTrue(r.ok)
        self.assertEqual(r.data["name"], "New")
        c.refresh_from_db()
        self.assertEqual(c.name, "New")

    def test_update_contact_multiple_fields(self):
        c = _make_contact(self.user)
        r = self.service.update_contact(self.user, c.pk, {
            "name": "Updated", "phone": "999",
            "email": "new@test.com", "address": "Addr",
        })
        self.assertTrue(r.ok)
        self.assertEqual(r.data["phone"], "999")
        self.assertEqual(r.data["email"], "new@test.com")

    def test_update_contact_not_found(self):
        r = self.service.update_contact(self.user, 99999, {"name": "X"})
        self.assertFalse(r.ok)
        self.assertEqual(r.status_code, 404)

    def test_update_contact_wrong_owner(self):
        user2 = _make_user(username="other")
        c = _make_contact(user2)
        r = self.service.update_contact(self.user, c.pk, {"name": "Hacked"})
        self.assertFalse(r.ok)
        self.assertEqual(r.status_code, 404)

    # delete contact
    def test_delete_contact_success(self):
        c = _make_contact(self.user)
        r = self.service.delete_contact(self.user, c.pk)
        self.assertTrue(r.ok)
        self.assertEqual(r.status_code, 204)
        self.assertFalse(Contact.objects.filter(pk=c.pk).exists())

    def test_delete_contact_not_found(self):
        r = self.service.delete_contact(self.user, 99999)
        self.assertFalse(r.ok)
        self.assertEqual(r.status_code, 404)

    def test_delete_contact_wrong_owner(self):
        user2 = _make_user(username="other")
        c = _make_contact(user2)
        r = self.service.delete_contact(self.user, c.pk)
        self.assertFalse(r.ok)
        self.assertEqual(r.status_code, 404)


class GetUserFromTokenTest(TestCase):
    def setUp(self):
        self.user = _make_user()

    def test_valid_token_returns_user(self):
        result = get_user_from_token(_jwt_for(self.user))
        self.assertIsNotNone(result)
        self.assertEqual(result.pk, self.user.pk)

    def test_invalid_token_returns_none(self):
        self.assertIsNone(get_user_from_token("not-a-valid-token"))

    def test_empty_token_returns_none(self):
        self.assertIsNone(get_user_from_token(""))

    def test_token_for_deleted_user_returns_none(self):
        token = _jwt_for(self.user)
        self.user.delete()
        self.assertIsNone(get_user_from_token(token))


# ─────────────────────────────────────────────────────────────────────────────
# Selectors
# ─────────────────────────────────────────────────────────────────────────────

class ApplyContactFiltersTest(TestCase):
    def setUp(self):
        self.user = _make_user()
        self.user2 = _make_user(username="other")
        _make_contact(self.user, name="Alice Smith", phone="1111", email="alice@test.com", address="New York")
        _make_contact(self.user, name="Bob Jones", phone="2222", email="bob@test.com", address="Los Angeles")
        _make_contact(self.user2, name="Charlie", phone="3333")

    def test_no_filters_returns_all_own(self):
        self.assertEqual(len(apply_contact_filters({}, self.user)), 2)

    def test_q_filter_by_name(self):
        result = apply_contact_filters({"q": "Alice"}, self.user)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "Alice Smith")

    def test_q_filter_by_phone(self):
        result = apply_contact_filters({"q": "2222"}, self.user)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "Bob Jones")

    def test_q_filter_case_insensitive(self):
        self.assertEqual(len(apply_contact_filters({"q": "alice"}, self.user)), 1)

    def test_email_filter(self):
        result = apply_contact_filters({"email": "alice"}, self.user)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "Alice Smith")

    def test_address_filter(self):
        result = apply_contact_filters({"address": "angeles"}, self.user)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "Bob Jones")

    def test_user_isolation(self):
        result = apply_contact_filters({}, self.user2)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "Charlie")

    def test_no_match_returns_empty(self):
        self.assertEqual(apply_contact_filters({"q": "zzz_nomatch"}, self.user), [])

    def test_ordering_name_asc(self):
        result = apply_contact_filters({"ordering": "name"}, self.user)
        names = [r["name"] for r in result]
        self.assertEqual(names, sorted(names))

    def test_ordering_name_desc(self):
        result = apply_contact_filters({"ordering": "-name"}, self.user)
        names = [r["name"] for r in result]
        self.assertEqual(names, sorted(names, reverse=True))

    def test_empty_string_filters_ignored(self):
        result = apply_contact_filters({"q": "", "email": "", "address": ""}, self.user)
        self.assertEqual(len(result), 2)


class BuildSuggestionsTest(TestCase):
    def setUp(self):
        self.contacts = [
            {"name": "Alice Smith", "phone": "1111", "email": "alice@test.com"},
            {"name": "Bob Jones",   "phone": "2222", "email": "bob@test.com"},
            {"name": "Alice Brown", "phone": "3333", "email": "abrown@test.com"},
        ]

    def test_empty_query_returns_empty(self):
        self.assertEqual(build_suggestions(self.contacts, ""), [])

    def test_whitespace_query_returns_empty(self):
        self.assertEqual(build_suggestions(self.contacts, "   "), [])

    def test_name_match(self):
        result = build_suggestions(self.contacts, "Alice")
        self.assertIn("Alice Smith", result)
        self.assertIn("Alice Brown", result)

    def test_phone_match(self):
        result = build_suggestions(self.contacts, "2222")
        self.assertIn("2222", result)

    def test_email_match(self):
        result = build_suggestions(self.contacts, "alice@")
        self.assertIn("alice@test.com", result)

    def test_limit_respected(self):
        many = [{"name": f"alice {i}", "phone": f"{i:010}", "email": f"x{i}@t.com"} for i in range(20)]
        self.assertLessEqual(len(build_suggestions(many, "alice", limit=3)), 3)

    def test_no_duplicates(self):
        result = build_suggestions(self.contacts, "alice")
        lower = [r.lower() for r in result]
        self.assertEqual(len(lower), len(set(lower)))

    def test_case_insensitive(self):
        result = build_suggestions(self.contacts, "ALICE")
        self.assertGreater(len(result), 0)


# ─────────────────────────────────────────────────────────────────────────────
# Serializers
# ─────────────────────────────────────────────────────────────────────────────

class CreateContactSerializerTest(TestCase):
    def setUp(self):
        self.user = _make_user()
        self.factory = APIRequestFactory()

    def _request(self):
        req = self.factory.post("/contacts/")
        req.user = self.user
        return req

    def test_valid_data(self):
        s = CreateContactSerializer(data={"name": "Alice", "phone": "555"}, context={"request": self._request()})
        self.assertTrue(s.is_valid(), s.errors)

    def test_missing_name_fails(self):
        s = CreateContactSerializer(data={"phone": "555"}, context={"request": self._request()})
        self.assertFalse(s.is_valid())
        self.assertIn("name", s.errors)

    def test_missing_phone_fails(self):
        s = CreateContactSerializer(data={"name": "Alice"}, context={"request": self._request()})
        self.assertFalse(s.is_valid())
        self.assertIn("phone", s.errors)

    def test_save_sets_owner(self):
        s = CreateContactSerializer(data={"name": "Alice", "phone": "555"}, context={"request": self._request()})
        self.assertTrue(s.is_valid())
        c = s.save()
        self.assertEqual(c.owner, self.user)


class ContactSerializerTest(TestCase):
    def test_all_fields_present(self):
        user = _make_user()
        c = _make_contact(user, email="e@e.com", address="Addr")
        data = ContactSerializer(c).data
        for field in ("id", "owner", "name", "phone", "email", "address"):
            self.assertIn(field, data)
        self.assertEqual(data["email"], "e@e.com")


class UpdateContactSerializerTest(TestCase):
    def test_partial_update(self):
        user = _make_user()
        c = _make_contact(user)
        s = UpdateContactSerializer(c, data={"name": "New Name"}, partial=True)
        self.assertTrue(s.is_valid(), s.errors)
        updated = s.save()
        self.assertEqual(updated.name, "New Name")

    def test_fields_are_name_phone_email_address(self):
        self.assertEqual(set(UpdateContactSerializer().fields.keys()), {"name", "phone", "email", "address"})


class RegisterSerializerTest(TestCase):
    def test_creates_user_with_hashed_password(self):
        s = RegisterSerializer(data={"username": "newuser", "password": "securepass123"})
        self.assertTrue(s.is_valid(), s.errors)
        user = s.save()
        self.assertTrue(User.objects.filter(username="newuser").exists())
        self.assertTrue(user.check_password("securepass123"))

    def test_password_is_write_only(self):
        s = RegisterSerializer(data={"username": "u", "password": "pass12345"})
        self.assertTrue(s.is_valid())
        self.assertNotIn("password", s.data)


# ─────────────────────────────────────────────────────────────────────────────
# Forms
# ─────────────────────────────────────────────────────────────────────────────

class LoginFormTest(TestCase):
    def test_valid(self):
        self.assertTrue(LoginForm(data={"username": "u", "password": "p"}).is_valid())

    def test_missing_username(self):
        f = LoginForm(data={"password": "p"})
        self.assertFalse(f.is_valid())
        self.assertIn("username", f.errors)

    def test_missing_password(self):
        f = LoginForm(data={"username": "u"})
        self.assertFalse(f.is_valid())
        self.assertIn("password", f.errors)

    def test_empty_form(self):
        self.assertFalse(LoginForm(data={}).is_valid())


class RegisterFormTest(TestCase):
    def _data(self, **kw):
        base = {"username": "newuser", "password": "securepass", "confirm_password": "securepass"}
        base.update(kw)
        return base

    def test_valid(self):
        self.assertTrue(RegisterForm(data=self._data()).is_valid())

    def test_password_mismatch(self):
        self.assertFalse(RegisterForm(data=self._data(confirm_password="other")).is_valid())

    def test_short_password(self):
        self.assertFalse(RegisterForm(data=self._data(password="short", confirm_password="short")).is_valid())

    def test_missing_username(self):
        d = self._data()
        del d["username"]
        self.assertFalse(RegisterForm(data=d).is_valid())


class ContactSearchFormTest(TestCase):
    def test_all_optional(self):
        self.assertTrue(ContactSearchForm(data={}).is_valid())

    def test_valid_ordering_choices(self):
        for o in ("name", "-name", "phone", "-phone"):
            self.assertTrue(ContactSearchForm(data={"ordering": o}).is_valid())

    def test_invalid_ordering(self):
        self.assertFalse(ContactSearchForm(data={"ordering": "invalid"}).is_valid())


class ContactCreateUpdateFormTest(TestCase):
    def test_valid_required_only(self):
        self.assertTrue(ContactCreateUpdateForm(data={"name": "Alice", "phone": "555"}).is_valid())

    def test_valid_all_fields(self):
        f = ContactCreateUpdateForm(data={"name": "Alice", "phone": "555", "email": "a@a.com", "address": "Addr"})
        self.assertTrue(f.is_valid())

    def test_missing_name(self):
        self.assertFalse(ContactCreateUpdateForm(data={"phone": "555"}).is_valid())

    def test_missing_phone(self):
        self.assertFalse(ContactCreateUpdateForm(data={"name": "Alice"}).is_valid())

    def test_invalid_email(self):
        f = ContactCreateUpdateForm(data={"name": "Alice", "phone": "555", "email": "not-email"})
        self.assertFalse(f.is_valid())
        self.assertIn("email", f.errors)


class ContactFormTest(TestCase):
    def test_valid_digits(self):
        self.assertTrue(ContactForm(data={"name": "Alice", "phone": "1234567890"}).is_valid())

    def test_valid_with_plus(self):
        self.assertTrue(ContactForm(data={"name": "Alice", "phone": "+447911123456"}).is_valid())

    def test_invalid_with_letters(self):
        f = ContactForm(data={"name": "Alice", "phone": "123abc456"})
        self.assertFalse(f.is_valid())
        self.assertIn("phone", f.errors)

    def test_invalid_with_dashes(self):
        self.assertFalse(ContactForm(data={"name": "Alice", "phone": "123-456-7890"}).is_valid())


# ─────────────────────────────────────────────────────────────────────────────
# REST API Views
# ─────────────────────────────────────────────────────────────────────────────

class ContactViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = _make_user()
        self.token = _jwt_for(self.user)

    def _auth(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token}")

    # GET
    def test_get_requires_auth(self):
        self.assertEqual(self.client.get("/contacts/").status_code, 401)

    def test_get_returns_own_contacts(self):
        self._auth()
        _make_contact(self.user, name="Alice")
        user2 = _make_user(username="other")
        _make_contact(user2, name="Charlie")
        response = self.client.get("/contacts/")
        self.assertEqual(response.status_code, 200)
        names = [c["name"] for c in response.data]
        self.assertIn("Alice", names)
        self.assertNotIn("Charlie", names)

    def test_get_empty_list(self):
        self._auth()
        response = self.client.get("/contacts/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [])

    # POST
    def test_post_requires_auth(self):
        resp = self.client.post("/contacts/", {"name": "A", "phone": "1"}, format="json")
        self.assertEqual(resp.status_code, 401)

    def test_post_creates_contact(self):
        self._auth()
        resp = self.client.post("/contacts/", {"name": "Alice", "phone": "555"}, format="json")
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(Contact.objects.filter(owner=self.user, name="Alice").exists())

    def test_post_missing_phone_returns_400(self):
        self._auth()
        resp = self.client.post("/contacts/", {"name": "Alice"}, format="json")
        self.assertEqual(resp.status_code, 400)

    # PUT (via RequestFactory — URL pattern for <id> is not defined)
    def test_put_updates_contact(self):
        c = _make_contact(self.user, name="Old")
        factory = APIRequestFactory()
        req = factory.put("/", {"name": "New"}, format="json")
        force_authenticate(req, user=self.user)
        resp = ContactView.as_view()(req, id=c.pk)
        self.assertEqual(resp.status_code, 200)
        c.refresh_from_db()
        self.assertEqual(c.name, "New")

    def test_put_wrong_owner_returns_404(self):
        user2 = _make_user(username="other")
        c = _make_contact(user2)
        factory = APIRequestFactory()
        req = factory.put("/", {"name": "Hacked"}, format="json")
        force_authenticate(req, user=self.user)
        self.assertEqual(ContactView.as_view()(req, id=c.pk).status_code, 404)

    def test_put_nonexistent_returns_404(self):
        factory = APIRequestFactory()
        req = factory.put("/", {"name": "X"}, format="json")
        force_authenticate(req, user=self.user)
        self.assertEqual(ContactView.as_view()(req, id=99999).status_code, 404)

    # DELETE (via RequestFactory)
    def test_delete_contact(self):
        c = _make_contact(self.user)
        factory = APIRequestFactory()
        req = factory.delete("/")
        force_authenticate(req, user=self.user)
        resp = ContactView.as_view()(req, id=c.pk)
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(Contact.objects.filter(pk=c.pk).exists())

    def test_delete_wrong_owner_returns_404(self):
        user2 = _make_user(username="other")
        c = _make_contact(user2)
        factory = APIRequestFactory()
        req = factory.delete("/")
        force_authenticate(req, user=self.user)
        self.assertEqual(ContactView.as_view()(req, id=c.pk).status_code, 404)

    def test_delete_nonexistent_returns_404(self):
        factory = APIRequestFactory()
        req = factory.delete("/")
        force_authenticate(req, user=self.user)
        self.assertEqual(ContactView.as_view()(req, id=99999).status_code, 404)


class RegisterViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_register_creates_user(self):
        resp = self.client.post("/api/register/", {"username": "newuser", "password": "securepass123"}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(User.objects.filter(username="newuser").exists())

    def test_register_duplicate_returns_400(self):
        _make_user(username="existing")
        resp = self.client.post("/api/register/", {"username": "existing", "password": "pass"}, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_register_missing_password(self):
        resp = self.client.post("/api/register/", {"username": "newuser"}, format="json")
        self.assertEqual(resp.status_code, 400)


class JWTLoginTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        _make_user()

    def test_login_returns_tokens(self):
        resp = self.client.post("/api/login/", {"username": "testuser", "password": "testpass123"}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("access", resp.data)
        self.assertIn("refresh", resp.data)

    def test_login_wrong_credentials(self):
        resp = self.client.post("/api/login/", {"username": "testuser", "password": "wrong"}, format="json")
        self.assertEqual(resp.status_code, 401)

    def test_token_refresh(self):
        login = self.client.post("/api/login/", {"username": "testuser", "password": "testpass123"}, format="json")
        resp = self.client.post("/api/token/refresh/", {"refresh": login.data["refresh"]}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("access", resp.data)


# ─────────────────────────────────────────────────────────────────────────────
# Template views
# ─────────────────────────────────────────────────────────────────────────────

@override_settings(STATICFILES_STORAGE="django.contrib.staticfiles.storage.StaticFilesStorage")
class LoginPageViewTest(TestCase):
    def test_get_renders_form(self):
        resp = self.client.get("/login/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "form")

    def test_post_valid_redirects_to_dashboard(self):
        _make_user()
        resp = self.client.post("/login/", {"username": "testuser", "password": "testpass123"})
        self.assertRedirects(resp, "/", fetch_redirect_response=False)

    def test_post_invalid_stays_on_page(self):
        _make_user()
        resp = self.client.post("/login/", {"username": "testuser", "password": "wrong"})
        self.assertEqual(resp.status_code, 200)

    def test_post_invalid_form_stays_on_page(self):
        resp = self.client.post("/login/", {})
        self.assertEqual(resp.status_code, 200)


@override_settings(STATICFILES_STORAGE="django.contrib.staticfiles.storage.StaticFilesStorage")
class RegisterPageViewTest(TestCase):
    def test_get_renders_form(self):
        resp = self.client.get("/register/")
        self.assertEqual(resp.status_code, 200)

    def test_post_valid_redirects_to_login(self):
        resp = self.client.post("/register/", {
            "username": "brand_new", "password": "securepass", "confirm_password": "securepass",
        })
        self.assertRedirects(resp, "/login/", fetch_redirect_response=False)
        self.assertTrue(User.objects.filter(username="brand_new").exists())

    def test_post_duplicate_stays_on_page(self):
        _make_user(username="existing")
        resp = self.client.post("/register/", {
            "username": "existing", "password": "securepass", "confirm_password": "securepass",
        })
        self.assertEqual(resp.status_code, 200)

    def test_post_password_mismatch_stays_on_page(self):
        resp = self.client.post("/register/", {
            "username": "newuser", "password": "pass1234", "confirm_password": "pass5678",
        })
        self.assertEqual(resp.status_code, 200)


@override_settings(STATICFILES_STORAGE="django.contrib.staticfiles.storage.StaticFilesStorage")
class LogoutPageViewTest(TestCase):
    def test_post_clears_session_and_redirects(self):
        user = _make_user()
        _set_session_jwt(self.client, user)
        resp = self.client.post("/logout/")
        self.assertRedirects(resp, "/login/", fetch_redirect_response=False)
        self.assertNotIn("jwt_access", self.client.session)


@override_settings(STATICFILES_STORAGE="django.contrib.staticfiles.storage.StaticFilesStorage")
class ContactDashboardViewTest(TestCase):
    def test_get_unauthenticated_redirects(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 302)

    def test_get_authenticated_shows_dashboard(self):
        user = _make_user()
        _make_contact(user, name="Alice")
        _set_session_jwt(self.client, user)
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)

    def test_get_with_search_filter(self):
        user = _make_user()
        _make_contact(user, name="Alice")
        _set_session_jwt(self.client, user)
        resp = self.client.get("/?q=Alice")
        self.assertEqual(resp.status_code, 200)


@override_settings(STATICFILES_STORAGE="django.contrib.staticfiles.storage.StaticFilesStorage")
class ContactCreateViewTest(TestCase):
    def test_get_renders_form(self):
        resp = self.client.get("/create/")
        self.assertEqual(resp.status_code, 200)

    def test_post_unauthenticated_redirects(self):
        resp = self.client.post("/create/", {"name": "Alice", "phone": "555"})
        self.assertEqual(resp.status_code, 302)

    def test_post_authenticated_creates_contact(self):
        user = _make_user()
        _set_session_jwt(self.client, user)
        resp = self.client.post("/create/", {"name": "Alice", "phone": "555"})
        self.assertRedirects(resp, "/", fetch_redirect_response=False)
        self.assertTrue(Contact.objects.filter(owner=user, name="Alice").exists())

    def test_post_invalid_form_stays_on_page(self):
        user = _make_user()
        _set_session_jwt(self.client, user)
        resp = self.client.post("/create/", {"name": ""})
        self.assertEqual(resp.status_code, 200)


@override_settings(STATICFILES_STORAGE="django.contrib.staticfiles.storage.StaticFilesStorage")
class ContactUpdateViewTest(TestCase):
    def test_get_unauthenticated_redirects(self):
        user = _make_user()
        c = _make_contact(user)
        resp = self.client.get(f"/{c.pk}/edit/")
        self.assertEqual(resp.status_code, 302)

    def test_get_authenticated_renders_form(self):
        user = _make_user()
        c = _make_contact(user, name="Old Name")
        _set_session_jwt(self.client, user)
        resp = self.client.get(f"/{c.pk}/edit/")
        self.assertEqual(resp.status_code, 200)

    def test_get_nonexistent_redirects_to_dashboard(self):
        user = _make_user()
        _set_session_jwt(self.client, user)
        resp = self.client.get("/99999/edit/")
        self.assertRedirects(resp, "/", fetch_redirect_response=False)

    def test_post_authenticated_updates_contact(self):
        user = _make_user()
        c = _make_contact(user, name="Old")
        _set_session_jwt(self.client, user)
        resp = self.client.post(f"/{c.pk}/edit/", {"name": "New", "phone": "999"})
        self.assertRedirects(resp, "/", fetch_redirect_response=False)
        c.refresh_from_db()
        self.assertEqual(c.name, "New")

    def test_post_invalid_form_stays_on_page(self):
        user = _make_user()
        c = _make_contact(user)
        _set_session_jwt(self.client, user)
        resp = self.client.post(f"/{c.pk}/edit/", {"name": ""})
        self.assertEqual(resp.status_code, 200)


@override_settings(STATICFILES_STORAGE="django.contrib.staticfiles.storage.StaticFilesStorage")
class ContactDeleteViewTest(TestCase):
    def test_get_renders_confirmation(self):
        user = _make_user()
        c = _make_contact(user)
        resp = self.client.get(f"/{c.pk}/delete/")
        self.assertEqual(resp.status_code, 200)

    def test_post_unauthenticated_redirects(self):
        user = _make_user()
        c = _make_contact(user)
        resp = self.client.post(f"/{c.pk}/delete/")
        self.assertEqual(resp.status_code, 302)

    def test_post_authenticated_deletes_contact(self):
        user = _make_user()
        c = _make_contact(user)
        _set_session_jwt(self.client, user)
        resp = self.client.post(f"/{c.pk}/delete/")
        self.assertRedirects(resp, "/", fetch_redirect_response=False)
        self.assertFalse(Contact.objects.filter(pk=c.pk).exists())

    def test_post_wrong_owner_redirects_with_error(self):
        user = _make_user()
        user2 = _make_user(username="other")
        c = _make_contact(user2)
        _set_session_jwt(self.client, user)
        resp = self.client.post(f"/{c.pk}/delete/")
        self.assertRedirects(resp, "/", fetch_redirect_response=False)
        self.assertTrue(Contact.objects.filter(pk=c.pk).exists())


@override_settings(STATICFILES_STORAGE="django.contrib.staticfiles.storage.StaticFilesStorage")
class LiveSearchSuggestionViewTest(TestCase):
    def test_unauthenticated_returns_empty(self):
        resp = self.client.get("/search/suggestions/?q=alice")
        self.assertEqual(resp.status_code, 401)

    def test_authenticated_returns_suggestions(self):
        user = _make_user()
        _make_contact(user, name="Alice Wonder")
        _set_session_jwt(self.client, user)
        resp = self.client.get("/search/suggestions/?q=Alice")
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertIn("suggestions", data)
        self.assertIn("Alice Wonder", data["suggestions"])

    def test_empty_query_returns_no_suggestions(self):
        user = _make_user()
        _set_session_jwt(self.client, user)
        resp = self.client.get("/search/suggestions/?q=")
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertEqual(data["suggestions"], [])

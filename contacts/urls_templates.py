from django.urls import path

from .views_templates import (
    ContactCreateView,
    ContactDashboardView,
    ContactDeleteView,
    ContactUpdateView,
    LiveSearchSuggestionView,
    LoginPageView,
    LogoutPageView,
    RegisterPageView,
)

app_name = "contacts"

urlpatterns = [
    path("", ContactDashboardView.as_view(), name="dashboard"),
    path("login/", LoginPageView.as_view(), name="login"),
    path("register/", RegisterPageView.as_view(), name="register"),
    path("logout/", LogoutPageView.as_view(), name="logout"),
    path("create/", ContactCreateView.as_view(), name="create"),
    path("<int:contact_id>/edit/", ContactUpdateView.as_view(), name="edit"),
    path("<int:contact_id>/delete/", ContactDeleteView.as_view(), name="delete"),
    path("search/suggestions/", LiveSearchSuggestionView.as_view(), name="search_suggestions"),
]
"""
URL configuration for contact project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path , include
from rest_framework_simplejwt.views import TokenRefreshView, TokenObtainPairView
from drf_yasg.views import get_schema_view 
from drf_yasg import openapi

from contacts.views import RegisterView
from django.conf import settings
from django.conf.urls.static import static  
from django.views.static import serve as static_serve
from django.urls import re_path



schema_view = get_schema_view(
    openapi.Info(
        title="Contact API",
        default_version="v1",
        description="API for managing contacts"
    ),
    public=True
)


urlpatterns = [
    path('admin/', admin.site.urls),
    path("", include("contacts.urls_templates", namespace="contacts_templates")),
    path("api/login/", TokenObtainPairView.as_view(), name="login"),
    path("api/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path('contacts/', include('contacts.urls')),
    path('doc/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path("api/register/", RegisterView.as_view()),
    path("ai/", include("ai_agent.urls", namespace="ai_agent")),
]


urlpatterns += [
    re_path(r'^media/(?P<path>.*)$', static_serve, {'document_root': settings.MEDIA_ROOT}),
]

urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    
"""URLs racine du projet — toutes les routes sont nommées et regroupées par app,
comme exigé pour éviter tout NoReverseMatch ou redirection cassée.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("comptes/", include("accounts.urls")),
    path("comptes/", include("allauth.urls")),
    path("dashboard/", include("dashboard.urls")),
    path("donnees/", include("datasets.urls")),
    path("modeles/", include("forecasting.urls")),
    path("previsions/", include("predictions.urls")),
    path("i18n/", include("django.conf.urls.i18n")),
    path("", include("core.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

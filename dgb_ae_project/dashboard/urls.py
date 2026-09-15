from django.urls import path

from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.redirection_role, name="redirection_role"),
    path("admin/", views.dashboard_admin, name="admin"),
    path("analyste/", views.dashboard_analyste, name="analyste"),
    path("decideur/", views.dashboard_decideur, name="decideur"),
]

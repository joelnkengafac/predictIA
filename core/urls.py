from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.accueil, name="accueil"),
    path("journal-activite/", views.journal_activite, name="journal_activite"),
]

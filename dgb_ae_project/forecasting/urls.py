from django.urls import path

from . import views

app_name = "forecasting"

urlpatterns = [
    path("entrainer/", views.page_entrainement, name="entrainement"),
    path("entrainer/lancer/", views.lancer_entrainement, name="lancer_entrainement"),
    path("comparer/", views.page_comparaison, name="comparaison"),
    path("diagnostic/", views.page_diagnostic_serie, name="diagnostic_serie"),
]

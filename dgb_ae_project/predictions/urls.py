from django.urls import path

from . import views

app_name = "predictions"

urlpatterns = [
    path("nouvelle/", views.nouvelle_prediction, name="nouvelle"),
    path("historique/", views.historique_predictions, name="historique"),
    path("<int:pk>/exporter/<str:format_export>/", views.exporter_prediction, name="exporter"),
    path("<int:pk>/question-ia/", views.poser_question_ia, name="question_ia"),
    path("<int:pk>/supprimer/", views.supprimer_prediction, name="supprimer"),
]

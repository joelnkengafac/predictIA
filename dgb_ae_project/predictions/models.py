from django.conf import settings
from django.db import models


class Prediction(models.Model):
    """Une prévision future générée par un utilisateur pour un chapitre et un horizon donnés."""

    utilisateur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    session_entrainement = models.ForeignKey(
        "forecasting.SessionEntrainement", on_delete=models.CASCADE, related_name="predictions"
    )
    chapitre = models.PositiveIntegerField()
    modele_utilise = models.CharField(max_length=20)
    horizon_mois = models.PositiveIntegerField()
    date_creation = models.DateTimeField(auto_now_add=True)
    dates_predites = models.JSONField(help_text="Liste des dates prédites, format MM-AAAA")
    valeurs_predites = models.JSONField(help_text="Liste des taux prédits, alignée avec dates_predites")
    mae_modele = models.FloatField(null=True, blank=True)
    rmse_modele = models.FloatField(null=True, blank=True)
    r2_modele = models.FloatField(null=True, blank=True)
    mape_modele = models.FloatField(null=True, blank=True)

    class Meta:
        verbose_name = "Prévision"
        verbose_name_plural = "Prévisions"
        ordering = ["-date_creation"]

    def __str__(self) -> str:
        return f"Prévision chapitre {self.chapitre} — {self.horizon_mois} mois — {self.modele_utilise}"

    def lignes(self):
        return list(zip(self.dates_predites, self.valeurs_predites))


class MessageAssistantIA(models.Model):
    """Historique des questions posées à l'assistant IA au sujet d'une prévision.

    Conservé pour audit (traçabilité des interactions avec l'IA, exigée par
    les bonnes pratiques de gouvernance des systèmes d'aide à la décision
    publics) et pour permettre au décideur de retrouver ses échanges précédents.
    """

    prediction = models.ForeignKey(Prediction, on_delete=models.CASCADE, related_name="messages_ia")
    utilisateur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    question = models.TextField()
    reponse = models.TextField()
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Message assistant IA"
        verbose_name_plural = "Messages assistant IA"
        ordering = ["date_creation"]

    def __str__(self) -> str:
        return f"Question sur prévision #{self.prediction_id} — {self.date_creation:%d-%m-%Y %H:%M}"

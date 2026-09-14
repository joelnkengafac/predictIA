import pickle

from django.conf import settings
from django.db import models

NOMS_MODELES = [
    ("XGBoost", "XGBoost"),
    ("LightGBM", "LightGBM"),
    ("LSTM", "LSTM"),
    ("ARIMA", "ARIMA"),
]


class SessionEntrainement(models.Model):
    """Une exécution du pipeline complet (les 4 modèles entraînés et comparés ensemble)."""

    dataset = models.ForeignKey("datasets.Dataset", on_delete=models.CASCADE, related_name="sessions_entrainement")
    lance_par = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    date_entrainement = models.DateTimeField(auto_now_add=True)
    periode_train = models.CharField(max_length=50, blank=True)
    periode_test = models.CharField(max_length=50, blank=True)
    meilleur_modele = models.CharField(max_length=20, blank=True)
    explication_meilleur_modele = models.TextField(blank=True)
    est_active = models.BooleanField(
        default=True, help_text="Session actuellement utilisée pour générer les prévisions."
    )
    artefacts_pickle = models.BinaryField(
        null=True,
        blank=True,
        help_text="Sérialisation des modèles entraînés (usage interne, non exposé côté UI).",
    )

    class Meta:
        verbose_name = "Session d'entraînement"
        verbose_name_plural = "Sessions d'entraînement"
        ordering = ["-date_entrainement"]

    def __str__(self) -> str:
        return f"Entraînement du {self.date_entrainement:%d-%m-%Y %H:%M} — meilleur : {self.meilleur_modele or '—'}"

    def sauvegarder_artefacts(self, artefacts: dict) -> None:
        self.artefacts_pickle = pickle.dumps(artefacts)

    def charger_artefacts(self) -> dict:
        return pickle.loads(bytes(self.artefacts_pickle)) if self.artefacts_pickle else {}


class EvaluationModele(models.Model):
    """Les 4 métriques d'un modèle donné pour une session d'entraînement donnée."""

    session = models.ForeignKey(SessionEntrainement, on_delete=models.CASCADE, related_name="evaluations")
    nom_modele = models.CharField(max_length=20, choices=NOMS_MODELES)
    mae = models.FloatField(null=True, blank=True)
    rmse = models.FloatField(null=True, blank=True)
    r2 = models.FloatField(null=True, blank=True)
    mape = models.FloatField(null=True, blank=True)
    duree_secondes = models.FloatField(null=True, blank=True)
    statut = models.CharField(max_length=255, default="Entraîné")
    est_le_meilleur = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Évaluation de modèle"
        verbose_name_plural = "Évaluations de modèles"
        constraints = [
            models.UniqueConstraint(fields=["session", "nom_modele"], name="unique_evaluation_par_session")
        ]

    def __str__(self) -> str:
        return f"{self.nom_modele} — MAE={self.mae}, RMSE={self.rmse}, R²={self.r2}, MAPE={self.mape}"

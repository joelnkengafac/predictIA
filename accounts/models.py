from django.contrib.auth.models import AbstractUser
from django.db import models


class Role(models.TextChoices):
    ADMINISTRATEUR = "ADMIN", "Administrateur"
    ANALYSTE = "ANALYSTE", "Analyste budgétaire"
    DECIDEUR = "DECIDEUR", "Décideur"


class Utilisateur(AbstractUser):
    """Utilisateur de la plateforme, avec un rôle métier déterminant ses accès.

    On étend AbstractUser (plutôt que de repartir de zéro) pour conserver
    gratuitement toute l'infrastructure d'authentification Django éprouvée
    (mots de passe hashés, permissions, groupes, etc.).
    """

    role = models.CharField(
        max_length=20, choices=Role.choices, default=Role.DECIDEUR, verbose_name="Rôle"
    )
    telephone = models.CharField(max_length=30, blank=True, verbose_name="Téléphone")
    service = models.CharField(max_length=150, blank=True, verbose_name="Service / Direction")
    est_actif_metier = models.BooleanField(
        default=True,
        verbose_name="Compte activé",
        help_text="Désactivation métier distincte de is_active (conservée pour audit).",
    )
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Utilisateur"
        verbose_name_plural = "Utilisateurs"

    def __str__(self) -> str:
        return f"{self.get_full_name() or self.username} ({self.get_role_display()})"

    @property
    def est_admin(self) -> bool:
        return self.role == Role.ADMINISTRATEUR

    @property
    def est_analyste(self) -> bool:
        return self.role == Role.ANALYSTE

    @property
    def est_decideur(self) -> bool:
        return self.role == Role.DECIDEUR

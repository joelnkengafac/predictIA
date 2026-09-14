from django.conf import settings
from django.db import models


class JournalActivite(models.Model):
    """Journal d'audit : trace les actions importantes réalisées sur la plateforme."""

    utilisateur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="journal_entries",
    )
    action = models.CharField(max_length=255)
    adresse_ip = models.GenericIPAddressField(null=True, blank=True)
    horodatage = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Entrée du journal d'activité"
        verbose_name_plural = "Journal d'activité"
        ordering = ["-horodatage"]
        indexes = [models.Index(fields=["-horodatage"])]

    def __str__(self) -> str:
        nom = self.utilisateur.username if self.utilisateur else "Système"
        return f"[{self.horodatage:%d-%m-%Y %H:%M}] {nom} — {self.action}"

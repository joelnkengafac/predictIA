"""
Commande : configure_google_oauth
==================================
Crée ou met à jour automatiquement le SocialApp Google (django-allauth) à
partir des variables d'environnement GOOGLE_OAUTH_CLIENT_ID / _SECRET,
et l'associe au Site courant (settings.SITE_ID).

Usage :
    python manage.py configure_google_oauth

Évite d'avoir à passer par l'admin Django pour cette étape technique.
"""

import os

from django.conf import settings
from django.contrib.sites.models import Site
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Configure automatiquement le SocialApp Google à partir du .env"

    def handle(self, *args, **options):
        from allauth.socialaccount.models import SocialApp

        client_id = os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "").strip()
        client_secret = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", "").strip()

        if not client_id or not client_secret:
            raise CommandError(
                "GOOGLE_OAUTH_CLIENT_ID et GOOGLE_OAUTH_CLIENT_SECRET doivent être "
                "renseignés dans le fichier .env avant de lancer cette commande."
            )

        site, _ = Site.objects.get_or_create(
            id=settings.SITE_ID, defaults={"domain": "localhost:8000", "name": "Plateforme AE DGB/MINFI"}
        )

        app, cree = SocialApp.objects.update_or_create(
            provider="google",
            defaults={"name": "Google", "client_id": client_id, "secret": client_secret},
        )
        app.sites.add(site)

        action = "créé" if cree else "mis à jour"
        self.stdout.write(self.style.SUCCESS(f"SocialApp Google {action} avec succès (site : {site.domain})."))

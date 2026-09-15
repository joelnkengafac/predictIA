"""
Garantit qu'un objet Site avec id=settings.SITE_ID existe toujours en base.

Sans cette donnée, django-allauth provoque une erreur 500 (Site.DoesNotExist)
dès l'affichage de la page de connexion, sur toute base fraîchement migrée
en environnement de production (typiquement PostgreSQL) où la fixture par
défaut de django.contrib.sites n'a pas été chargée manuellement.
"""

from django.conf import settings
from django.db import migrations


def creer_site_par_defaut(apps, schema_editor):
    Site = apps.get_model("sites", "Site")
    Site.objects.update_or_create(
        id=getattr(settings, "SITE_ID", 1),
        defaults={"domain": "localhost:8000", "name": "Plateforme AE DGB/MINFI"},
    )


def annuler(apps, schema_editor):
    # Pas de suppression : perdre le Site casserait à nouveau l'application.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0001_initial"),
        ("sites", "0002_alter_domain_unique"),
    ]

    operations = [
        migrations.RunPython(creer_site_par_defaut, annuler),
    ]

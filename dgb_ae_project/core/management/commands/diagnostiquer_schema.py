"""
diagnostiquer_schema.py
========================
Détecte les colonnes présentes dans la BASE DE DONNÉES mais absentes des
MODÈLES Django (« colonnes orphelines »).

Contexte — pourquoi cette commande existe
-----------------------------------------
Symptôme observé :

    IntegrityError: une valeur NULL viole la contrainte NOT NULL
    de la colonne « filtre_libelle » dans la relation
    « forecasting_sessionentrainement »

`filtre_libelle` n'existe ni dans `forecasting/models.py`, ni dans les
migrations du projet. Django ne peut donc pas lui fournir de valeur à
l'INSERT, et PostgreSQL rejette la ligne car la colonne est NOT NULL sans
valeur par défaut.

Cela signifie que la base a été créée par une version ANTÉRIEURE du projet
(qui possédait ce champ), puis que les fichiers de migration ont été
régénérés/réinitialisés sans que la base ne soit recréée en conséquence. La
table conserve alors des colonnes « fantômes » dont Django ignore
l'existence — tout INSERT échoue tant qu'elles sont NOT NULL.

Cette commande ne modifie RIEN : elle se contente de lister les écarts et de
proposer le SQL correctif à exécuter en connaissance de cause.

Usage :
    python manage.py diagnostiquer_schema
"""

from django.apps import apps
from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "Liste les colonnes présentes en base mais absentes des modèles Django (lecture seule)."

    def handle(self, *args, **options):
        anomalies = []

        with connection.cursor() as cursor:
            for modele in apps.get_models():
                table = modele._meta.db_table

                # Colonnes réellement présentes en base pour cette table
                cursor.execute(
                    """
                    SELECT column_name, is_nullable, column_default
                    FROM information_schema.columns
                    WHERE table_name = %s
                    """,
                    [table],
                )
                colonnes_bdd = {ligne[0]: (ligne[1], ligne[2]) for ligne in cursor.fetchall()}
                if not colonnes_bdd:
                    continue  # table absente (migration non appliquée) — hors sujet ici

                # Colonnes attendues par le modèle Django
                colonnes_modele = {
                    champ.column for champ in modele._meta.local_fields
                }

                orphelines = sorted(set(colonnes_bdd) - colonnes_modele)
                if orphelines:
                    anomalies.append((table, orphelines, colonnes_bdd))

        if not anomalies:
            self.stdout.write(self.style.SUCCESS(
                "Aucune colonne orpheline detectee : le schema de la base correspond aux modeles."
            ))
            return

        self.stdout.write(self.style.ERROR(
            "\nCOLONNES ORPHELINES DETECTEES (presentes en base, absentes des modeles Django)\n"
        ))

        sql_correctif = []
        for table, orphelines, colonnes_bdd in anomalies:
            self.stdout.write(self.style.WARNING(f"Table : {table}"))
            for colonne in orphelines:
                nullable, defaut = colonnes_bdd[colonne]
                bloquante = nullable == "NO" and defaut is None
                marqueur = "  [BLOQUANTE - empeche tout INSERT]" if bloquante else "  (non bloquante)"
                self.stdout.write(f"    - {colonne}{marqueur}")
                sql_correctif.append(f"ALTER TABLE {table} DROP COLUMN IF EXISTS {colonne};")
            self.stdout.write("")

        self.stdout.write(self.style.MIGRATE_HEADING(
            "SQL correctif propose (a executer APRES sauvegarde de la base) :\n"
        ))
        for ligne in sql_correctif:
            self.stdout.write(f"  {ligne}")
        self.stdout.write(
            "\nCes colonnes ne sont lues par aucun code du projet : les supprimer ne "
            "fait perdre aucune donnee exploitee par l'application.\n"
        )

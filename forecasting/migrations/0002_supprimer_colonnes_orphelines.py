"""
0002_supprimer_colonnes_orphelines.py
=======================================
CORRECTIF DÉFINITIF — "IntegrityError: une valeur NULL viole la contrainte
NOT NULL de la colonne « filtre_libelle »" (et toute colonne du même genre).

Diagnostic (voir aussi `python manage.py diagnostiquer_schema`) :
la table `forecasting_sessionentrainement` contient en base des colonnes qui
n'existent dans AUCUN fichier de ce projet (`models.py` ni migrations) —
`filtre_libelle` entre autres, mais l'INTEGRITYERROR montre 5 valeurs `null`
en trop sur la ligne, donc probablement plusieurs colonnes orphelines, pas
une seule. La base a été créée par une version antérieure du projet, dont le
schéma a ensuite divergé sans qu'elle ne soit recréée.

Plutôt que de vous demander d'exécuter du SQL à la main (source d'erreur, et
qu'il faudrait refaire sur chaque poste/serveur), cette migration :
1. interroge le catalogue PostgreSQL (`information_schema.columns`) pour
   obtenir la liste RÉELLE des colonnes de `forecasting_sessionentrainement` ;
2. la compare à l'ensemble des colonnes réellement déclarées par le modèle
   Django `SessionEntrainement` ;
3. supprime uniquement les colonnes en trop (`DROP COLUMN IF EXISTS`,
   idempotent : sans danger si déjà exécutée, ou si le nombre/nom exact des
   colonnes orphelines diffère de ce qui a été observé dans les logs).

Aucune colonne utilisée par le code n'est jamais concernée : seules celles
absentes du modèle Django peuvent être supprimées.

Irréversible par choix : annuler cette migration recréerait des colonnes
NOT NULL vides, ce qui recréerait exactement le bug — la fonction `noop`
ci-dessous ne fait donc rien lors d'un `migrate` en arrière.
"""

from django.db import migrations

TABLE = "forecasting_sessionentrainement"

# Colonnes réellement déclarées par le modèle SessionEntrainement à ce jour
# (accounts/models.py) — tenu à jour manuellement ici à dessein : si ce
# modèle évolue plus tard, cette liste reste un instantané figé de ce qu'il
# fallait garantir présent au moment de CETTE migration.
COLONNES_MODELE = {
    "id",
    "date_entrainement",
    "periode_train",
    "periode_test",
    "meilleur_modele",
    "explication_meilleur_modele",
    "est_active",
    "artefacts_pickle",
    "dataset_id",
    "lance_par_id",
}


def supprimer_colonnes_orphelines(apps, schema_editor):
    connection = schema_editor.connection
    if connection.vendor != "postgresql":
        # Cette migration cible spécifiquement le symptôme observé sur
        # PostgreSQL (celui utilisé par ce projet, voir settings.py) ; sur
        # tout autre moteur on ne prend aucun risque et on ne fait rien.
        return

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = %s",
            [TABLE],
        )
        colonnes_bdd = {ligne[0] for ligne in cursor.fetchall()}

    orphelines = sorted(colonnes_bdd - COLONNES_MODELE)
    if not orphelines:
        return

    with connection.cursor() as cursor:
        for colonne in orphelines:
            cursor.execute(f'ALTER TABLE {TABLE} DROP COLUMN IF EXISTS "{colonne}"')


def noop(apps, schema_editor):
    """Migration volontairement non réversible (voir docstring du module)."""


class Migration(migrations.Migration):
    dependencies = [
        ("forecasting", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(supprimer_colonnes_orphelines, noop),
    ]

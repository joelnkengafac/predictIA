"""Expose la structure de navigation (sidebar) adaptée au rôle de l'utilisateur
courant à tous les templates, sans avoir à la reconstruire dans chaque vue.

Structure de menu alignée sur les spécifications :
- Analyste : Accueil, Dashboard, Données, Analyse, Prévisions, Comparaison, Historique, Profil
- Décideur : Accueil, Dashboard, Prévisions, Indicateurs, Rapports, Profil
- Administrateur : Dashboard, Utilisateurs, Statistiques, Paramètres, Profil

Certains libellés (« Analyse », « Indicateurs », « Statistiques », « Paramètres »)
pointent vers la page existante la plus proche fonctionnellement plutôt que de
créer une nouvelle page vide, conformément à la règle « ne pas casser / ne pas
dupliquer l'existant ». Les libellés utilisent gettext_lazy pour être traduits
automatiquement (fr/en) sans dupliquer cette structure par langue.
"""

from django.utils.translation import gettext_lazy as _

NAVIGATION_PAR_ROLE = {
    "ADMIN": [
        {"label": _("Tableau de bord"), "url": "dashboard:admin", "icon": "bi-speedometer2"},
        {"label": _("Utilisateurs"), "url": "accounts:liste_utilisateurs", "icon": "bi-people"},
        {"label": _("Statistiques"), "url": "core:journal_activite", "icon": "bi-bar-chart"},
        {"label": _("Paramètres"), "url": "accounts:profil", "icon": "bi-gear"},
        {"label": _("Données"), "url": "datasets:liste", "icon": "bi-table"},
        {"label": _("Modèles"), "url": "forecasting:entrainement", "icon": "bi-cpu"},
        {"label": _("Prévisions"), "url": "predictions:nouvelle", "icon": "bi-graph-up-arrow"},
        {"label": _("Historique"), "url": "predictions:historique", "icon": "bi-clock-history"},
        {"label": _("Journal d'activité"), "url": "core:journal_activite", "icon": "bi-journal-text"},
        {"label": _("Profil"), "url": "accounts:profil", "icon": "bi-person-circle"},
    ],
    "ANALYSTE": [
        {"label": _("Accueil"), "url": "core:accueil", "icon": "bi-house"},
        {"label": _("Tableau de bord"), "url": "dashboard:analyste", "icon": "bi-speedometer2"},
        {"label": _("Données"), "url": "datasets:liste", "icon": "bi-table"},
        {"label": _("Importer"), "url": "datasets:importer", "icon": "bi-upload"},
        {"label": _("Analyse"), "url": "forecasting:entrainement", "icon": "bi-graph-up"},
        {"label": _("Diagnostic ADF/ACF/PACF"), "url": "forecasting:diagnostic_serie", "icon": "bi-activity"},
        {"label": _("Prévisions"), "url": "predictions:nouvelle", "icon": "bi-graph-up-arrow"},
        {"label": _("Comparaison des modèles"), "url": "forecasting:comparaison", "icon": "bi-bar-chart"},
        {"label": _("Historique"), "url": "predictions:historique", "icon": "bi-clock-history"},
        {"label": _("Profil"), "url": "accounts:profil", "icon": "bi-person-circle"},
    ],
    "DECIDEUR": [
        {"label": _("Accueil"), "url": "core:accueil", "icon": "bi-house"},
        {"label": _("Tableau de bord"), "url": "dashboard:decideur", "icon": "bi-speedometer2"},
        {"label": _("Prévisions"), "url": "predictions:nouvelle", "icon": "bi-graph-up-arrow"},
        {"label": _("Indicateurs"), "url": "forecasting:comparaison", "icon": "bi-bar-chart"},
        {"label": _("Rapports"), "url": "predictions:historique", "icon": "bi-file-earmark-text"},
        {"label": _("Profil"), "url": "accounts:profil", "icon": "bi-person-circle"},
    ],
}


def navigation_context(request):
    utilisateur = getattr(request, "user", None)
    if not utilisateur or not utilisateur.is_authenticated:
        return {"menu_navigation": []}
    return {"menu_navigation": NAVIGATION_PAR_ROLE.get(utilisateur.role, [])}

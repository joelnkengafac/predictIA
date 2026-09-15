import logging

from django.core.paginator import Paginator
from django.shortcuts import render

from accounts.decorators import admin_required

from .models import JournalActivite

logger = logging.getLogger(__name__)


def accueil(request):
    """Page d'accueil publique — vitrine de la plateforme."""
    return render(request, "core/accueil.html")


@admin_required
def journal_activite(request):
    entrees = JournalActivite.objects.select_related("utilisateur").all()
    paginator = Paginator(entrees, 25)
    page = paginator.get_page(request.GET.get("page"))
    return render(request, "core/journal_activite.html", {"page_obj": page})


# ==================================================
# PAGES D'ERREUR PERSONNALISÉES (jamais de traceback exposé à l'utilisateur)
# ==================================================

def erreur_403(request, exception=None):
    logger.warning("Accès refusé (403) pour %s sur %s", getattr(request.user, "username", "anonyme"), request.path)
    return render(request, "errors/403.html", status=403)


def erreur_404(request, exception=None):
    logger.info("Page introuvable (404) : %s", request.path)
    return render(request, "errors/404.html", status=404)


def erreur_500(request):
    logger.error("Erreur serveur (500) sur %s", request.path)
    return render(request, "errors/500.html", status=500)

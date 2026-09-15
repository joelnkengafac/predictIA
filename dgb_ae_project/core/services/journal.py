"""Service centralisé d'écriture dans le journal d'activité (audit trail)."""

import logging

logger = logging.getLogger(__name__)


def _ip_client(request) -> str | None:
    if request is None:
        return None
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def enregistrer_activite(utilisateur, action: str, request=None) -> None:
    """Enregistre une entrée dans le journal d'activité.

    Échoue silencieusement (avec log) en cas de problème BDD : l'audit ne
    doit jamais faire planter le flux principal de l'application.
    """
    from core.models import JournalActivite  # import local pour éviter les cycles

    try:
        JournalActivite.objects.create(
            utilisateur=utilisateur if getattr(utilisateur, "pk", None) else None,
            action=action,
            adresse_ip=_ip_client(request),
        )
    except Exception:
        logger.exception("Impossible d'enregistrer l'entrée du journal d'activité : %s", action)

"""
rate_limit.py
=============
Limitation du nombre de tentatives de connexion, basée sur le cache Django
(fonctionne avec n'importe quel backend de cache configuré — LocMemCache par
défaut, Redis en production). Aucune dépendance externe requise.

Règle : au-delà de MAX_TENTATIVES tentatives (réussies ou échouées) pour une
même adresse IP au cours de la fenêtre glissante de FENETRE_SECONDES, la
10e est encore acceptée et la 11e est bloquée avec un message clair.
"""

from django.core.cache import cache

MAX_TENTATIVES = 10
FENETRE_SECONDES = 60
PREFIXE_CACHE = "rate_limit_connexion"


def _cle_cache(adresse_ip: str) -> str:
    return f"{PREFIXE_CACHE}:{adresse_ip}"


def _ip_client(request) -> str:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "inconnue")


def trop_de_tentatives(request) -> bool:
    """Retourne True si l'IP a déjà atteint la limite de tentatives (doit être
    appelé AVANT de traiter la tentative de connexion, pour bloquer la 11e).
    """
    cle = _cle_cache(_ip_client(request))
    compteur = cache.get(cle, 0)
    return compteur >= MAX_TENTATIVES


def enregistrer_tentative(request) -> int:
    """Incrémente le compteur de tentatives pour l'IP courante et retourne
    le nouveau total. À appeler à chaque tentative de connexion (réussie ou non).
    """
    cle = _cle_cache(_ip_client(request))
    try:
        nouveau_total = cache.incr(cle)
    except ValueError:
        # Clé absente ou expirée : on (re)initialise la fenêtre.
        cache.set(cle, 1, timeout=FENETRE_SECONDES)
        nouveau_total = 1
    return nouveau_total


def reinitialiser_tentatives(request) -> None:
    """Réinitialise le compteur après une connexion réussie."""
    cache.delete(_cle_cache(_ip_client(request)))


def secondes_avant_reessai(request) -> int:
    """Estimation du temps restant avant que la fenêtre n'expire (best-effort ;
    la plupart des backends de cache n'exposent pas le TTL restant précisément).
    """
    return FENETRE_SECONDES

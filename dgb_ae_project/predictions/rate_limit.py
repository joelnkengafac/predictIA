"""
rate_limit.py
=============
Limite le nombre de questions posées à l'assistant IA par utilisateur et par
heure. Contrairement au rate limiter de connexion (basé sur l'IP), celui-ci
est basé sur l'utilisateur authentifié, car c'est lui qui génère un coût
d'API réel à chaque question.
"""

from django.conf import settings
from django.core.cache import cache

FENETRE_SECONDES = 3600
PREFIXE_CACHE = "rate_limit_assistant_ia"


def _cle_cache(utilisateur_id: int) -> str:
    return f"{PREFIXE_CACHE}:{utilisateur_id}"


def limite_atteinte(utilisateur) -> bool:
    limite = getattr(settings, "ASSISTANT_IA_LIMITE_PAR_HEURE", 20)
    compteur = cache.get(_cle_cache(utilisateur.pk), 0)
    return compteur >= limite


def enregistrer_question(utilisateur) -> int:
    cle = _cle_cache(utilisateur.pk)
    try:
        return cache.incr(cle)
    except ValueError:
        cache.set(cle, 1, timeout=FENETRE_SECONDES)
        return 1

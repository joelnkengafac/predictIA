"""
utils.py
========
Utilitaires divers pour l'app accounts.

CORRECTIF — génération de mot de passe temporaire
---------------------------------------------------
`UserManager.make_random_password()` (utilisée auparavant dans
`accounts/views.py::creer_utilisateur`) a été DÉPRÉCIÉE dans Django 4.2 puis
RETIRÉE dans Django 5.1 (voir notes de version Django 5.1). Comme ce projet
autorise Django jusqu'à la branche 6.x (`Django>=5.0,<6.2` dans
requirements.txt), l'appeler lève désormais :

    AttributeError: 'UserManager' object has no attribute 'make_random_password'

... ce qui empêchait purement et simplement la création de tout utilisateur
par l'administrateur (le formulaire semblait "planter" sans message clair).

`generer_mot_de_passe_temporaire()` ci-dessous est un remplacement autonome,
indépendant de l'API interne de Django, qui :
- utilise `secrets` (générateur cryptographiquement sûr, PAS `random`) ;
- garantit au moins une minuscule, une majuscule, un chiffre et un caractère
  spécial, pour rester conforme dans l'esprit aux validateurs configurés
  dans `AUTH_PASSWORD_VALIDATORS` (longueur mini 9, pas 100% numérique) ;
- exclut les caractères ambigus à l'affichage (0/O, 1/l/I) puisque ce mot de
  passe temporaire est destiné à être lu et retapé par un humain.
"""

from __future__ import annotations

import secrets
import string

_MAJUSCULES = "ABCDEFGHJKLMNPQRSTUVWXYZ"  # sans I, O (ambigus)
_MINUSCULES = "abcdefghijkmnpqrstuvwxyz"  # sans l, o (ambigus)
_CHIFFRES = "23456789"  # sans 0, 1 (ambigus)
_SPECIAUX = "!@#$%^&*-_+="

_ALPHABET_COMPLET = _MAJUSCULES + _MINUSCULES + _CHIFFRES + _SPECIAUX


def generer_mot_de_passe_temporaire(longueur: int = 14) -> str:
    """Génère un mot de passe temporaire aléatoire et sûr.

    Toujours au moins 12 caractères (imposé ici, indépendamment du paramètre
    `longueur`, par sécurité) et toujours conforme à AUTH_PASSWORD_VALIDATORS
    (MinimumLengthValidator=9, NumericPasswordValidator, etc.).
    """
    longueur = max(longueur, 12)

    # On garantit la présence d'au moins un caractère de chaque catégorie,
    # puis on complète aléatoirement, puis on mélange (sinon les 4 premiers
    # caractères auraient toujours un type prévisible).
    mot_de_passe = [
        secrets.choice(_MAJUSCULES),
        secrets.choice(_MINUSCULES),
        secrets.choice(_CHIFFRES),
        secrets.choice(_SPECIAUX),
    ]
    mot_de_passe += [secrets.choice(_ALPHABET_COMPLET) for _ in range(longueur - len(mot_de_passe))]

    rng = secrets.SystemRandom()
    rng.shuffle(mot_de_passe)
    return "".join(mot_de_passe)

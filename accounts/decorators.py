"""
decorators.py
=============
Décorateurs de contrôle d'accès par rôle métier.

Un utilisateur authentifié mais sans le rôle requis est redirigé vers la
page 403 personnalisée — jamais une exception brute, jamais une 404 trompeuse.
"""

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def role_required(*roles_autorises):
    """Restreint l'accès à une vue aux utilisateurs ayant l'un des rôles donnés.

    Usage : @role_required("ADMIN", "ANALYSTE")
    """

    def decorateur(vue):
        @wraps(vue)
        @login_required(login_url="accounts:connexion")
        def vue_protegee(request, *args, **kwargs):
            if request.user.role not in roles_autorises:
                raise PermissionDenied(
                    "Vous n'avez pas les droits nécessaires pour accéder à cette page."
                )
            return vue(request, *args, **kwargs)

        return vue_protegee

    return decorateur


def admin_required(vue):
    return role_required("ADMIN")(vue)


def analyste_required(vue):
    return role_required("ADMIN", "ANALYSTE")(vue)


def decideur_required(vue):
    return role_required("ADMIN", "DECIDEUR")(vue)

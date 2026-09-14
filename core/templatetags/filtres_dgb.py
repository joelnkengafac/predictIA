"""
filtres_dgb.py
==============
Filtres de template maison pour la plateforme DGB/MINFI.

`pourcentage` : convertit une fraction stockée en base (ex: 0.0017, soit
0,17%) en une chaîne de pourcentage lisible (ex: "0.17"), en multipliant
explicitement par 100. Créé après avoir découvert un bug réel où plusieurs
templates affichaient `{{ valeur|floatformat:2 }}%` directement sur une
fraction — ce qui affiche "0.00%" au lieu de "0.17%" pour une valeur de
0.0017. Centraliser cette conversion dans un filtre unique évite de refaire
cette erreur à chaque nouvel affichage de taux.
"""

from django import template

register = template.Library()


@register.filter(name="pourcentage")
def pourcentage(valeur, decimales: int = 2):
    """Multiplie une fraction (0 à 1) par 100 et la formate avec N décimales.

    Retourne "—" si la valeur est None (jamais d'erreur de template).
    """
    if valeur is None:
        return "—"
    try:
        valeur_pct = float(valeur) * 100
    except (TypeError, ValueError):
        return "—"
    return f"{valeur_pct:.{int(decimales)}f}"

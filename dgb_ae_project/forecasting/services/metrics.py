"""
metrics.py
==========
Calcul des 4 métriques d'évaluation obligatoires : MAE, RMSE, R², MAPE.

Le MAPE est calculé de façon robuste : les observations dont le taux réel
est nul ou quasi nul (< epsilon) sont exclues du calcul du MAPE pour éviter
une division par zéro / des valeurs aberrantes qui fausseraient la comparaison
entre modèles. Le nombre de points exclus est renvoyé pour transparence.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

MAPE_EPSILON = 1e-4  # en dessous de ce seuil, un taux réel est considéré "nul"


@dataclass
class Metrics:
    mae: float
    rmse: float
    r2: float
    mape: float  # exprimé en pourcentage
    mape_n_exclus: int  # nb de points exclus du calcul du MAPE (taux réel ~ 0)

    def to_dict(self) -> dict:
        return {
            "MAE": round(self.mae, 6),
            "RMSE": round(self.rmse, 6),
            "R2": round(self.r2, 6),
            "MAPE": round(self.mape, 4),
            "mape_n_exclus": self.mape_n_exclus,
        }


def calculer_metriques(y_true: np.ndarray, y_pred: np.ndarray) -> Metrics:
    """Calcule MAE, RMSE, R² et MAPE robuste entre valeurs réelles et prédites.

    Lève ValueError si y_true / y_pred sont vides ou de tailles différentes,
    afin d'échouer tôt et clairement plutôt que de produire un résultat trompeur.
    """
    y_true = np.asarray(y_true, dtype=float).ravel()
    y_pred = np.asarray(y_pred, dtype=float).ravel()

    if y_true.shape[0] == 0 or y_pred.shape[0] == 0:
        raise ValueError("calculer_metriques: y_true ou y_pred est vide.")
    if y_true.shape[0] != y_pred.shape[0]:
        raise ValueError(
            f"calculer_metriques: tailles incompatibles (y_true={y_true.shape[0]}, "
            f"y_pred={y_pred.shape[0]})."
        )

    mae = float(mean_absolute_error(y_true, y_pred))
    rmse = float(np.sqrt(mean_squared_error(y_true, y_pred)))

    # R² nécessite au moins 2 points avec variance non nulle, sinon non défini
    if y_true.shape[0] >= 2 and np.var(y_true) > 0:
        r2 = float(r2_score(y_true, y_pred))
    else:
        r2 = float("nan")

    # MAPE robuste : on exclut les taux réels ~ 0 (division par zéro)
    mask_non_nul = np.abs(y_true) > MAPE_EPSILON
    n_exclus = int((~mask_non_nul).sum())
    if mask_non_nul.any():
        ape = np.abs((y_true[mask_non_nul] - y_pred[mask_non_nul]) / y_true[mask_non_nul])
        mape = float(np.mean(ape) * 100)
    else:
        mape = float("nan")

    return Metrics(mae=mae, rmse=rmse, r2=r2, mape=mape, mape_n_exclus=n_exclus)


def classer_modeles_par_performance(resultats: dict[str, Metrics]) -> list[str]:
    """Classe les modèles du MEILLEUR au moins bon, en combinant les 4 métriques
    (même méthode que determiner_meilleur_modele, mais retourne le classement
    complet plutôt que le seul premier). Utile pour implémenter un repli
    automatique : si le meilleur modèle échoue pour un chapitre donné (ex.
    historique insuffisant), on peut essayer le suivant dans ce classement.
    """
    if not resultats:
        raise ValueError("classer_modeles_par_performance: aucun résultat fourni.")

    noms = list(resultats.keys())

    def rang(valeurs: list[float], plus_petit_est_meilleur: bool) -> dict[str, int]:
        valeurs_valides = [(n, v) for n, v in zip(noms, valeurs) if not np.isnan(v)]
        valeurs_valides.sort(key=lambda x: x[1], reverse=not plus_petit_est_meilleur)
        return {n: i + 1 for i, (n, _v) in enumerate(valeurs_valides)}

    rangs_mae = rang([resultats[n].mae for n in noms], plus_petit_est_meilleur=True)
    rangs_rmse = rang([resultats[n].rmse for n in noms], plus_petit_est_meilleur=True)
    rangs_r2 = rang([resultats[n].r2 for n in noms], plus_petit_est_meilleur=False)
    rangs_mape = rang([resultats[n].mape for n in noms], plus_petit_est_meilleur=True)

    scores = {}
    for n in noms:
        scores[n] = (
            rangs_mae.get(n, len(noms) + 1)
            + rangs_rmse.get(n, len(noms) + 1)
            + rangs_r2.get(n, len(noms) + 1)
            + rangs_mape.get(n, len(noms) + 1)
        )

    return sorted(noms, key=lambda n: scores[n])


def determiner_meilleur_modele(resultats: dict[str, Metrics]) -> tuple[str, str]:
    """Détermine le meilleur modèle en combinant les 4 métriques (pas une seule).

    Méthode : pour chaque métrique, on classe les modèles (rang 1 = meilleur),
    puis on additionne les rangs. Le modèle avec la somme de rangs la plus
    basse est retenu. C'est une méthode simple, transparente et explicable
    à un décideur non technique.

    Retourne (nom_du_modele_retenu, explication_textuelle).
    """
    classement = classer_modeles_par_performance(resultats)
    meilleur = classement[0]
    m = resultats[meilleur]
    explication = (
        f"{meilleur} est retenu car il obtient le meilleur classement combiné sur les "
        f"4 métriques : MAE={m.mae:.4f}, RMSE={m.rmse:.4f}, R²={m.r2:.4f}, MAPE={m.mape:.2f}%."
    )
    return meilleur, explication

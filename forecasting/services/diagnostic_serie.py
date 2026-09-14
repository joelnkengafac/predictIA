"""
diagnostic_serie.py
====================
Diagnostic statistique rigoureux d'une série temporelle (par chapitre) :
- Test de stationnarité ADF (Augmented Dickey-Fuller), avec statistique,
  p-value et conclusion explicite.
- Fonction d'autocorrélation (ACF) et autocorrélation partielle (PACF),
  utilisées classiquement pour justifier le choix des ordres p (PACF) et
  q (ACF) d'un modèle ARIMA.

Ce module ne sert pas à l'entraînement lui-même (la sélection des ordres
ARIMA reste automatique par recherche en grille sur l'AIC, dans
model_arima.py) : il sert à AFFICHER et JUSTIFIER cette sélection auprès de
l'analyste, ce qui est attendu dans toute analyse de série temporelle rigoureuse.

LIMITE HONNÊTEMENT DOCUMENTÉE : les données réelles de ce projet comportent
des mois manquants pour la plupart des chapitres (couverture mensuelle
irrégulière). L'ACF/PACF et le test ADF classiques supposent un pas de temps
régulier. Ce module calcule ces diagnostics sur les SEULES valeurs réellement
observées (en ignorant les mois manquants, sans les combler artificiellement),
ce qui reste l'approche standard en pratique pour des séries irrégulières
modérément trouées, mais introduit une légère approximation si les trous sont
nombreux — le taux de couverture réel est donc toujours affiché à côté du
diagnostic, pour que l'analyste puisse juger de la fiabilité du résultat.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import acf, adfuller, pacf

from .preprocessing import reindexer_mensuel

NB_LAGS_AFFICHES = 24
SEUIL_SIGNIFICATIVITE_ADF = 0.05


@dataclass
class ResultatADF:
    statistique: float
    p_value: float
    valeurs_critiques: dict
    stationnaire: bool
    n_observations: int
    conclusion: str


@dataclass
class DiagnosticSerie:
    chapitre: int
    n_observations_reelles: int
    n_mois_calendaires: int
    taux_couverture: float
    adf: ResultatADF | None
    acf_valeurs: list[float] = field(default_factory=list)
    pacf_valeurs: list[float] = field(default_factory=list)
    seuil_significativite: float = 0.0  # borne approximative (±1.96/√n) pour lire l'ACF/PACF
    avertissement: str | None = None


def diagnostiquer_serie(df_chapitre: pd.DataFrame, nb_lags: int = NB_LAGS_AFFICHES) -> DiagnosticSerie:
    """Calcule le diagnostic ADF + ACF + PACF pour la série d'UN chapitre.

    `df_chapitre` doit être déjà filtré sur un seul chapitre et contenir les
    colonnes `date` et `taux_EngagementAE`. Le diagnostic est calculé sur les
    valeurs réellement observées (mois manquants ignorés, jamais comblés).
    """
    chapitre = int(df_chapitre["chapitre"].iloc[0])
    serie_grille = reindexer_mensuel(df_chapitre)
    n_mois_calendaires = len(serie_grille)
    serie_observee = serie_grille.dropna()
    n_observations = len(serie_observee)
    taux_couverture = n_observations / n_mois_calendaires if n_mois_calendaires else 0.0

    diagnostic = DiagnosticSerie(
        chapitre=chapitre,
        n_observations_reelles=n_observations,
        n_mois_calendaires=n_mois_calendaires,
        taux_couverture=round(taux_couverture, 3),
        adf=None,
    )

    if taux_couverture < 0.5:
        diagnostic.avertissement = (
            f"Attention : seulement {taux_couverture*100:.0f}% des mois calendaires sont "
            "réellement observés pour ce chapitre. Le test ADF et l'ACF/PACF supposent un pas "
            "de temps régulier — leur interprétation doit rester prudente sur cette série très trouée."
        )
    elif taux_couverture < 0.8:
        diagnostic.avertissement = (
            f"{taux_couverture*100:.0f}% des mois calendaires sont observés pour ce chapitre "
            "(quelques mois manquants) — le diagnostic reste indicatif."
        )

    if n_observations < 8:
        diagnostic.avertissement = (
            (diagnostic.avertissement + " ") if diagnostic.avertissement else ""
        ) + "Moins de 8 observations réelles : le test ADF n'est pas calculé (résultat non fiable en dessous de ce seuil)."
        return diagnostic

    # --- Test ADF ---
    try:
        stat, p_value, _, nobs, valeurs_critiques, _ = adfuller(serie_observee, autolag="AIC", result_object=False)
        stationnaire = p_value < SEUIL_SIGNIFICATIVITE_ADF
        conclusion = (
            f"La série est jugée STATIONNAIRE (p-value={p_value:.4f} < {SEUIL_SIGNIFICATIVITE_ADF}) : "
            "pas de différenciation nécessaire (d=0 probable)."
            if stationnaire
            else f"La série est jugée NON stationnaire (p-value={p_value:.4f} ≥ {SEUIL_SIGNIFICATIVITE_ADF}) : "
            "une différenciation est probablement nécessaire (d≥1)."
        )
        diagnostic.adf = ResultatADF(
            statistique=float(stat),
            p_value=float(p_value),
            valeurs_critiques={
                "seuil_1pct": float(valeurs_critiques.get("1%", float("nan"))),
                "seuil_5pct": float(valeurs_critiques.get("5%", float("nan"))),
                "seuil_10pct": float(valeurs_critiques.get("10%", float("nan"))),
            },
            stationnaire=stationnaire,
            n_observations=int(nobs),
            conclusion=conclusion,
        )
    except Exception:
        diagnostic.avertissement = (
            (diagnostic.avertissement + " ") if diagnostic.avertissement else ""
        ) + "Le test ADF n'a pas pu être calculé sur cette série (données insuffisamment variables)."

    # --- ACF / PACF ---
    nb_lags_effectif = min(nb_lags, n_observations // 2 - 1)
    if nb_lags_effectif >= 1:
        try:
            valeurs_acf = acf(serie_observee, nlags=nb_lags_effectif, fft=True)
            valeurs_pacf = pacf(serie_observee, nlags=nb_lags_effectif)
            diagnostic.acf_valeurs = [round(float(v), 4) for v in valeurs_acf[1:]]  # lag 0 (=1.0) exclu
            diagnostic.pacf_valeurs = [round(float(v), 4) for v in valeurs_pacf[1:]]
            diagnostic.seuil_significativite = round(1.96 / np.sqrt(n_observations), 4)
        except Exception:
            pass

    return diagnostic

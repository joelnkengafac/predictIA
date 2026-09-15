"""
model_arima.py
==============
Modèle ARIMA appliqué SÉPARÉMENT à chaque chapitre.

Les chapitres ne sont jamais mélangés dans une même série temporelle :
un dictionnaire {chapitre: modèle_ARIMA_entraîné} est conservé.
Les paramètres (p, d, q) sont sélectionnés automatiquement par recherche
en grille restreinte, en minimisant l'AIC (repli robuste si statsmodels
échoue à converger sur une combinaison).

RESPECT DE LA DISTANCE CALENDAIRE RÉELLE (point critique découvert en testant
sur des données réelles où certains chapitres n'ont qu'une observation tous
les 3 à 10 mois) : chaque série est reconstruite sur une grille mensuelle
calendaire complète (via `reindexer_mensuel`), avec des `NaN` explicites aux
mois réellement absents. `statsmodels` gère nativement ces `NaN` (filtre de
Kalman), et les prévisions continuent alors correctement à partir du vrai
dernier mois calendaire — jamais de la "dernière ligne disponible".
"""

from __future__ import annotations

import time
import warnings

import numpy as np
import pandas as pd
from statsmodels.tsa.arima.model import ARIMA
from statsmodels.tsa.stattools import adfuller

from .preprocessing import reindexer_mensuel

warnings.filterwarnings("ignore")

P_RANGE = range(0, 4)
D_RANGE = range(0, 3)
Q_RANGE = range(0, 4)

MINIMUM_OBSERVATIONS_REELLES = 8  # nombre de VRAIES observations (hors NaN), pas la longueur de la grille


def _est_stationnaire(serie: pd.Series, seuil: float = 0.05) -> bool:
    """Test ADF : True si la série est jugée stationnaire (p-value < seuil).

    Le test ADF ne tolère pas les NaN : on l'applique sur les seules valeurs
    réellement observées (dropna), ce qui reste statistiquement valide pour
    estimer l'ordre de différenciation.
    """
    serie_observee = serie.dropna()
    if len(serie_observee) < 8 or serie_observee.nunique() <= 1:
        return False
    try:
        p_value = adfuller(serie_observee)[1]
        return p_value < seuil
    except Exception:
        return False


def _meilleur_ordre_arima(serie: pd.Series) -> tuple[int, int, int]:
    """Sélectionne (p, d, q) minimisant l'AIC sur une grille restreinte.

    `serie` peut contenir des NaN (mois calendaires manquants) : statsmodels
    les gère nativement via son filtre de Kalman, sans qu'il soit nécessaire
    de les combler artificiellement.
    """
    d_init = 0 if _est_stationnaire(serie) else 1

    meilleur_aic = np.inf
    meilleur_ordre = (1, d_init, 0)
    n_observations_reelles = serie.notna().sum()

    for d in sorted({d_init, 1}):
        if d >= n_observations_reelles:
            continue
        for p in P_RANGE:
            for q in Q_RANGE:
                if p == 0 and q == 0:
                    continue
                try:
                    modele = ARIMA(serie, order=(p, d, q))
                    resultat = modele.fit()
                    if resultat.aic < meilleur_aic:
                        meilleur_aic = resultat.aic
                        meilleur_ordre = (p, d, q)
                except Exception:
                    continue

    return meilleur_ordre


def entrainer_arima_par_chapitre(
    train: pd.DataFrame, test: pd.DataFrame
) -> tuple[dict, np.ndarray, np.ndarray, float]:
    """Entraîne un ARIMA distinct par chapitre présent à la fois en train et en test.

    Retourne (dict {chapitre: (modele_fit, ordre)}, y_test_reel, y_test_pred, durée).
    Les chapitres sans historique train suffisant (< 8 VRAIES observations,
    hors mois manquants) sont ignorés pour le calcul des métriques globales.

    Les prédictions sont extraites aux dates EXACTES du jeu de test (jointure
    par date, jamais par position), pour rester correctes même si le jeu de
    test lui-même contient des mois manquants pour certains chapitres.
    """
    modeles: dict[int, tuple[object, tuple]] = {}
    y_reel, y_pred = [], []

    t0 = time.time()

    chapitres_test = sorted(test["chapitre"].unique())
    for chapitre in chapitres_test:
        train_chapitre = train[train["chapitre"] == chapitre]
        if train_chapitre.empty:
            continue

        serie_train = reindexer_mensuel(train_chapitre)
        if serie_train.notna().sum() < MINIMUM_OBSERVATIONS_REELLES:
            continue  # historique réel insuffisant pour un ARIMA fiable sur ce chapitre

        try:
            ordre = _meilleur_ordre_arima(serie_train)
            modele_fit = ARIMA(serie_train, order=ordre).fit()
        except Exception:
            continue

        modeles[chapitre] = (modele_fit, ordre)

        test_chapitre = test[test["chapitre"] == chapitre].sort_values("date")
        if test_chapitre.empty:
            continue

        derniere_date_train = serie_train.index.max()
        derniere_date_test = test_chapitre["date"].max()
        n_mois_a_prevoir = (
            (derniere_date_test.year - derniere_date_train.year) * 12
            + (derniere_date_test.month - derniere_date_train.month)
        )
        if n_mois_a_prevoir <= 0:
            continue

        try:
            prevision = modele_fit.forecast(steps=n_mois_a_prevoir)
        except Exception:
            continue

        # Jointure par DATE réelle, jamais par position : robuste même si le
        # jeu de test a lui-même des mois manquants pour ce chapitre.
        prevision_aux_dates_test = prevision.reindex(test_chapitre["date"].values)
        masque_valide = prevision_aux_dates_test.notna().values

        y_reel.extend(test_chapitre["taux_EngagementAE"].to_numpy()[masque_valide].tolist())
        y_pred.extend(prevision_aux_dates_test.to_numpy()[masque_valide].tolist())

    duree = time.time() - t0
    return modeles, np.array(y_reel), np.array(y_pred), duree


def predire_futur_arima(
    modeles: dict, chapitre: int, horizon: int, historique_complet: pd.DataFrame | pd.Series | None = None
) -> list[float]:
    """Prévision future pour un chapitre donné, en ré-entraînant sur tout l'historique
    disponible si fourni (meilleure pratique pour la prévision finale en production),
    sinon en réutilisant le modèle déjà entraîné sur train uniquement.

    `historique_complet` peut être soit un DataFrame (avec colonnes date/
    taux_EngagementAE, auquel cas il est reindexé mensuellement en respectant
    les vrais trous calendaires) soit une Series déjà correctement indexée
    par date — pour compatibilité ascendante.
    """
    if chapitre not in modeles:
        raise ValueError(
            f"predire_futur_arima: aucun modèle ARIMA disponible pour le chapitre {chapitre} "
            "(historique probablement insuffisant)."
        )

    modele_fit, ordre = modeles[chapitre]

    if historique_complet is not None:
        if isinstance(historique_complet, pd.DataFrame):
            serie_historique = reindexer_mensuel(historique_complet)
        else:
            serie_historique = historique_complet

        if serie_historique.notna().sum() >= MINIMUM_OBSERVATIONS_REELLES:
            try:
                modele_fit = ARIMA(serie_historique, order=ordre).fit()
            except Exception:
                pass  # repli sur le modèle déjà entraîné

    forecast = modele_fit.forecast(steps=horizon)
    return [float(v) for v in np.asarray(forecast)]

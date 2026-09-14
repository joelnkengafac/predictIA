"""
pipeline.py
===========
Orchestrateur du pipeline complet de prévision du taux d'engagement des AE.

Étapes :
1. Prétraitement (preprocessing.nettoyer_et_preparer)
2. Split chronologique (split.split_chronologique)
3. Entraînement des 4 modèles (XGBoost, LightGBM, LSTM, ARIMA)
4. Calcul des 4 métriques pour chacun
5. Sélection du meilleur modèle (comparaison multi-métriques)
6. Génération de prévisions futures pour un chapitre + horizon donnés

Ce module est le point d'entrée unique destiné à être appelé depuis les vues
Django (ou une tâche asynchrone Celery pour les entraînements longs, LSTM
et ARIMA en particulier).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .metrics import Metrics, calculer_metriques, determiner_meilleur_modele
from .model_arima import entrainer_arima_par_chapitre, predire_futur_arima
from .model_lightgbm import entrainer_lightgbm, predire_futur_lightgbm
from .model_lstm import entrainer_lstm, predire_futur_lstm
from .model_xgboost import entrainer_xgboost, predire_futur_xgboost
from .preprocessing import get_feature_columns, nettoyer_et_preparer
from .split import split_chronologique

logger = logging.getLogger(__name__)

NOMS_MODELES = ["XGBoost", "LightGBM", "LSTM", "ARIMA"]


@dataclass
class ResultatEntrainement:
    """Résultat complet d'une session d'entraînement des 4 modèles."""

    metriques: dict[str, Metrics] = field(default_factory=dict)
    durees: dict[str, float] = field(default_factory=dict)
    meilleur_modele: str | None = None
    explication: str | None = None
    periode_train: str | None = None
    periode_test: str | None = None
    erreurs_modeles: dict[str, str] = field(default_factory=dict)

    # Objets entraînés, conservés en mémoire pour permettre la prévision
    # immédiate sans ré-entraînement (à sérialiser/pickler côté Django si besoin).
    _artefacts: dict = field(default_factory=dict, repr=False)

    def tableau_comparatif(self) -> list[dict]:
        """Retourne le tableau Modèle | MAE | RMSE | R² | MAPE | Statut prêt pour le template."""
        lignes = []
        for nom in NOMS_MODELES:
            if nom in self.metriques:
                d = self.metriques[nom].to_dict()
                d["Modele"] = nom
                d["Statut"] = "Entraîné"
                d["meilleur"] = nom == self.meilleur_modele
            else:
                d = {
                    "Modele": nom,
                    "MAE": None,
                    "RMSE": None,
                    "R2": None,
                    "MAPE": None,
                    "Statut": f"Échec : {self.erreurs_modeles.get(nom, 'inconnu')}",
                    "meilleur": False,
                }
            lignes.append(d)
        return lignes


def entrainer_tous_les_modeles(df_brut: pd.DataFrame, train_ratio: float = 0.8) -> ResultatEntrainement:
    """Exécute le pipeline complet d'entraînement et de comparaison des 4 modèles.

    Chaque modèle est isolé dans un bloc try/except : l'échec d'un modèle
    (ex. LSTM si trop peu d'historique) n'empêche jamais les autres de
    s'entraîner, et le résultat le signale clairement plutôt que de planter.
    """
    df = nettoyer_et_preparer(df_brut)

    # Les modèles tabulaires ont besoin d'au moins le lag_1 pour être utiles ;
    # on retire les lignes sans aucun historique (début de chaque chapitre).
    df_avec_lags = df.dropna(subset=["lag_1"]).reset_index(drop=True)

    split = split_chronologique(df_avec_lags, train_ratio=train_ratio)
    resultat = ResultatEntrainement(
        periode_train=split.resume()["periode_train"],
        periode_test=split.resume()["periode_test"],
    )

    # --- XGBoost ---
    try:
        model_xgb, y_pred_xgb, duree_xgb = entrainer_xgboost(split.train, split.test)
        resultat.metriques["XGBoost"] = calculer_metriques(
            split.test["taux_EngagementAE"].to_numpy(), y_pred_xgb
        )
        resultat.durees["XGBoost"] = duree_xgb
        resultat._artefacts["XGBoost"] = model_xgb
    except Exception as exc:
        logger.exception("Échec entraînement XGBoost")
        resultat.erreurs_modeles["XGBoost"] = str(exc)

    # --- LightGBM ---
    try:
        model_lgbm, y_pred_lgbm, duree_lgbm = entrainer_lightgbm(split.train, split.test)
        resultat.metriques["LightGBM"] = calculer_metriques(
            split.test["taux_EngagementAE"].to_numpy(), y_pred_lgbm
        )
        resultat.durees["LightGBM"] = duree_lgbm
        resultat._artefacts["LightGBM"] = model_lgbm
    except Exception as exc:
        logger.exception("Échec entraînement LightGBM")
        resultat.erreurs_modeles["LightGBM"] = str(exc)

    # --- LSTM (utilise df complet, avant filtrage lag_1, pour avoir tout l'historique brut) ---
    try:
        split_lstm = split_chronologique(df, train_ratio=train_ratio)
        model_lstm, scaler_lstm, y_reel_lstm, y_pred_lstm, duree_lstm = entrainer_lstm(
            split_lstm.train, split_lstm.test, df
        )
        if len(y_reel_lstm) == 0:
            raise ValueError("Aucun point de test n'a assez d'historique pour le LSTM.")
        resultat.metriques["LSTM"] = calculer_metriques(y_reel_lstm, y_pred_lstm)
        resultat.durees["LSTM"] = duree_lstm
        resultat._artefacts["LSTM"] = (model_lstm, scaler_lstm)
    except Exception as exc:
        logger.exception("Échec entraînement LSTM")
        resultat.erreurs_modeles["LSTM"] = str(exc)

    # --- ARIMA (par chapitre, sur df complet également) ---
    try:
        split_arima = split_chronologique(df, train_ratio=train_ratio)
        modeles_arima, y_reel_arima, y_pred_arima, duree_arima = entrainer_arima_par_chapitre(
            split_arima.train, split_arima.test
        )
        if len(y_reel_arima) == 0:
            raise ValueError("Aucun chapitre n'a assez d'historique pour ARIMA.")
        resultat.metriques["ARIMA"] = calculer_metriques(y_reel_arima, y_pred_arima)
        resultat.durees["ARIMA"] = duree_arima
        resultat._artefacts["ARIMA"] = modeles_arima
    except Exception as exc:
        logger.exception("Échec entraînement ARIMA")
        resultat.erreurs_modeles["ARIMA"] = str(exc)

    if not resultat.metriques:
        raise RuntimeError(
            "Aucun des 4 modèles n'a pu être entraîné. Vérifiez le volume de données "
            "et le nombre de mois d'historique par chapitre."
        )

    meilleur, explication = determiner_meilleur_modele(resultat.metriques)
    resultat.meilleur_modele = meilleur
    resultat.explication = explication

    resultat._artefacts["df_complet"] = df  # conservé pour les prévisions futures

    return resultat


def _generer_features_futures(df_chapitre: pd.DataFrame, chapitre: int, horizon: int) -> pd.DataFrame:
    """Construit récursivement les lignes de features futures pour un chapitre.

    À chaque pas futur, les lags sont recalculés à partir de l'historique réel
    + des prédictions déjà générées aux pas précédents (approche récursive
    standard pour les modèles tabulaires en prévision multi-horizon).
    Les valeurs de taux prédites sont ajoutées au fil de l'eau par l'appelant
    via `injecter_prediction`.
    """
    historique = df_chapitre.sort_values("date")[["date", "taux_EngagementAE"]].copy()
    derniere_date = historique["date"].max()
    date_min_globale = df_chapitre["date"].min()  # non utilisé ici, cohérence avec trend_index d'origine

    lignes_futures = []
    for pas in range(1, horizon + 1):
        date_future = (derniere_date + pd.DateOffset(months=pas))
        ligne = {
            "date": date_future,
            "chapitre": chapitre,
            "annee": date_future.year,
            "mois": date_future.month,
            "trimestre": date_future.quarter,
        }
        lignes_futures.append(ligne)

    return pd.DataFrame(lignes_futures)


def _verifier_horizon_exploitable(nom_modele: str, horizon: int, n_mois_historique: int) -> list[str]:
    """Vérifie qu'un horizon donné est raisonnable au regard de l'historique
    disponible pour ce chapitre, et retourne une liste d'avertissements
    (jamais bloquants — le cahier des charges interdit de limiter l'horizon
    arbitrairement, mais impose de vérifier son exploitabilité et donc d'en
    informer l'utilisateur).
    """
    avertissements = []

    minimum_requis = {"LSTM": 12, "ARIMA": 8, "XGBoost": 12, "LightGBM": 12}.get(nom_modele, 12)
    if n_mois_historique < minimum_requis:
        avertissements.append(
            f"Attention : seuls {n_mois_historique} mois d'historique sont disponibles pour ce "
            f"chapitre, en dessous du minimum recommandé ({minimum_requis} mois) pour {nom_modele}. "
            "La prévision peut être peu fiable."
        )

    if horizon > 2 * n_mois_historique:
        avertissements.append(
            f"L'horizon demandé ({horizon} mois) dépasse largement l'historique disponible pour ce "
            f"chapitre ({n_mois_historique} mois). Les prévisions au-delà de quelques mois s'appuient "
            "sur une extrapolation de plus en plus incertaine — à interpréter avec prudence, "
            "notamment pour XGBoost/LightGBM dont la récursion peut s'arrêter prématurément si "
            "l'historique manque pour calculer un lag."
        )

    return avertissements


def generer_previsions_futures(
    resultat: ResultatEntrainement,
    chapitre: int,
    horizon: int,
    nom_modele: str | None = None,
    mois_historique_limite: int | None = None,
) -> pd.DataFrame:
    """Génère les prévisions futures pour un chapitre et un horizon donnés.

    Si `nom_modele` n'est pas précisé, utilise le meilleur modèle déterminé
    lors de l'entraînement. Retourne un DataFrame : date | chapitre | taux_prevu.

    `mois_historique_limite` (optionnel) permet de restreindre la période
    historique prise comme base de la prévision aux N derniers mois
    disponibles pour ce chapitre (ex: 24 pour ne considérer que les 2
    dernières années) — conformément à l'exigence de pouvoir choisir la
    période historique. Si None (par défaut), tout l'historique disponible
    est utilisé, comme avant l'ajout de cette option (rétrocompatible).

    Les avertissements de non-bloquants sur l'exploitabilité de l'horizon
    sont accessibles via `df_resultat.attrs["avertissements"]` (métadonnée
    pandas standard), sans changer le type de retour de la fonction.
    """
    nom_modele = nom_modele or resultat.meilleur_modele
    if nom_modele not in resultat.metriques:
        raise ValueError(f"generer_previsions_futures: modèle '{nom_modele}' indisponible.")

    df_complet = resultat._artefacts["df_complet"]
    df_chapitre = df_complet[df_complet["chapitre"] == chapitre].sort_values("date")
    if df_chapitre.empty:
        raise ValueError(f"generer_previsions_futures: chapitre {chapitre} introuvable dans les données.")

    if mois_historique_limite is not None and mois_historique_limite > 0:
        date_limite = df_chapitre["date"].max() - pd.DateOffset(months=mois_historique_limite)
        df_chapitre = df_chapitre[df_chapitre["date"] > date_limite]

    avertissements = _verifier_horizon_exploitable(nom_modele, horizon, len(df_chapitre))

    derniere_date = df_chapitre["date"].max()
    date_min_globale = df_complet["date"].min()

    if nom_modele == "LSTM":
        model_lstm, scaler_lstm = resultat._artefacts["LSTM"]
        valeurs = predire_futur_lstm(model_lstm, scaler_lstm, df_chapitre, horizon)

    elif nom_modele == "ARIMA":
        modeles_arima = resultat._artefacts["ARIMA"]
        valeurs = predire_futur_arima(modeles_arima, chapitre, horizon, historique_complet=df_chapitre)

    elif nom_modele in ("XGBoost", "LightGBM"):
        # Prévision récursive : on prédit mois par mois, en réinjectant la
        # prédiction dans l'historique pour calculer les lags du pas suivant.
        historique = df_chapitre[["date", "taux_EngagementAE"]].copy()
        valeurs = []
        for pas in range(1, horizon + 1):
            date_future = derniere_date + pd.DateOffset(months=pas)
            trend_index = (date_future.year - date_min_globale.year) * 12 + (
                date_future.month - date_min_globale.month
            )
            ligne_features = {
                "chapitre": chapitre,
                "annee": date_future.year,
                "mois": date_future.month,
                "trimestre": date_future.quarter,
                "trend_index": trend_index,
            }
            for lag in [1, 2, 3, 6, 12]:
                idx_lag = len(historique) - lag
                ligne_features[f"lag_{lag}"] = (
                    historique.iloc[idx_lag]["taux_EngagementAE"] if idx_lag >= 0 else np.nan
                )

            X_future = pd.DataFrame([ligne_features])
            if X_future[get_feature_columns()].isna().any(axis=None):
                # Historique insuffisant pour certains lags -> on arrête la récursion ici
                if pas <= horizon:
                    avertissements.append(
                        f"La prévision récursive s'est arrêtée après {pas - 1} mois (sur {horizon} "
                        "demandés) faute d'historique suffisant pour calculer les variables retardées "
                        "(lags) au-delà de ce point."
                    )
                break

            if nom_modele == "XGBoost":
                pred = predire_futur_xgboost(resultat._artefacts["XGBoost"], X_future)[0]
            else:
                pred = predire_futur_lightgbm(resultat._artefacts["LightGBM"], X_future)[0]

            valeurs.append(float(pred))
            historique = pd.concat(
                [historique, pd.DataFrame([{"date": date_future, "taux_EngagementAE": pred}])],
                ignore_index=True,
            )
    else:
        raise ValueError(f"generer_previsions_futures: modèle inconnu '{nom_modele}'.")

    if len(valeurs) < horizon:
        avertissements.append(
            f"Seules {len(valeurs)} valeur(s) sur {horizon} demandées ont pu être générées."
        )

    dates_futures = [derniere_date + pd.DateOffset(months=i + 1) for i in range(len(valeurs))]
    df_resultat = pd.DataFrame(
        {
            "date": dates_futures,
            "chapitre": chapitre,
            "taux_prevu": valeurs,
            "modele": nom_modele,
        }
    )
    df_resultat.attrs["avertissements"] = avertissements
    df_resultat.attrs["n_mois_historique_utilise"] = len(df_chapitre)
    return df_resultat

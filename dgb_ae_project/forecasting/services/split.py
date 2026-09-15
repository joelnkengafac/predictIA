"""
split.py
========
Séparation chronologique des données (jamais aléatoire).

Le seuil de coupure est déterminé sur la période globale (toutes chapitres
confondus) : les 80% des mois les plus anciens -> TRAIN, les 20% les plus
récents -> TEST. Cela garantit qu'aucune information du futur ne fuite
dans l'entraînement, quel que soit le chapitre.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class SplitResult:
    train: pd.DataFrame
    test: pd.DataFrame
    date_debut_train: pd.Timestamp
    date_fin_train: pd.Timestamp
    date_debut_test: pd.Timestamp
    date_fin_test: pd.Timestamp

    def resume(self) -> dict:
        return {
            "periode_train": (
                f"{self.date_debut_train:%m-%Y} → {self.date_fin_train:%m-%Y}"
            ),
            "periode_test": (
                f"{self.date_debut_test:%m-%Y} → {self.date_fin_test:%m-%Y}"
            ),
            "n_train": len(self.train),
            "n_test": len(self.test),
        }


def split_chronologique(df: pd.DataFrame, train_ratio: float = 0.8) -> SplitResult:
    """Découpe le dataset en TRAIN (mois les plus anciens) / TEST (mois les plus récents).

    Le split est basé sur les dates DISTINCTES (pas sur le nombre de lignes),
    pour que chaque chapitre soit coupé au même mois-frontière et que la
    comparaison entre modèles reste équitable et interprétable.
    """
    if df.empty:
        raise ValueError("split_chronologique: le dataset est vide.")

    dates_distinctes = sorted(df["date"].unique())
    n_dates = len(dates_distinctes)
    if n_dates < 5:
        raise ValueError(
            "split_chronologique: pas assez de mois distincts pour un split "
            "train/test fiable (minimum recommandé : 5)."
        )

    idx_coupure = max(1, int(round(n_dates * train_ratio)))
    idx_coupure = min(idx_coupure, n_dates - 1)  # garder au moins 1 date en test
    date_frontiere = dates_distinctes[idx_coupure - 1]

    train = df[df["date"] <= date_frontiere].copy()
    test = df[df["date"] > date_frontiere].copy()

    return SplitResult(
        train=train,
        test=test,
        date_debut_train=train["date"].min(),
        date_fin_train=train["date"].max(),
        date_debut_test=test["date"].min(),
        date_fin_test=test["date"].max(),
    )

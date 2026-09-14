"""
model_lightgbm.py
==================
Modèle LightGBM pour la prévision du taux d'engagement des AE.

Utilise exactement les mêmes features que XGBoost (preprocessing.get_feature_columns)
afin de garantir une comparaison équitable entre les deux modèles tabulaires.
"""

from __future__ import annotations

import time

import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor

from .preprocessing import get_feature_columns

DEFAULT_PARAMS = dict(
    n_estimators=400,
    max_depth=-1,
    num_leaves=31,
    learning_rate=0.05,
    subsample=0.8,
    colsample_bytree=0.8,
    reg_alpha=0.1,
    reg_lambda=1.0,
    min_child_samples=10,
    random_state=42,
    n_jobs=-1,
    verbose=-1,
)


def entrainer_lightgbm(
    train: pd.DataFrame, test: pd.DataFrame, params: dict | None = None
) -> tuple[LGBMRegressor, np.ndarray, float]:
    """Entraîne un LGBMRegressor et retourne (modèle, prédictions sur test, durée en secondes)."""
    features = get_feature_columns()
    target = "taux_EngagementAE"

    X_train, y_train = train[features], train[target]
    X_test = test[features]

    # chapitre est déclaré comme catégorielle pour laisser LightGBM exploiter
    # les splits natifs par catégorie plutôt qu'un simple ordre numérique.
    X_train = X_train.copy()
    X_test = X_test.copy()
    X_train["chapitre"] = X_train["chapitre"].astype("category")
    X_test["chapitre"] = X_test["chapitre"].astype("category")

    model = LGBMRegressor(**(params or DEFAULT_PARAMS))

    t0 = time.time()
    model.fit(X_train, y_train, categorical_feature=["chapitre"])
    duree = time.time() - t0

    y_pred = model.predict(X_test)
    return model, y_pred, duree


def predire_futur_lightgbm(model: LGBMRegressor, X_future: pd.DataFrame) -> np.ndarray:
    """Applique le modèle entraîné à un jeu de features futures déjà construit."""
    features = get_feature_columns()
    X = X_future[features].copy()
    X["chapitre"] = X["chapitre"].astype("category")
    return model.predict(X)

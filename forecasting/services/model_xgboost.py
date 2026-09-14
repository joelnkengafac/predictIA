"""
model_xgboost.py
=================
Modèle XGBoost pour la prévision du taux d'engagement des AE.

Utilise les variables temporelles (année, mois, trimestre, tendance),
le chapitre, et les variables historiques (lags). Aucun data leakage :
les lags sont calculés une seule fois en amont (preprocessing.py) à partir
du passé de chaque chapitre, jamais recalculés à partir du jeu de test.
"""

from __future__ import annotations

import time

import numpy as np
import pandas as pd
from xgboost import XGBRegressor

from .preprocessing import get_feature_columns

DEFAULT_PARAMS = dict(
    n_estimators=400,
    max_depth=4,
    learning_rate=0.05,
    subsample=0.8,
    colsample_bytree=0.8,
    reg_alpha=0.1,
    reg_lambda=1.0,
    min_child_weight=3,
    objective="reg:squarederror",
    random_state=42,
    n_jobs=-1,
)


def entrainer_xgboost(
    train: pd.DataFrame, test: pd.DataFrame, params: dict | None = None
) -> tuple[XGBRegressor, np.ndarray, float]:
    """Entraîne un XGBRegressor et retourne (modèle, prédictions sur test, durée en secondes)."""
    features = get_feature_columns()
    target = "taux_EngagementAE"

    X_train, y_train = train[features], train[target]
    X_test = test[features]

    model = XGBRegressor(**(params or DEFAULT_PARAMS))

    t0 = time.time()
    model.fit(X_train, y_train)
    duree = time.time() - t0

    y_pred = model.predict(X_test)
    return model, y_pred, duree


def predire_futur_xgboost(model: XGBRegressor, X_future: pd.DataFrame) -> np.ndarray:
    """Applique le modèle entraîné à un jeu de features futures déjà construit."""
    features = get_feature_columns()
    return model.predict(X_future[features])

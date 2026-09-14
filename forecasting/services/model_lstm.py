"""
model_lstm.py
=============
Modèle LSTM pour la prévision du taux d'engagement des AE.

Construit des séquences temporelles par chapitre (l'historique d'un chapitre
n'alimente jamais les séquences d'un autre chapitre). Le scaler est ajusté
UNIQUEMENT sur les données d'entraînement puis réutilisé tel quel sur le test
et sur les prévisions futures, pour éviter toute fuite d'information.

Architecture : Input -> LSTM -> Dropout -> LSTM -> Dropout -> Dense -> sortie (1)
Régularisation : EarlyStopping sur la perte de validation.

RESPECT DE LA DISTANCE CALENDAIRE RÉELLE (point critique découvert en testant
sur des données réelles où certains chapitres n'ont qu'une observation tous
les 3 à 10 mois) : une séquence LSTM de longueur `seq_len` doit représenter
`seq_len` MOIS CALENDAIRES VRAIMENT CONSÉCUTIFS, jamais `seq_len` lignes
disponibles prises telles quelles (qui peuvent en réalité s'étaler sur
plusieurs années si le chapitre a des trous). Toutes les séquences sont donc
construites à partir d'une grille mensuelle complète (via `reindexer_mensuel`)
et une fenêtre n'est retenue QUE si tous ses mois sont réellement observés
(aucun NaN) — sinon elle est écartée plutôt que de mélanger silencieusement
des mois non consécutifs.
"""

from __future__ import annotations

import time

import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler

from .preprocessing import reindexer_mensuel

SEQUENCE_LENGTH = 12  # nombre de mois d'historique utilisés pour prédire le mois suivant
GRAINE_ALEATOIRE = 42  # reproductibilité — sans elle, chaque entraînement produit des poids
# initiaux différents et donc des métriques légèrement différentes d'une exécution à l'autre,
# ce qui est problématique pour la comparaison objective des modèles et la reproductibilité
# des résultats (essentiel pour un mémoire académique).


def _fixer_graines_aleatoires(graine: int = GRAINE_ALEATOIRE) -> None:
    """Fixe toutes les sources d'aléatoire pertinentes (numpy + TensorFlow) pour
    que deux entraînements sur les mêmes données produisent des résultats
    reproductibles. Doit être appelé avant toute construction/entraînement du modèle.
    """
    import random

    import tensorflow as tf

    random.seed(graine)
    np.random.seed(graine)
    tf.random.set_seed(graine)


def _build_sequences(
    df_chapitre: pd.DataFrame, scaler: MinMaxScaler, seq_len: int = SEQUENCE_LENGTH
) -> tuple[np.ndarray, np.ndarray]:
    """Construit les séquences (X, y) pour UN chapitre, sur une grille mensuelle
    calendaire complète. Une fenêtre de `seq_len` mois + 1 mois cible n'est
    retenue QUE si tous les mois qu'elle couvre sont réellement observés
    (aucun trou) — sinon elle est écartée (jamais de valeur fabriquée).
    """
    serie_complete = reindexer_mensuel(df_chapitre)
    valeurs = serie_complete.to_numpy()
    valeurs_valides = ~np.isnan(valeurs)

    # On ne transforme (scaler) que les valeurs réellement présentes, mais on
    # garde la grille complète (avec NaN) pour détecter les fenêtres invalides.
    valeurs_scaled = np.full_like(valeurs, np.nan, dtype=float)
    if valeurs_valides.any():
        valeurs_scaled[valeurs_valides] = scaler.transform(
            valeurs[valeurs_valides].reshape(-1, 1)
        ).ravel()

    X, y = [], []
    for i in range(len(valeurs_scaled) - seq_len):
        fenetre = valeurs_scaled[i : i + seq_len]
        cible = valeurs_scaled[i + seq_len]
        if np.isnan(fenetre).any() or np.isnan(cible):
            continue  # mois manquant dans la fenêtre ou la cible -> séquence écartée
        X.append(fenetre)
        y.append(cible)

    if not X:
        return np.empty((0, seq_len, 1)), np.empty((0,))

    X = np.array(X).reshape(-1, seq_len, 1)
    y = np.array(y)
    return X, y


def _build_model(seq_len: int):
    # Import local pour ne charger TensorFlow que si le LSTM est réellement utilisé
    # (démarrage plus rapide de l'application pour les autres modèles).
    from tensorflow import keras
    from tensorflow.keras import layers

    model = keras.Sequential(
        [
            layers.Input(shape=(seq_len, 1)),
            layers.LSTM(64, return_sequences=True),
            layers.Dropout(0.2),
            layers.LSTM(32),
            layers.Dropout(0.2),
            layers.Dense(16, activation="relu"),
            layers.Dense(1),
        ]
    )
    model.compile(optimizer="adam", loss="mse")
    return model


def entrainer_lstm(
    train: pd.DataFrame,
    test: pd.DataFrame,
    full_df: pd.DataFrame,
    seq_len: int = SEQUENCE_LENGTH,
    epochs: int = 100,
) -> tuple[object, MinMaxScaler, np.ndarray, np.ndarray, float]:
    """Entraîne un LSTM multi-chapitres et prédit les valeurs sur la période de test.

    Le scaler est ajusté uniquement sur `train`. Pour prédire chaque point du
    test, on utilise les `seq_len` MOIS CALENDAIRES qui précèdent immédiatement
    ce point (aucun trou toléré dans la fenêtre) — un point de test dont les
    `seq_len` mois précédents ne sont pas tous observés est écarté plutôt que
    d'utiliser une fenêtre trompeuse.

    Retourne (modèle, scaler, y_test_reel, y_test_pred, durée_secondes).
    """
    from tensorflow import keras

    _fixer_graines_aleatoires()

    scaler = MinMaxScaler(feature_range=(0, 1))
    scaler.fit(train[["taux_EngagementAE"]])

    # 1) Construire les séquences d'entraînement, par chapitre, sans mélange,
    #    en écartant toute fenêtre non calendairement contiguë.
    X_train_list, y_train_list = [], []
    for chapitre, grp in train.groupby("chapitre"):
        X_c, y_c = _build_sequences(grp, scaler, seq_len)
        if len(X_c):
            X_train_list.append(X_c)
            y_train_list.append(y_c)

    if not X_train_list:
        raise ValueError(
            "entrainer_lstm: aucun chapitre ne dispose de "
            f"{seq_len} mois calendaires CONSÉCUTIFS (sans trou) pour entraîner le LSTM. "
            "Les données sont peut-être trop irrégulières (mois manquants fréquents)."
        )

    X_train = np.concatenate(X_train_list, axis=0)
    y_train = np.concatenate(y_train_list, axis=0)

    model = _build_model(seq_len)
    early_stop = keras.callbacks.EarlyStopping(
        monitor="val_loss", patience=8, restore_best_weights=True
    )

    t0 = time.time()
    model.fit(
        X_train,
        y_train,
        validation_split=0.15,
        epochs=epochs,
        batch_size=16,
        callbacks=[early_stop],
        verbose=0,
    )
    duree = time.time() - t0

    # 2) Prédiction sur le test : pour chaque point de test de chaque chapitre,
    #    on exige que les seq_len mois calendaires immédiatement précédents
    #    soient TOUS réellement observés (grille reconstruite via full_df).
    #    Batché en un seul appel model.predict() pour la performance (voir
    #    justification détaillée dans l'historique du projet : appeler
    #    model.predict() ligne par ligne coûte plusieurs dizaines de secondes
    #    inutiles à l'échelle de milliers de lignes).
    sequences, y_test_reel = [], []
    for chapitre, grp_test in test.groupby("chapitre"):
        grp_full = full_df[full_df["chapitre"] == chapitre]
        if grp_full.empty:
            continue
        serie_complete = reindexer_mensuel(grp_full)

        for _, row in grp_test.iterrows():
            date_cible = row["date"]
            fenetre_dates = pd.date_range(end=date_cible - pd.DateOffset(months=1), periods=seq_len, freq="MS")
            if not fenetre_dates.isin(serie_complete.index).all():
                continue  # fenêtre partiellement hors de la plage connue du chapitre
            fenetre_valeurs = serie_complete.reindex(fenetre_dates)
            if fenetre_valeurs.isna().any():
                continue  # au moins un mois manquant dans les seq_len mois précédents -> écarté

            seq = scaler.transform(fenetre_valeurs.to_numpy().reshape(-1, 1)).reshape(seq_len, 1)
            sequences.append(seq)
            y_test_reel.append(row["taux_EngagementAE"])

    if sequences:
        X_test_batch = np.stack(sequences, axis=0)  # (n_sequences, seq_len, 1)
        predictions_scaled = model.predict(X_test_batch, verbose=0).reshape(-1, 1)
        y_test_pred = scaler.inverse_transform(predictions_scaled).ravel().tolist()
    else:
        y_test_pred = []

    return model, scaler, np.array(y_test_reel), np.array(y_test_pred), duree


def predire_futur_lstm(
    model,
    scaler: MinMaxScaler,
    historique_chapitre: pd.DataFrame,
    horizon: int,
    seq_len: int = SEQUENCE_LENGTH,
) -> list[float]:
    """Prévision multi-pas (récursive) pour UN chapitre sur `horizon` mois.

    À chaque pas, la prédiction précédente est réinjectée dans la fenêtre
    glissante pour prédire le mois suivant (approche standard pour LSTM en
    prévision multi-horizon sans réentraînement). Exige que les `seq_len`
    DERNIERS MOIS CALENDAIRES réels du chapitre soient tous observés (sans
    trou) — sinon la fenêtre de départ serait trompeuse.
    """
    serie_complete = reindexer_mensuel(historique_chapitre)
    fenetre_initiale = serie_complete.tail(seq_len)

    if len(fenetre_initiale) < seq_len or fenetre_initiale.isna().any():
        raise ValueError(
            f"predire_futur_lstm: les {seq_len} derniers mois calendaires de ce chapitre ne sont "
            "pas tous observés (au moins un mois manquant), impossible de démarrer la prévision LSTM "
            "de façon fiable. Essayez un autre modèle (ARIMA, XGBoost, LightGBM) pour ce chapitre."
        )

    fenetre = scaler.transform(fenetre_initiale.to_numpy().reshape(-1, 1)).ravel().tolist()
    predictions = []

    for _ in range(horizon):
        seq = np.array(fenetre[-seq_len:]).reshape(1, seq_len, 1)
        pred_scaled = model.predict(seq, verbose=0)[0, 0]
        pred_scaled = float(np.clip(pred_scaled, 0.0, 1.0))
        fenetre.append(pred_scaled)
        pred = scaler.inverse_transform([[pred_scaled]])[0, 0]
        predictions.append(float(pred))

    return predictions

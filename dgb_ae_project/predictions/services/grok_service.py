"""
grok_service.py
================
Assistant IA d'interprétation des prévisions, destiné au Décideur — propulsé
par **Grok (xAI)**, via l'API officielle xAI, compatible OpenAI.

Référence officielle : https://docs.x.ai/docs/guides/chat-completions
- Base URL   : https://api.x.ai/v1
- Endpoint   : POST /chat/completions
- Auth       : en-tête "Authorization: Bearer <XAI_API_KEY>"
- Format     : identique à l'API OpenAI Chat Completions
              ({"model", "messages": [{"role", "content"}, ...]})
              -> réponse : {"choices": [{"message": {"content": "..."}}]}

Ce module remplace l'ancienne intégration Claude/Anthropic
(predictions/services/assistant_ia.py). Le contrat public (noms de fonctions,
signatures, exceptions) est conservé à l'identique pour ne rien casser côté
appelant (predictions/views.py) :
    - poser_question(prediction, question, historique_observations) -> str
    - AssistantIndisponible (exception)

Principe métier inchangé : l'IA ne reçoit JAMAIS un accès libre aux données —
uniquement un contexte structuré et borné (la prévision consultée, son
historique récent, le modèle utilisé et ses métriques). Elle est explicitement
instruite de :
- ne raisonner qu'à partir des chiffres fournis, jamais en inventer d'autres ;
- rester descriptive/explicative, jamais prescriptive (pas de conseil
  financier, juridique ou de décision budgétaire à sa place) ;
- signaler clairement les limites d'une prévision statistique.
"""

from __future__ import annotations

import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

INSTRUCTIONS_SYSTEME = """Tu es un assistant intégré à la plateforme de prévision du taux \
d'engagement des Autorisations d'Engagement (AE) de la Direction Générale du Budget (DGB) \
du Ministère des Finances du Cameroun (MINFI).

Ton rôle unique : aider un Décideur à COMPRENDRE une prévision déjà générée par le système. \
Tu ne génères pas de nouvelles prévisions, tu ne recalcules rien.

RÈGLES STRICTES :
1. Base-toi UNIQUEMENT sur les données fournies dans le contexte ci-dessous. N'invente \
jamais de chiffre, de date ou de tendance qui n'y figure pas.
2. Si une question porte sur une donnée absente du contexte, dis clairement que tu ne \
disposes pas de cette information plutôt que de l'estimer.
3. Explique les tendances en termes simples (hausse, baisse, stabilité, saisonnalité \
apparente) sans jargon technique inutile pour un décideur non spécialiste.
4. Rappelle si pertinent que la prévision est une estimation statistique (marge d'erreur \
donnée par le MAPE/RMSE), jamais une certitude.
5. Ne donne jamais de conseil financier, juridique ou de décision budgétaire définitive \
(« vous devriez... », « il faut... ») — décris les faits et laisse le décideur décider.
6. Réponds en français, de façon concise (quelques phrases, sauf si la question demande \
explicitement plus de détail).
"""

TIMEOUT_SECONDES = 30


def _construire_contexte(prediction, historique_observations) -> str:
    """Construit le bloc de contexte factuel transmis au modèle, à partir
    UNIQUEMENT des données réelles de la prévision et de son historique.
    """
    lignes_previsions = "\n".join(
        f"  - {date} : {valeur * 100:.2f}%" for date, valeur in prediction.lignes()
    )
    lignes_historique = "\n".join(
        f"  - {obs['date']} : {obs['taux'] * 100:.2f}%" for obs in historique_observations[-24:]
    )

    return f"""CONTEXTE DE LA PRÉVISION CONSULTÉE :

Chapitre budgétaire : {prediction.chapitre}
Modèle utilisé : {prediction.modele_utilise}
Horizon de prévision : {prediction.horizon_mois} mois
Date de génération : {prediction.date_creation:%d-%m-%Y}

Métriques de performance du modèle utilisé (calculées sur des données historiques réelles) :
  - MAE  : {prediction.mae_modele:.4f}
  - RMSE : {prediction.rmse_modele:.4f}
  - R²   : {prediction.r2_modele:.4f}
  - MAPE : {prediction.mape_modele:.2f}%

Historique réel récent (jusqu'à 24 derniers mois disponibles) :
{lignes_historique or "  (aucun historique disponible)"}

Valeurs prévues par le modèle :
{lignes_previsions}
"""


class AssistantIndisponible(Exception):
    """Levée quand l'assistant IA ne peut pas répondre (clé absente, erreur API, etc.)."""


def poser_question(prediction, question: str, historique_observations: list[dict]) -> str:
    """Envoie la question à Grok (xAI) avec le contexte de la prévision, retourne la réponse.

    Lève AssistantIndisponible avec un message utilisateur clair en cas de problème
    (clé API manquante, erreur réseau, quota dépassé, timeout...) — ne laisse jamais
    une exception technique brute remonter jusqu'à l'utilisateur.
    """
    if not settings.XAI_API_KEY:
        raise AssistantIndisponible(
            "L'assistant IA n'est pas configuré sur cette instance (clé API xAI manquante). "
            "Contactez votre administrateur."
        )

    contexte = _construire_contexte(prediction, historique_observations)

    payload = {
        "model": settings.XAI_MODEL,
        "messages": [
            {"role": "system", "content": INSTRUCTIONS_SYSTEME + "\n" + contexte},
            {"role": "user", "content": question.strip()[:2000]},
        ],
        "max_tokens": 600,
        "temperature": 0.3,
        "stream": False,
    }
    headers = {
        "Authorization": f"Bearer {settings.XAI_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        reponse_http = requests.post(
            settings.XAI_API_URL, json=payload, headers=headers, timeout=TIMEOUT_SECONDES
        )
    except requests.exceptions.Timeout as exc:
        logger.warning("Assistant IA (Grok) : délai d'attente dépassé.")
        raise AssistantIndisponible(
            "L'assistant IA met trop de temps à répondre. Réessayez dans un instant."
        ) from exc
    except requests.exceptions.RequestException as exc:
        logger.exception("Assistant IA (Grok) : erreur réseau.")
        raise AssistantIndisponible(
            "L'assistant IA est momentanément injoignable (problème réseau). Réessayez plus tard."
        ) from exc

    if reponse_http.status_code == 401:
        logger.error("Assistant IA (Grok) : clé API invalide (401).")
        raise AssistantIndisponible("L'assistant IA est mal configuré (clé API xAI invalide).")
    if reponse_http.status_code == 429:
        logger.warning("Assistant IA (Grok) : limite de débit atteinte côté xAI (429).")
        raise AssistantIndisponible("L'assistant IA est momentanément surchargé. Réessayez dans un instant.")
    if reponse_http.status_code >= 500:
        logger.error("Assistant IA (Grok) : erreur serveur xAI (%d).", reponse_http.status_code)
        raise AssistantIndisponible("L'assistant IA est momentanément indisponible. Réessayez plus tard.")
    if reponse_http.status_code != 200:
        logger.error(
            "Assistant IA (Grok) : réponse inattendue (%d) : %s",
            reponse_http.status_code,
            reponse_http.text[:500],
        )
        raise AssistantIndisponible("L'assistant IA a retourné une réponse inattendue. Réessayez plus tard.")

    try:
        donnees = reponse_http.json()
        texte = donnees["choices"][0]["message"]["content"].strip()
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        logger.exception("Assistant IA (Grok) : réponse JSON invalide ou inattendue.")
        raise AssistantIndisponible("L'assistant n'a pas pu formuler de réponse. Réessayez.") from exc

    if not texte:
        raise AssistantIndisponible("L'assistant n'a pas pu formuler de réponse. Réessayez.")

    return texte

"""
assistant_ia.py
================
Assistant IA d'interprétation des prévisions, destiné au Décideur.

Principe : l'IA ne reçoit JAMAIS un accès libre aux données — uniquement un
contexte structuré et borné (la prévision consultée, son historique récent,
le modèle utilisé et ses métriques). Elle est explicitement instruite de :
- ne raisonner qu'à partir des chiffres fournis, jamais en inventer d'autres ;
- rester descriptive/explicative, jamais prescriptive (pas de conseil
  financier, juridique ou de décision budgétaire à sa place) ;
- signaler clairement les limites d'une prévision statistique.

Cela évite les deux risques principaux d'un chatbot branché sur des données
budgétaires réelles : l'hallucination de chiffres et le dépassement de rôle
(un modèle de langage ne doit pas se substituer à la décision humaine).
"""

from __future__ import annotations

import logging

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
    """Envoie la question à Claude avec le contexte de la prévision, retourne la réponse.

    Lève AssistantIndisponible avec un message utilisateur clair en cas de problème
    (clé API manquante, erreur réseau, quota dépassé...) — ne laisse jamais une
    exception technique brute remonter jusqu'à l'utilisateur.
    """
    if not settings.ANTHROPIC_API_KEY:
        raise AssistantIndisponible(
            "L'assistant IA n'est pas configuré sur cette instance (clé API manquante). "
            "Contactez votre administrateur."
        )

    try:
        import anthropic
    except ImportError as exc:
        raise AssistantIndisponible(
            "Le module de l'assistant IA n'est pas installé sur le serveur."
        ) from exc

    contexte = _construire_contexte(prediction, historique_observations)

    try:
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        reponse = client.messages.create(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=600,
            system=INSTRUCTIONS_SYSTEME + "\n" + contexte,
            messages=[{"role": "user", "content": question.strip()[:2000]}],
        )
        blocs_texte = [bloc.text for bloc in reponse.content if getattr(bloc, "type", None) == "text"]
        texte = "\n".join(blocs_texte).strip()
        if not texte:
            raise AssistantIndisponible("L'assistant n'a pas pu formuler de réponse. Réessayez.")
        return texte

    except anthropic.AuthenticationError as exc:
        logger.error("Assistant IA : clé API invalide.")
        raise AssistantIndisponible("L'assistant IA est mal configuré (clé API invalide).") from exc
    except anthropic.RateLimitError as exc:
        logger.warning("Assistant IA : limite de débit atteinte côté fournisseur.")
        raise AssistantIndisponible("L'assistant IA est momentanément surchargé. Réessayez dans un instant.") from exc
    except anthropic.APIError as exc:
        logger.exception("Assistant IA : erreur API Anthropic.")
        raise AssistantIndisponible("L'assistant IA est momentanément indisponible. Réessayez plus tard.") from exc
    except Exception as exc:
        logger.exception("Assistant IA : erreur inattendue.")
        raise AssistantIndisponible("Une erreur inattendue est survenue avec l'assistant IA.") from exc

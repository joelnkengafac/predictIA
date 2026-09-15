"""
assistant_ia.py
================
CONSERVÉ POUR COMPATIBILITÉ ASCENDANTE UNIQUEMENT.

L'intégration Claude/Anthropic a été remplacée par Grok (xAI) — voir
`grok_service.py` dans ce même dossier pour l'implémentation réelle et sa
documentation. Ce module ne fait que ré-exporter la même interface publique
afin qu'un éventuel import existant de `predictions.services.assistant_ia`
continue de fonctionner sans modification.
"""

from .grok_service import AssistantIndisponible, poser_question  # noqa: F401

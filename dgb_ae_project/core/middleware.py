"""Middleware léger — actuellement un simple passe-plat, prévu comme point
d'extension pour un audit automatique de toutes les requêtes si nécessaire.
"""


class JournalActiviteMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)


class SecurityHeadersMiddleware:
    """Ajoute des en-têtes de sécurité HTTP non couverts par défaut par
    django.middleware.security.SecurityMiddleware, en complément (pas en
    remplacement) des réglages SECURE_* de settings.py.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response.setdefault("X-Content-Type-Options", "nosniff")
        response.setdefault("Referrer-Policy", "same-origin")
        response.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
        response.setdefault("X-Frame-Options", "DENY")
        return response

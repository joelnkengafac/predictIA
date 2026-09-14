from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Utilisateur


@admin.register(Utilisateur)
class UtilisateurAdmin(UserAdmin):
    list_display = ("username", "email", "role", "is_active", "date_creation")
    list_filter = ("role", "is_active")
    fieldsets = UserAdmin.fieldsets + (
        ("Informations métier", {"fields": ("role", "telephone", "service", "est_actif_metier")}),
    )

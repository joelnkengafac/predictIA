from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("connexion/", views.ConnexionView.as_view(), name="connexion"),
    path("deconnexion/", views.deconnexion, name="deconnexion"),
    path("inscription/", views.InscriptionView.as_view(), name="inscription"),
    path("profil/", views.profil, name="profil"),

    # Mot de passe oublié / réinitialisation (vues Django génériques + templates personnalisés)
    path(
        "mot-de-passe-oublie/",
        auth_views.PasswordResetView.as_view(
            template_name="accounts/mot_de_passe_oublie.html",
            email_template_name="accounts/emails/mot_de_passe_email.txt",
            subject_template_name="accounts/emails/mot_de_passe_sujet.txt",
            success_url="/comptes/mot-de-passe-oublie/envoye/",
        ),
        name="mot_de_passe_oublie",
    ),
    path(
        "mot-de-passe-oublie/envoye/",
        auth_views.PasswordResetDoneView.as_view(template_name="accounts/mot_de_passe_envoye.html"),
        name="mot_de_passe_envoye",
    ),
    path(
        "reinitialiser/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="accounts/mot_de_passe_confirmer.html",
            success_url="/comptes/reinitialiser/termine/",
        ),
        name="mot_de_passe_confirmer",
    ),
    path(
        "reinitialiser/termine/",
        auth_views.PasswordResetCompleteView.as_view(template_name="accounts/mot_de_passe_termine.html"),
        name="mot_de_passe_termine",
    ),

    # Gestion des utilisateurs (Administrateur)
    path("utilisateurs/", views.liste_utilisateurs, name="liste_utilisateurs"),
    path("utilisateurs/nouveau/", views.creer_utilisateur, name="creer_utilisateur"),
    path("utilisateurs/<int:pk>/modifier/", views.modifier_utilisateur, name="modifier_utilisateur"),
    path("utilisateurs/<int:pk>/desactiver/", views.desactiver_utilisateur, name="desactiver_utilisateur"),
    path("utilisateurs/<int:pk>/supprimer/", views.supprimer_utilisateur, name="supprimer_utilisateur"),
]

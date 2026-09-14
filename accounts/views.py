import logging

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views.generic import CreateView

from core.services.journal import enregistrer_activite

from .decorators import admin_required
from .forms import ConnexionForm, InscriptionForm, ProfilForm, UtilisateurAdminForm
from .models import Utilisateur
from .rate_limit import enregistrer_tentative, reinitialiser_tentatives, trop_de_tentatives

logger = logging.getLogger(__name__)


class ConnexionView(LoginView):
    template_name = "accounts/connexion.html"
    authentication_form = ConnexionForm
    redirect_authenticated_user = True

    def dispatch(self, request, *args, **kwargs):
        if request.method == "POST" and trop_de_tentatives(request):
            messages.error(
                request,
                "Trop de tentatives de connexion depuis cette adresse. "
                "Veuillez patienter une minute avant de réessayer.",
            )
            logger.warning("Rate limit atteint pour la connexion depuis %s", request.META.get("REMOTE_ADDR"))
            return render(request, "accounts/connexion.html", {"form": self.get_form_class()()}, status=429)
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        reinitialiser_tentatives(self.request)
        reponse = super().form_valid(form)
        enregistrer_activite(self.request.user, "Connexion réussie", request=self.request)
        return reponse

    def form_invalid(self, form):
        total = enregistrer_tentative(self.request)
        logger.warning(
            "Tentative de connexion échouée pour '%s' (tentative n°%d).",
            form.data.get("username", "?"),
            total,
        )
        return super().form_invalid(form)


@login_required
def deconnexion(request):
    enregistrer_activite(request.user, "Déconnexion", request=request)
    logout(request)
    messages.success(request, "Vous avez été déconnecté avec succès.")
    return redirect("core:accueil")


class InscriptionView(CreateView):
    """Inscription — RÉSERVÉE À L'ADMINISTRATEUR.

    Conformément à la règle métier « seul l'Administrateur peut inscrire un
    utilisateur », cette vue reste techniquement disponible (fonctionnalité
    conservée, URL inchangée) mais est désormais protégée par admin_required
    et n'est plus liée depuis les pages publiques. Le rôle attribué reste
    éditable ensuite via la gestion des utilisateurs (accounts:modifier_utilisateur).
    """

    model = Utilisateur
    form_class = InscriptionForm
    template_name = "accounts/inscription.html"
    success_url = reverse_lazy("accounts:liste_utilisateurs")

    @method_decorator(admin_required)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        reponse = super().form_valid(form)
        messages.success(
            self.request,
            f"Le compte « {self.object.username} » a été créé avec succès. "
            "Vous pouvez lui attribuer un rôle depuis la liste des utilisateurs.",
        )
        enregistrer_activite(
            self.request.user, f"Inscription de l'utilisateur {self.object.username}", request=self.request
        )
        return reponse


@login_required
def profil(request):
    if request.method == "POST":
        form = ProfilForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Votre profil a été mis à jour avec succès.")
            enregistrer_activite(request.user, "Mise à jour du profil", request=request)
            return redirect("accounts:profil")
        messages.error(request, "Le formulaire contient des erreurs. Veuillez les corriger.")
    else:
        form = ProfilForm(instance=request.user)
    return render(request, "accounts/profil.html", {"form": form})


# ==================================================
# GESTION DES UTILISATEURS (réservée à l'Administrateur)
# ==================================================

@admin_required
def liste_utilisateurs(request):
    recherche = request.GET.get("q", "").strip()
    utilisateurs = Utilisateur.objects.all().order_by("-date_creation")
    if recherche:
        utilisateurs = utilisateurs.filter(username__icontains=recherche) | utilisateurs.filter(
            email__icontains=recherche
        )

    paginator = Paginator(utilisateurs, 15)
    page = paginator.get_page(request.GET.get("page"))
    return render(
        request,
        "accounts/liste_utilisateurs.html",
        {"page_obj": page, "recherche": recherche},
    )


@admin_required
def creer_utilisateur(request):
    if request.method == "POST":
        form = UtilisateurAdminForm(request.POST)
        if form.is_valid():
            utilisateur = form.save(commit=False)
            mot_de_passe_temporaire = Utilisateur.objects.make_random_password(length=12)
            utilisateur.set_password(mot_de_passe_temporaire)
            utilisateur.save()
            messages.success(
                request,
                f"Utilisateur « {utilisateur.username} » créé avec succès. "
                f"Mot de passe temporaire : {mot_de_passe_temporaire} "
                "(à communiquer de façon sécurisée et à faire changer à la première connexion).",
            )
            enregistrer_activite(
                request.user, f"Création de l'utilisateur {utilisateur.username}", request=request
            )
            return redirect("accounts:liste_utilisateurs")
        messages.error(request, "Le formulaire contient des erreurs. Veuillez les corriger.")
    else:
        form = UtilisateurAdminForm()
    return render(request, "accounts/formulaire_utilisateur.html", {"form": form, "mode": "creation"})


@admin_required
def modifier_utilisateur(request, pk):
    utilisateur = get_object_or_404(Utilisateur, pk=pk)
    if request.method == "POST":
        form = UtilisateurAdminForm(request.POST, instance=utilisateur)
        if form.is_valid():
            form.save()
            messages.success(request, f"Utilisateur « {utilisateur.username} » modifié avec succès.")
            enregistrer_activite(
                request.user, f"Modification de l'utilisateur {utilisateur.username}", request=request
            )
            return redirect("accounts:liste_utilisateurs")
        messages.error(request, "Le formulaire contient des erreurs. Veuillez les corriger.")
    else:
        form = UtilisateurAdminForm(instance=utilisateur)
    return render(
        request, "accounts/formulaire_utilisateur.html", {"form": form, "mode": "modification", "cible": utilisateur}
    )


@admin_required
def desactiver_utilisateur(request, pk):
    utilisateur = get_object_or_404(Utilisateur, pk=pk)
    if utilisateur == request.user:
        messages.error(request, "Vous ne pouvez pas désactiver votre propre compte.")
        return redirect("accounts:liste_utilisateurs")

    if request.method == "POST":
        utilisateur.is_active = not utilisateur.is_active
        utilisateur.est_actif_metier = utilisateur.is_active
        utilisateur.save(update_fields=["is_active", "est_actif_metier"])
        etat = "réactivé" if utilisateur.is_active else "désactivé"
        messages.success(request, f"Utilisateur « {utilisateur.username} » {etat} avec succès.")
        enregistrer_activite(request.user, f"Compte {utilisateur.username} {etat}", request=request)
        return redirect("accounts:liste_utilisateurs")

    return render(request, "accounts/confirmer_action.html", {
        "titre": "Désactiver l'utilisateur" if utilisateur.is_active else "Réactiver l'utilisateur",
        "message": f"Confirmez-vous cette action pour « {utilisateur.username} » ?",
        "url_retour": "accounts:liste_utilisateurs",
    })


@admin_required
def supprimer_utilisateur(request, pk):
    utilisateur = get_object_or_404(Utilisateur, pk=pk)
    if utilisateur == request.user:
        messages.error(request, "Vous ne pouvez pas supprimer votre propre compte.")
        return redirect("accounts:liste_utilisateurs")
    if utilisateur.role == "ADMIN" and Utilisateur.objects.filter(role="ADMIN", is_active=True).count() <= 1:
        messages.error(request, "Impossible de supprimer le dernier administrateur actif du système.")
        return redirect("accounts:liste_utilisateurs")

    if request.method == "POST":
        nom = utilisateur.username
        utilisateur.delete()
        messages.success(request, f"Utilisateur « {nom} » supprimé avec succès.")
        enregistrer_activite(request.user, f"Suppression de l'utilisateur {nom}", request=request)
        return redirect("accounts:liste_utilisateurs")

    return render(request, "accounts/confirmer_action.html", {
        "titre": "Supprimer l'utilisateur",
        "message": f"Cette action est irréversible. Confirmez-vous la suppression de « {utilisateur.username} » ?",
        "url_retour": "accounts:liste_utilisateurs",
        "danger": True,
    })

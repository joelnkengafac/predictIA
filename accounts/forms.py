from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.core.exceptions import ValidationError

from .models import Role, Utilisateur

CLASSE_CHAMP = "form-control"


class ConnexionForm(AuthenticationForm):
    username = forms.CharField(
        label="Nom d'utilisateur ou email",
        widget=forms.TextInput(attrs={"class": CLASSE_CHAMP, "autofocus": True, "placeholder": "Votre identifiant"}),
    )
    password = forms.CharField(
        label="Mot de passe",
        widget=forms.PasswordInput(attrs={"class": CLASSE_CHAMP, "placeholder": "Votre mot de passe"}),
    )

    error_messages = {
        "invalid_login": "Identifiant ou mot de passe incorrect. Veuillez réessayer.",
        "inactive": "Ce compte a été désactivé. Contactez votre administrateur.",
    }


class InscriptionForm(UserCreationForm):
    """Inscription — le rôle par défaut est Décideur ; seul un administrateur
    peut promouvoir un compte en Analyste ou Administrateur (voir gestion_utilisateurs).
    """

    first_name = forms.CharField(label="Prénom", max_length=150, widget=forms.TextInput(attrs={"class": CLASSE_CHAMP}))
    last_name = forms.CharField(label="Nom", max_length=150, widget=forms.TextInput(attrs={"class": CLASSE_CHAMP}))
    email = forms.EmailField(label="Adresse email", widget=forms.EmailInput(attrs={"class": CLASSE_CHAMP}))
    service = forms.CharField(
        label="Service / Direction", max_length=150, required=False, widget=forms.TextInput(attrs={"class": CLASSE_CHAMP})
    )

    class Meta:
        model = Utilisateur
        fields = ["username", "first_name", "last_name", "email", "service", "password1", "password2"]
        widgets = {"username": forms.TextInput(attrs={"class": CLASSE_CHAMP})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for champ in ("password1", "password2"):
            self.fields[champ].widget.attrs.update({"class": CLASSE_CHAMP})

    def clean_email(self):
        email = self.cleaned_data["email"]
        if Utilisateur.objects.filter(email__iexact=email).exists():
            raise ValidationError("Un compte existe déjà avec cette adresse email.")
        return email

    def save(self, commit: bool = True):
        utilisateur = super().save(commit=False)
        utilisateur.role = Role.DECIDEUR
        if commit:
            utilisateur.save()
        return utilisateur


class UtilisateurAdminForm(forms.ModelForm):
    """Formulaire utilisé par l'Administrateur pour créer/modifier un utilisateur (avec rôle)."""

    class Meta:
        model = Utilisateur
        fields = ["username", "first_name", "last_name", "email", "role", "service", "telephone", "est_actif_metier"]
        widgets = {
            "username": forms.TextInput(attrs={"class": CLASSE_CHAMP}),
            "first_name": forms.TextInput(attrs={"class": CLASSE_CHAMP}),
            "last_name": forms.TextInput(attrs={"class": CLASSE_CHAMP}),
            "email": forms.EmailInput(attrs={"class": CLASSE_CHAMP}),
            "role": forms.Select(attrs={"class": "form-select"}),
            "service": forms.TextInput(attrs={"class": CLASSE_CHAMP}),
            "telephone": forms.TextInput(attrs={"class": CLASSE_CHAMP}),
            "est_actif_metier": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class ProfilForm(forms.ModelForm):
    class Meta:
        model = Utilisateur
        fields = ["first_name", "last_name", "email", "telephone", "service"]
        widgets = {
            "first_name": forms.TextInput(attrs={"class": CLASSE_CHAMP}),
            "last_name": forms.TextInput(attrs={"class": CLASSE_CHAMP}),
            "email": forms.EmailInput(attrs={"class": CLASSE_CHAMP}),
            "telephone": forms.TextInput(attrs={"class": CLASSE_CHAMP}),
            "service": forms.TextInput(attrs={"class": CLASSE_CHAMP}),
        }

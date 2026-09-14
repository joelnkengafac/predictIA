from django import forms

HORIZONS_PROPOSES = [(3, "3 mois"), (6, "6 mois"), (12, "12 mois"), (24, "24 mois")]

PERIODES_HISTORIQUES_PROPOSEES = [
    ("", "Toute la période disponible (recommandé)"),
    ("12", "12 derniers mois"),
    ("24", "24 derniers mois"),
    ("36", "36 derniers mois"),
    ("60", "60 derniers mois"),
]


class NouvellePredictionForm(forms.Form):
    chapitre = forms.ChoiceField(label="Chapitre", widget=forms.Select(attrs={"class": "form-select"}))
    periode_historique = forms.ChoiceField(
        label="Période historique prise en compte",
        choices=PERIODES_HISTORIQUES_PROPOSEES,
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
        help_text="Restreindre la base historique utilisée pour générer la prévision (ex : ne considérer que les tendances récentes).",
    )
    horizon_predefini = forms.ChoiceField(
        label="Horizon de prévision",
        choices=HORIZONS_PROPOSES + [("personnalise", "Personnalisé")],
        widget=forms.Select(attrs={"class": "form-select", "id": "id_horizon_predefini"}),
    )
    horizon_personnalise = forms.IntegerField(
        label="Nombre de mois (personnalisé)",
        required=False,
        min_value=1,
        max_value=60,
        widget=forms.NumberInput(attrs={"class": "form-control", "id": "id_horizon_personnalise"}),
    )
    modele = forms.ChoiceField(
        label="Modèle à utiliser",
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
        help_text="Par défaut : le meilleur modèle retenu automatiquement.",
    )

    def __init__(self, *args, chapitres_disponibles=None, modeles_disponibles=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["chapitre"].choices = [(c, f"Chapitre {c}") for c in (chapitres_disponibles or [])]
        self.fields["modele"].choices = [("", "Meilleur modèle (recommandé)")] + [
            (m, m) for m in (modeles_disponibles or [])
        ]

    def clean(self):
        cleaned = super().clean()
        horizon_predefini = cleaned.get("horizon_predefini")
        if horizon_predefini == "personnalise":
            if not cleaned.get("horizon_personnalise"):
                self.add_error("horizon_personnalise", "Veuillez indiquer un nombre de mois.")
            else:
                cleaned["horizon"] = cleaned["horizon_personnalise"]
        elif horizon_predefini:
            cleaned["horizon"] = int(horizon_predefini)

        periode = cleaned.get("periode_historique")
        cleaned["mois_historique_limite"] = int(periode) if periode else None
        return cleaned

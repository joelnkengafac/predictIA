from django.contrib.auth import get_user_model
from django.db.models import Avg, Max, Min
from django.db.models.functions import TruncMonth
from django.shortcuts import redirect, render

from accounts.decorators import admin_required, analyste_required, decideur_required
from accounts.models import Role
from core.models import JournalActivite
from datasets.models import Dataset, Observation
from forecasting.models import EvaluationModele, SessionEntrainement
from predictions.models import Prediction

Utilisateur = get_user_model()


def redirection_role(request):
    """Point d'entrée unique après connexion : redirige vers le bon tableau de bord.

    Centraliser cette logique évite toute redirection incohérente ou brisée
    ailleurs dans l'application.
    """
    if not request.user.is_authenticated:
        return redirect("accounts:connexion")

    if request.user.role == Role.ADMINISTRATEUR:
        return redirect("dashboard:admin")
    if request.user.role == Role.ANALYSTE:
        return redirect("dashboard:analyste")
    return redirect("dashboard:decideur")


@admin_required
def dashboard_admin(request):
    session_active = SessionEntrainement.objects.filter(est_active=True).select_related("dataset").first()
    dataset_actif = Dataset.objects.filter(est_actif=True).first()
    derniere_prediction = Prediction.objects.select_related("utilisateur").first()

    contexte = {
        "n_utilisateurs": Utilisateur.objects.count(),
        "n_analystes": Utilisateur.objects.filter(role=Role.ANALYSTE).count(),
        "n_decideurs": Utilisateur.objects.filter(role=Role.DECIDEUR).count(),
        "n_admins": Utilisateur.objects.filter(role=Role.ADMINISTRATEUR).count(),
        "n_lignes_dataset": dataset_actif.n_lignes if dataset_actif else 0,
        "n_chapitres": dataset_actif.n_chapitres if dataset_actif else 0,
        "date_derniere_importation": dataset_actif.date_import if dataset_actif else None,
        "modele_selectionne": session_active.meilleur_modele if session_active else None,
        "derniere_prediction": derniere_prediction,
        "activites_recentes": JournalActivite.objects.select_related("utilisateur")[:8],
    }
    return render(request, "dashboard/admin.html", contexte)


@analyste_required
def dashboard_analyste(request):
    dataset_actif = Dataset.objects.filter(est_actif=True).first()
    session_active = SessionEntrainement.objects.filter(est_active=True).first()
    evaluations = (
        EvaluationModele.objects.filter(session=session_active).order_by("nom_modele") if session_active else []
    )

    observations = Observation.objects.filter(dataset=dataset_actif) if dataset_actif else Observation.objects.none()

    stats_globales = observations.aggregate(
        taux_moyen=Avg("taux_engagement_ae"), taux_min=Min("taux_engagement_ae"), taux_max=Max("taux_engagement_ae")
    )

    # Évolution mensuelle (taux moyen tous chapitres confondus, mois par mois)
    evolution_mensuelle = list(
        observations.annotate(mois=TruncMonth("date_mois"))
        .values("mois")
        .annotate(taux_moyen=Avg("taux_engagement_ae"))
        .order_by("mois")
    )

    # Comparaison entre chapitres (taux moyen par chapitre, pour tous les repérer d'un coup d'œil)
    evolution_par_chapitre = list(
        observations.values("chapitre").annotate(taux_moyen=Avg("taux_engagement_ae")).order_by("chapitre")
    )

    contexte = {
        "dataset_actif": dataset_actif,
        "session_active": session_active,
        "evaluations": evaluations,
        "n_observations": observations.count(),
        "n_chapitres": dataset_actif.n_chapitres if dataset_actif else 0,
        "stats_globales": stats_globales,
        "evolution_mensuelle": evolution_mensuelle,
        "evolution_par_chapitre": evolution_par_chapitre,
        "mes_predictions_recentes": Prediction.objects.filter(utilisateur=request.user)[:5],
    }
    return render(request, "dashboard/analyste.html", contexte)


def _niveau_performance_qualitatif(evaluation) -> str:
    """Traduit les métriques techniques (R², MAPE) en appréciation qualitative
    compréhensible par un décideur non technicien — jamais de chiffre brut ici,
    conformément à l'exigence de ne pas exposer de détails ML inutiles.
    """
    if evaluation is None or evaluation.r2 is None:
        return "Non disponible"
    if evaluation.r2 >= 0.7:
        return "Élevée"
    if evaluation.r2 >= 0.4:
        return "Modérée"
    return "Faible — à interpréter avec prudence"


@decideur_required
def dashboard_decideur(request):
    session_active = SessionEntrainement.objects.filter(est_active=True).select_related("dataset").first()
    derniere_prediction = (
        Prediction.objects.filter(utilisateur=request.user).order_by("-date_creation").first()
        or Prediction.objects.order_by("-date_creation").first()
    )

    taux_actuel = None
    tendance = None
    niveau_performance = "Non disponible"

    if session_active:
        evaluation_meilleur = session_active.evaluations.filter(nom_modele=session_active.meilleur_modele).first()
        niveau_performance = _niveau_performance_qualitatif(evaluation_meilleur)

    if derniere_prediction:
        dataset = derniere_prediction.session_entrainement.dataset
        derniere_obs = (
            Observation.objects.filter(dataset=dataset, chapitre=derniere_prediction.chapitre)
            .order_by("-date_mois")
            .first()
        )
        if derniere_obs:
            taux_actuel = derniere_obs.taux_engagement_ae
            premiere_valeur_prevue = derniere_prediction.valeurs_predites[0] if derniere_prediction.valeurs_predites else None
            if premiere_valeur_prevue is not None:
                tendance = "Hausse" if premiere_valeur_prevue > taux_actuel else "Baisse" if premiere_valeur_prevue < taux_actuel else "Stable"

    # Chapitres nécessitant une attention particulière : ceux dont le DERNIER
    # taux observé fait partie des plus bas de l'ensemble des chapitres — signal
    # simple et transparent d'un possible sous-engagement budgétaire, sans se
    # substituer à l'analyse humaine.
    chapitres_a_surveiller = []
    if session_active:
        dataset = session_active.dataset
        derniere_date_par_chapitre = (
            Observation.objects.filter(dataset=dataset)
            .values("chapitre")
            .annotate(derniere_date=Max("date_mois"))
        )
        for entree in derniere_date_par_chapitre:
            obs = Observation.objects.filter(
                dataset=dataset, chapitre=entree["chapitre"], date_mois=entree["derniere_date"]
            ).first()
            if obs:
                chapitres_a_surveiller.append(
                    {"chapitre": obs.chapitre, "taux": obs.taux_engagement_ae, "date": obs.date_mois}
                )
        chapitres_a_surveiller.sort(key=lambda x: x["taux"])
        chapitres_a_surveiller = chapitres_a_surveiller[:5]

    contexte = {
        "session_active": session_active,
        "derniere_prediction": derniere_prediction,
        "taux_actuel": taux_actuel,
        "tendance": tendance,
        "niveau_performance": niveau_performance,
        "chapitres_a_surveiller": chapitres_a_surveiller,
    }
    return render(request, "dashboard/decideur.html", contexte)

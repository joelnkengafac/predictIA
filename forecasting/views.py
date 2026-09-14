import logging

import pandas as pd
from django.contrib import messages
from django.shortcuts import redirect, render

from accounts.decorators import analyste_required
from core.services.journal import enregistrer_activite
from datasets.models import Dataset

from .models import EvaluationModele, SessionEntrainement
from .services.diagnostic_serie import diagnostiquer_serie
from .services.pipeline import entrainer_tous_les_modeles
from .services.preprocessing import DataValidationError

logger = logging.getLogger(__name__)

NOMS_MODELES = ["XGBoost", "LightGBM", "LSTM", "ARIMA"]

# Cache mémoire process-local des artefacts de la dernière session (les objets
# scikit-learn/keras/statsmodels ne se sérialisent pas tous proprement en BDD
# pour un usage immédiat ; le pickle en base sert à la persistance long terme,
# ce cache sert à la génération immédiate de prévisions dans le même process).
_CACHE_ARTEFACTS: dict[int, object] = {}


@analyste_required
def page_entrainement(request):
    dataset_actif = Dataset.objects.filter(est_actif=True).first()
    derniere_session = SessionEntrainement.objects.filter(est_active=True).select_related("dataset").first()
    evaluations = (
        EvaluationModele.objects.filter(session=derniere_session).order_by("nom_modele")
        if derniere_session
        else []
    )
    cartes_modeles = _construire_cartes(derniere_session, evaluations)

    return render(
        request,
        "forecasting/entrainement.html",
        {
            "dataset_actif": dataset_actif,
            "derniere_session": derniere_session,
            "cartes_modeles": cartes_modeles,
        },
    )


def _construire_cartes(session, evaluations):
    evals_par_nom = {e.nom_modele: e for e in evaluations}
    cartes = []
    for nom in NOMS_MODELES:
        evaluation = evals_par_nom.get(nom)
        cartes.append(
            {
                "nom": nom,
                "statut": evaluation.statut if evaluation else "Non entraîné",
                "date": session.date_entrainement if (session and evaluation) else None,
                "duree": evaluation.duree_secondes if evaluation else None,
                "mape": evaluation.mape if evaluation else None,
                "est_le_meilleur": evaluation.est_le_meilleur if evaluation else False,
            }
        )
    return cartes


@analyste_required
def lancer_entrainement(request):
    if request.method != "POST":
        return redirect("forecasting:entrainement")

    dataset = Dataset.objects.filter(est_actif=True).first()
    if dataset is None:
        messages.error(request, "Aucun dataset actif. Veuillez d'abord importer des données.")
        return redirect("datasets:importer")

    df = pd.DataFrame.from_records(
        dataset.observations.values("date_mois", "chapitre", "taux_engagement_ae")
    ).rename(
        columns={
            "date_mois": "Mois_EngagementAE",
            "taux_engagement_ae": "taux_EngagementAE",
        }
    )
    df["Mois_EngagementAE"] = pd.to_datetime(df["Mois_EngagementAE"]).dt.strftime("%m-%Y")

    try:
        resultat = entrainer_tous_les_modeles(df)
    except DataValidationError as exc:
        messages.error(request, str(exc))
        return redirect("forecasting:entrainement")
    except Exception:
        logger.exception("Échec du pipeline d'entraînement complet")
        messages.error(
            request,
            "Une erreur est survenue lors de l'entraînement des modèles. "
            "Veuillez vérifier vos données ou réessayer.",
        )
        return redirect("forecasting:entrainement")

    SessionEntrainement.objects.filter(est_active=True).update(est_active=False)
    session = SessionEntrainement.objects.create(
        dataset=dataset,
        lance_par=request.user,
        periode_train=resultat.periode_train or "",
        periode_test=resultat.periode_test or "",
        meilleur_modele=resultat.meilleur_modele or "",
        explication_meilleur_modele=resultat.explication or "",
        est_active=True,
    )

    for ligne in resultat.tableau_comparatif():
        EvaluationModele.objects.create(
            session=session,
            nom_modele=ligne["Modele"],
            mae=ligne["MAE"],
            rmse=ligne["RMSE"],
            r2=ligne["R2"],
            mape=ligne["MAPE"],
            duree_secondes=resultat.durees.get(ligne["Modele"]),
            statut=ligne["Statut"],
            est_le_meilleur=ligne["meilleur"],
        )

    # Artefacts conservés en mémoire process pour la génération immédiate de
    # prévisions (voir predictions.views). Non bloquant si le process redémarre :
    # l'utilisateur devra relancer l'entraînement, avec message explicite.
    _CACHE_ARTEFACTS[session.pk] = resultat

    messages.success(
        request,
        f"Entraînement terminé avec succès. Meilleur modèle retenu : {resultat.meilleur_modele}.",
    )
    enregistrer_activite(
        request.user, f"Entraînement des 4 modèles (meilleur : {resultat.meilleur_modele})", request=request
    )
    return redirect("forecasting:comparaison")


def recuperer_artefacts_session(session: SessionEntrainement):
    """Retourne les artefacts en mémoire pour une session, ou None si indisponibles
    (ex. après redémarrage du serveur) — l'appelant doit alors inviter à relancer
    l'entraînement plutôt que d'échouer silencieusement.
    """
    return _CACHE_ARTEFACTS.get(session.pk)


@analyste_required
def page_diagnostic_serie(request):
    """Page de diagnostic statistique (ADF + ACF/PACF) par chapitre, destinée
    à justifier rigoureusement les choix de modélisation ARIMA auprès de
    l'analyste — pas seulement une boîte noire qui choisit (p,d,q) toute seule.
    """
    dataset = Dataset.objects.filter(est_actif=True).first()
    diagnostic = None
    chapitre_selectionne = None

    if dataset is None:
        return render(request, "forecasting/diagnostic_serie.html", {"dataset": None})

    chapitres_disponibles = sorted(
        set(dataset.observations.values_list("chapitre", flat=True))
    )

    chapitre_param = request.GET.get("chapitre")
    if chapitre_param and chapitre_param.isdigit() and int(chapitre_param) in chapitres_disponibles:
        chapitre_selectionne = int(chapitre_param)
        df_chapitre = pd.DataFrame.from_records(
            dataset.observations.filter(chapitre=chapitre_selectionne).values(
                "date_mois", "chapitre", "taux_engagement_ae"
            )
        ).rename(columns={"date_mois": "date", "taux_engagement_ae": "taux_EngagementAE"})
        df_chapitre["date"] = pd.to_datetime(df_chapitre["date"])
        diagnostic = diagnostiquer_serie(df_chapitre)

    return render(
        request,
        "forecasting/diagnostic_serie.html",
        {
            "dataset": dataset,
            "chapitres_disponibles": chapitres_disponibles,
            "chapitre_selectionne": chapitre_selectionne,
            "diagnostic": diagnostic,
        },
    )


@analyste_required
def page_comparaison(request):
    session = SessionEntrainement.objects.filter(est_active=True).select_related("dataset").first()
    if session is None:
        messages.info(request, "Aucun entraînement n'a encore été lancé.")
        return render(request, "forecasting/comparaison.html", {"session": None})

    evaluations = EvaluationModele.objects.filter(session=session).order_by("nom_modele")
    meilleur = evaluations.filter(est_le_meilleur=True).first()

    return render(
        request,
        "forecasting/comparaison.html",
        {
            "session": session,
            "evaluations": evaluations,
            "meilleur": meilleur,
        },
    )

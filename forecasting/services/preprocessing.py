"""
preprocessing.py
=================
Pipeline de prétraitement pour les données de taux d'engagement des AE (DGB/MINFI).

Supporte DEUX formats de fichier, détectés automatiquement :

FORMAT SIMPLIFIÉ (historique, 3 colonnes) :
    Mois_EngagementAE, chapitre, taux_EngagementAE

FORMAT COMPLET (7 colonnes) :
    exLibelleFrancais, exMillesime, chapitre, DotationReviseAE,
    montantEngageAE, Mois_EngagementAE, taux_EngagementAE_mensuel

Les deux formats produisent en sortie un DataFrame avec une colonne cible
canonique unique nommée `taux_EngagementAE`, afin que tout le reste du
pipeline (split.py, model_*.py, pipeline.py) continue de fonctionner sans
aucune modification, qu'il s'agisse de l'ancien ou du nouveau format.

ANTI-FUITE DE DONNÉES (exigence critique) :
`DotationReviseAE` et `montantEngageAE` ne sont JAMAIS ajoutées à
`get_feature_columns()`, car taux_EngagementAE_mensuel = montantEngageAE /
DotationReviseAE : les utiliser comme variables explicatives reviendrait à
donner au modèle la réponse déguisée. Elles sont conservées uniquement pour
stockage/affichage et pour la vérification de cohérence du taux fourni.

Ce module reste indépendant de Django et ne lève jamais d'exception non
gérée vers l'utilisateur final : toutes les erreurs métier sont remontées
via `DataValidationError` avec un message clair et actionnable.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Colonnes communes aux deux formats
COL_MOIS = "Mois_EngagementAE"
COL_CHAPITRE = "chapitre"

# Colonnes cible possibles (une seule doit être présente)
COL_TAUX_LEGACY = "taux_EngagementAE"
COL_TAUX_COMPLET = "taux_EngagementAE_mensuel"

# Colonnes optionnelles du format complet (7 colonnes)
COL_LIBELLE = "exLibelleFrancais"
COL_MILLESIME = "exMillesime"
COL_DOTATION = "DotationReviseAE"
COL_MONTANT = "montantEngageAE"

COLONNES_OPTIONNELLES = [COL_LIBELLE, COL_MILLESIME, COL_DOTATION, COL_MONTANT]

LAG_PERIODS = [1, 2, 3, 6, 12]

# Seuil au-delà duquel un écart entre taux fourni et taux recalculé
# (montant/dotation) est jugé "significatif" et signalé à l'utilisateur.
SEUIL_ECART_TAUX_SIGNIFICATIF = 0.01  # 1 point de pourcentage


class DataValidationError(Exception):
    """Erreur métier levée lorsque le dataset ne respecte pas le format attendu.

    Le message est destiné à être affiché tel quel à l'utilisateur (analyste),
    donc toujours rédigé en français clair, sans jargon technique ni traceback.
    """


@dataclass
class ValidationReport:
    """Rapport d'analyse d'un fichier importé, affiché à l'utilisateur avant traitement."""

    n_lignes: int = 0
    n_colonnes: int = 0
    colonnes_detectees: list[str] = field(default_factory=list)
    colonnes_manquantes: list[str] = field(default_factory=list)
    valeurs_manquantes: dict[str, int] = field(default_factory=dict)
    doublons: int = 0
    chapitres_detectes: list[int] = field(default_factory=list)
    periode_min: str | None = None
    periode_max: str | None = None
    erreurs: list[str] = field(default_factory=list)
    avertissements: list[str] = field(default_factory=list)

    # --- Nouveaux champs (format complet 7 colonnes) ---
    format_detecte: str = ""  # "complet" | "simplifie" | "partiel" | ""(invalide)
    colonne_cible_utilisee: str = ""
    colonnes_optionnelles_presentes: list[str] = field(default_factory=list)
    verification_taux: dict | None = None
    coherence_exercice_budgetaire: str | None = None

    @property
    def est_valide(self) -> bool:
        return len(self.erreurs) == 0

    def to_dict(self) -> dict:
        return {
            "n_lignes": self.n_lignes,
            "n_colonnes": self.n_colonnes,
            "colonnes_detectees": self.colonnes_detectees,
            "colonnes_manquantes": self.colonnes_manquantes,
            "valeurs_manquantes": self.valeurs_manquantes,
            "doublons": self.doublons,
            "chapitres_detectes": self.chapitres_detectes,
            "periode_min": self.periode_min,
            "periode_max": self.periode_max,
            "erreurs": self.erreurs,
            "avertissements": self.avertissements,
            "est_valide": self.est_valide,
            "format_detecte": self.format_detecte,
            "colonne_cible_utilisee": self.colonne_cible_utilisee,
            "colonnes_optionnelles_presentes": self.colonnes_optionnelles_presentes,
            "verification_taux": self.verification_taux,
            "coherence_exercice_budgetaire": self.coherence_exercice_budgetaire,
        }


def _detecter_colonne_cible(colonnes: list[str]) -> str | None:
    """Retourne le nom de la colonne cible présente, ou None si aucune ne l'est.

    Priorité à `taux_EngagementAE_mensuel` (format complet) si les deux
    étaient présentes simultanément (cas improbable mais géré proprement).
    """
    if COL_TAUX_COMPLET in colonnes:
        return COL_TAUX_COMPLET
    if COL_TAUX_LEGACY in colonnes:
        return COL_TAUX_LEGACY
    return None


def analyser_fichier(df_brut: pd.DataFrame) -> ValidationReport:
    """Analyse un DataFrame brut fraîchement importé (avant tout nettoyage).

    Détecte automatiquement le format (simplifié 3 colonnes ou complet 7
    colonnes) et adapte les contrôles en conséquence. Ne modifie jamais
    df_brut. Ne lève jamais d'exception : accumule les erreurs/avertissements
    dans le rapport pour affichage côté UI.
    """
    report = ValidationReport()
    report.n_lignes = len(df_brut)
    report.n_colonnes = df_brut.shape[1]
    report.colonnes_detectees = list(df_brut.columns)

    colonnes = list(df_brut.columns)
    colonne_cible = _detecter_colonne_cible(colonnes)

    colonnes_obligatoires_manquantes = []
    if COL_MOIS not in colonnes:
        colonnes_obligatoires_manquantes.append(COL_MOIS)
    if COL_CHAPITRE not in colonnes:
        colonnes_obligatoires_manquantes.append(COL_CHAPITRE)
    if colonne_cible is None:
        colonnes_obligatoires_manquantes.append(f"{COL_TAUX_LEGACY} (ou {COL_TAUX_COMPLET})")

    report.colonnes_manquantes = colonnes_obligatoires_manquantes
    if colonnes_obligatoires_manquantes:
        report.erreurs.append(
            "Colonnes manquantes dans le fichier : "
            f"{', '.join(colonnes_obligatoires_manquantes)}. "
            f"Formats acceptés : simplifié ({COL_MOIS}, {COL_CHAPITRE}, {COL_TAUX_LEGACY}) "
            f"ou complet ({COL_MOIS}, {COL_CHAPITRE}, {COL_TAUX_COMPLET}, {COL_LIBELLE}, "
            f"{COL_MILLESIME}, {COL_DOTATION}, {COL_MONTANT})."
        )
        return report

    if report.n_lignes == 0:
        report.erreurs.append("Le fichier ne contient aucune ligne de données.")
        return report

    report.colonne_cible_utilisee = colonne_cible
    colonnes_optionnelles_presentes = [c for c in COLONNES_OPTIONNELLES if c in colonnes]
    report.colonnes_optionnelles_presentes = colonnes_optionnelles_presentes
    report.format_detecte = "complet" if len(colonnes_optionnelles_presentes) == len(COLONNES_OPTIONNELLES) else (
        "simplifie" if not colonnes_optionnelles_presentes else "partiel"
    )

    colonnes_a_verifier_nulles = [COL_MOIS, COL_CHAPITRE, colonne_cible] + colonnes_optionnelles_presentes
    for col in colonnes_a_verifier_nulles:
        n_null = int(df_brut[col].isna().sum())
        if n_null > 0:
            report.valeurs_manquantes[col] = n_null

    # Doublons stricts (même mois + même chapitre)
    try:
        doublons = df_brut.duplicated(subset=[COL_MOIS, COL_CHAPITRE]).sum()
        report.doublons = int(doublons)
    except Exception:
        report.avertissements.append("Impossible de vérifier les doublons sur ce fichier.")

    # Validation du format de date
    dates_parsees = _parse_dates(df_brut[COL_MOIS])
    n_dates_invalides = int(dates_parsees.isna().sum())
    if n_dates_invalides > 0:
        report.erreurs.append(
            f"{n_dates_invalides} valeur(s) de la colonne '{COL_MOIS}' "
            "n'ont pas pu être interprétées comme une date (format attendu : MM-AAAA)."
        )

    # Validation des chapitres
    chapitres_valides = pd.to_numeric(df_brut[COL_CHAPITRE], errors="coerce")
    n_chapitres_invalides = int(chapitres_valides.isna().sum())
    if n_chapitres_invalides > 0:
        report.erreurs.append(
            f"{n_chapitres_invalides} valeur(s) de la colonne '{COL_CHAPITRE}' ne sont pas numériques."
        )
    else:
        report.chapitres_detectes = sorted(int(c) for c in chapitres_valides.dropna().unique())

    # Validation du taux cible
    taux_valides = pd.to_numeric(df_brut[colonne_cible], errors="coerce")
    n_taux_invalides = int(taux_valides.isna().sum())
    if n_taux_invalides > 0:
        report.erreurs.append(
            f"{n_taux_invalides} valeur(s) de la colonne '{colonne_cible}' ne sont pas numériques."
        )
    else:
        hors_plage = ((taux_valides < 0) | (taux_valides > 1.5)).sum()
        if hors_plage > 0:
            report.avertissements.append(
                f"{int(hors_plage)} valeur(s) de taux semblent hors plage habituelle (0 à 150%)."
            )

    # --- Contrôles spécifiques au format complet ---
    if COL_DOTATION in colonnes_optionnelles_presentes and COL_MONTANT in colonnes_optionnelles_presentes:
        dotation = pd.to_numeric(df_brut[COL_DOTATION], errors="coerce")
        montant = pd.to_numeric(df_brut[COL_MONTANT], errors="coerce")

        n_dotation_invalide = int(dotation.isna().sum())
        n_montant_invalide = int(montant.isna().sum())
        if n_dotation_invalide:
            report.erreurs.append(f"{n_dotation_invalide} valeur(s) de '{COL_DOTATION}' ne sont pas numériques.")
        if n_montant_invalide:
            report.erreurs.append(f"{n_montant_invalide} valeur(s) de '{COL_MONTANT}' ne sont pas numériques.")

        n_dotation_negative = int((dotation < 0).sum())
        n_montant_negatif = int((montant < 0).sum())
        if n_dotation_negative:
            report.avertissements.append(f"{n_dotation_negative} valeur(s) de '{COL_DOTATION}' sont négatives (anomalie potentielle).")
        if n_montant_negatif:
            report.avertissements.append(f"{n_montant_negatif} valeur(s) de '{COL_MONTANT}' sont négatives (anomalie potentielle).")

        n_dotation_nulle = int((dotation == 0).sum())
        if n_dotation_nulle:
            report.avertissements.append(
                f"{n_dotation_nulle} ligne(s) ont une '{COL_DOTATION}' égale à zéro : "
                "la vérification du taux (division) n'est pas possible pour ces lignes."
            )

        # Vérification taux fourni vs taux recalculé (montant / dotation) — SANS jamais modifier le taux fourni.
        masque_calculable = dotation.notna() & montant.notna() & (dotation != 0) & taux_valides.notna()
        if masque_calculable.any():
            taux_recalcule = montant[masque_calculable] / dotation[masque_calculable]
            ecarts = (taux_valides[masque_calculable] - taux_recalcule).abs()
            n_significatifs = int((ecarts > SEUIL_ECART_TAUX_SIGNIFICATIF).sum())
            report.verification_taux = {
                "n_lignes_verifiees": int(masque_calculable.sum()),
                "ecart_moyen": float(ecarts.mean()),
                "ecart_max": float(ecarts.max()),
                "n_ecarts_significatifs": n_significatifs,
                "seuil_significatif": SEUIL_ECART_TAUX_SIGNIFICATIF,
            }
            if n_significatifs > 0:
                report.avertissements.append(
                    f"{n_significatifs} ligne(s) présentent un écart de plus de "
                    f"{SEUIL_ECART_TAUX_SIGNIFICATIF*100:.0f} point(s) entre le taux fourni et le taux "
                    f"recalculé (montantEngageAE / DotationReviseAE). Le taux fourni est conservé tel "
                    "quel ; cet écart est documenté à titre informatif uniquement."
                )
            else:
                report.avertissements.append(
                    "Vérification effectuée : le taux fourni est cohérent avec montantEngageAE / "
                    f"DotationReviseAE (écart moyen {report.verification_taux['ecart_moyen']:.6f})."
                )

    # --- Cohérence exMillesime / année civile (sans jamais supposer une formule fixe) ---
    if COL_MILLESIME in colonnes_optionnelles_presentes and dates_parsees.notna().any():
        millesime = pd.to_numeric(df_brut[COL_MILLESIME], errors="coerce")
        masque = millesime.notna() & dates_parsees.notna()
        if masque.any():
            ecarts_exercice = (millesime[masque] - dates_parsees[masque].dt.year).unique()
            if len(ecarts_exercice) == 1:
                report.coherence_exercice_budgetaire = (
                    f"Correspondance constante détectée : exMillesime = année civile + ({int(ecarts_exercice[0])}). "
                    "Cette correspondance sera utilisée pour les prévisions futures."
                )
            else:
                report.coherence_exercice_budgetaire = (
                    "Aucune correspondance constante entre exMillesime et l'année civile n'a été détectée "
                    "sur ce fichier (plusieurs décalages observés). Par prudence, exMillesime ne sera pas "
                    "extrapolé pour les prévisions futures — il reste disponible pour l'analyse historique."
                )
                report.avertissements.append(report.coherence_exercice_budgetaire)

    if dates_parsees.notna().any():
        report.periode_min = str(dates_parsees.min().strftime("%m-%Y"))
        report.periode_max = str(dates_parsees.max().strftime("%m-%Y"))

    if report.doublons > 0:
        report.avertissements.append(
            f"{report.doublons} doublon(s) détecté(s) (même mois + même chapitre) : "
            "les valeurs seront fusionnées par moyenne lors du traitement."
        )

    return report


def lire_csv_intelligent(fichier) -> pd.DataFrame:
    """Lit un fichier CSV en détectant automatiquement le séparateur de colonnes
    (virgule ou point-virgule) et la convention décimale (point ou virgule).

    Les exports depuis Excel en France utilisent typiquement le point-virgule
    comme séparateur de colonnes ET la virgule comme séparateur décimal
    (ex: "0,0017" pour 0.0017) — un simple `pd.read_csv(fichier)` par défaut
    échoue purement et simplement sur ce genre de fichier (ce qui a été
    confirmé en testant avec un vrai export DGB). Cette fonction essaie
    plusieurs combinaisons raisonnables et retient la première qui produit
    un DataFrame exploitable (plus d'une colonne).
    """
    tentatives = [
        {"sep": ",", "decimal": "."},  # format anglo-saxon standard
        {"sep": ";", "decimal": ","},  # format Excel français (le plus courant en pratique)
        {"sep": ";", "decimal": "."},
        {"sep": ",", "decimal": ","},
    ]
    derniere_erreur = None
    for params in tentatives:
        try:
            fichier.seek(0)
        except (AttributeError, ValueError):
            pass
        try:
            df = pd.read_csv(fichier, **params)
        except Exception as exc:
            derniere_erreur = exc
            continue
        if df.shape[1] > 1:
            return df
    if derniere_erreur:
        raise derniere_erreur
    raise ValueError("Impossible d'interpréter le fichier CSV avec les formats connus.")


def _parse_dates(serie: pd.Series) -> pd.Series:
    """Parse une colonne de dates au format MM-AAAA (avec repli sur d'autres formats)."""
    parsed = pd.to_datetime(serie, format="%m-%Y", errors="coerce")
    mask_na = parsed.isna()
    if mask_na.any():
        fallback = pd.to_datetime(serie[mask_na], errors="coerce")
        parsed.loc[mask_na] = fallback
    return parsed


def nettoyer_et_preparer(df_brut: pd.DataFrame) -> pd.DataFrame:
    """Nettoie le dataset et calcule toutes les features nécessaires à l'entraînement.

    Fonctionne indifféremment sur le format simplifié (3 colonnes) ou complet
    (7 colonnes) : dans les deux cas, la colonne cible est normalisée en
    interne sous le nom `taux_EngagementAE`, afin que le reste du pipeline
    (split, modèles) reste totalement inchangé.

    Étapes :
    1. Validation stricte (lève DataValidationError si le format est invalide).
    2. Normalisation de la colonne cible vers le nom canonique `taux_EngagementAE`.
    3. Fusion des doublons (même mois + même chapitre) par MOYENNE (taux ET
       montants budgétaires si présents) — jamais par suppression arbitraire.
    4. Suppression des lignes avec valeurs manquantes critiques.
    5. Conversion de la date + tri chronologique PAR CHAPITRE.
    6. Extraction des features temporelles (année, mois, trimestre, index/tendance).
    7. Calcul de l'écart taux fourni / taux recalculé (colonne informative uniquement).
    8. Calcul des lags (1, 2, 3, 6, 12) — calculés séparément par chapitre, jamais mélangés.

    Retourne un DataFrame propre contenant au minimum :
    date, annee, mois, trimestre, chapitre, trend_index,
    lag_1..lag_12, taux_EngagementAE
    et, si le format complet est utilisé, également :
    ex_libelle_francais, ex_millesime, dotation_revisee_ae, montant_engage_ae,
    ecart_taux_calcule (toutes présentes mais à NaN/vide si non fournies,
    pour que le code appelant n'ait jamais à tester leur existence).
    """
    report = analyser_fichier(df_brut)
    if not report.est_valide:
        raise DataValidationError(" ".join(report.erreurs))

    df = df_brut.copy()
    colonne_cible = report.colonne_cible_utilisee

    # 1) Normalisation de la colonne cible vers le nom canonique interne
    if colonne_cible != COL_TAUX_LEGACY:
        df = df.rename(columns={colonne_cible: COL_TAUX_LEGACY})

    # 2) Types de base
    df["chapitre"] = pd.to_numeric(df["chapitre"], errors="coerce").astype("Int64")
    df["taux_EngagementAE"] = pd.to_numeric(df["taux_EngagementAE"], errors="coerce")
    df["date"] = _parse_dates(df[COL_MOIS])

    # 3) Colonnes optionnelles : toujours créées (à NaN/vide si absentes du fichier)
    #    pour que le code appelant (datasets/views.py) n'ait jamais à tester leur présence.
    df["ex_libelle_francais"] = df[COL_LIBELLE].astype(str) if COL_LIBELLE in df.columns else ""
    df["ex_millesime"] = pd.to_numeric(df[COL_MILLESIME], errors="coerce") if COL_MILLESIME in df.columns else np.nan
    df["dotation_revisee_ae"] = pd.to_numeric(df[COL_DOTATION], errors="coerce") if COL_DOTATION in df.columns else np.nan
    df["montant_engage_ae"] = pd.to_numeric(df[COL_MONTANT], errors="coerce") if COL_MONTANT in df.columns else np.nan

    # 4) Lignes invalides après conversion -> supprimées avec log (pas d'erreur silencieuse)
    n_avant = len(df)
    df = df.dropna(subset=["chapitre", "taux_EngagementAE", "date"])
    n_supprimees = n_avant - len(df)
    if n_supprimees > 0:
        logger.warning("nettoyer_et_preparer: %d ligne(s) invalide(s) supprimée(s).", n_supprimees)

    # 4bis) Écart taux fourni / taux recalculé — calculé LIGNE PAR LIGNE, sur les
    #    données BRUTES avant toute fusion de doublons. C'est essentiel : la
    #    moyenne de deux ratios n'est PAS égale au ratio des moyennes. Si on
    #    calculait cet écart après avoir moyenné montant_engage_ae et
    #    dotation_revisee_ae séparément (comme on le fait pour fusionner des
    #    doublons), on introduirait un écart artificiel qui n'existe pas dans
    #    les données sources (confirmé en pratique : jusqu'à 0.23 d'écart
    #    artificiel observé sur données réelles avec l'ancienne méthode, contre
    #    0.0001 réellement présent avant fusion). L'écart doit donc être figé
    #    ici, puis simplement moyenné comme n'importe quelle autre grandeur
    #    lors de la fusion des doublons — jamais recalculé après coup.
    masque_calculable = (
        df["dotation_revisee_ae"].notna() & df["montant_engage_ae"].notna() & (df["dotation_revisee_ae"] != 0)
    )
    df["ecart_taux_calcule"] = np.nan
    df.loc[masque_calculable, "ecart_taux_calcule"] = (
        df.loc[masque_calculable, "taux_EngagementAE"]
        - df.loc[masque_calculable, "montant_engage_ae"] / df.loc[masque_calculable, "dotation_revisee_ae"]
    ).abs()

    # 5) Doublons (mois, chapitre) : FUSIONNÉS PAR MOYENNE pour toutes les
    #    grandeurs numériques (taux, montants budgétaires ET écart déjà calculé).
    #    Pour le libellé, on conserve la première valeur non vide rencontrée.
    df = df.sort_values("date")
    n_lignes_avant_fusion = len(df)
    df = df.groupby(["date", "chapitre"], as_index=False).agg(
        taux_EngagementAE=("taux_EngagementAE", "mean"),
        ex_libelle_francais=("ex_libelle_francais", "first"),
        ex_millesime=("ex_millesime", "mean"),
        dotation_revisee_ae=("dotation_revisee_ae", "mean"),
        montant_engage_ae=("montant_engage_ae", "mean"),
        ecart_taux_calcule=("ecart_taux_calcule", "mean"),
    )
    n_doublons_fusionnes = n_lignes_avant_fusion - len(df)
    if n_doublons_fusionnes > 0:
        logger.info(
            "nettoyer_et_preparer: %d doublon(s) fusionné(s) par moyenne (même mois + même chapitre).",
            n_doublons_fusionnes,
        )

    df["chapitre"] = df["chapitre"].astype(int)

    # 6) Tri chronologique strict PAR CHAPITRE (jamais global uniquement)
    df = df.sort_values(["chapitre", "date"]).reset_index(drop=True)

    # 7) Features temporelles
    df["annee"] = df["date"].dt.year
    df["mois"] = df["date"].dt.month
    df["trimestre"] = df["date"].dt.quarter

    date_min = df["date"].min()
    df["trend_index"] = (
        (df["date"].dt.year - date_min.year) * 12 + (df["date"].dt.month - date_min.month)
    )

    # 8) Lags STRICTEMENT par chapitre, ET STRICTEMENT par distance calendaire
    #    réelle — UNIQUEMENT sur le taux (jamais sur les montants budgétaires,
    #    qui ne servent pas de variable explicative).
    #
    #    POINT CRITIQUE (découvert en testant sur des données réelles où de
    #    nombreux chapitres n'ont pas une observation tous les mois — jusqu'à
    #    90% de mois manquants pour certains) : un simple groupby().shift(1)
    #    prend la LIGNE précédente, pas le MOIS CALENDAIRE précédent. Si un
    #    chapitre a un trou (ex: rien en mars/avril), shift(1) donnerait à la
    #    ligne de mai la valeur de février en la faisant passer pour "le mois
    #    dernier" — c'est faux et fausse silencieusement l'entraînement.
    #
    #    Solution : pour chaque chapitre, on reconstruit une grille mensuelle
    #    COMPLÈTE (y compris les mois sans observation, mis à NaN), on calcule
    #    les lags sur cette grille (donc alignés sur de vrais mois calendaires,
    #    avec NaN si le mois requis manque réellement), puis on ne conserve que
    #    les lignes correspondant à des observations réellement présentes dans
    #    le fichier source (jamais de ligne fabriquée dans le résultat final).
    df = df.sort_values(["chapitre", "date"])

    blocs_par_chapitre = []
    for chapitre, groupe in df.groupby("chapitre"):
        groupe = groupe.set_index("date").sort_index()
        grille_complete = pd.date_range(groupe.index.min(), groupe.index.max(), freq="MS")
        serie_reindexee = groupe["taux_EngagementAE"].reindex(grille_complete)

        lags_sur_grille = pd.DataFrame(index=grille_complete)
        for lag in LAG_PERIODS:
            lags_sur_grille[f"lag_{lag}"] = serie_reindexee.shift(lag)

        # On ne garde que les lags aux dates où une observation existe réellement.
        lags_observes = lags_sur_grille.loc[groupe.index]
        bloc = groupe.copy()
        for lag in LAG_PERIODS:
            bloc[f"lag_{lag}"] = lags_observes[f"lag_{lag}"].values
        blocs_par_chapitre.append(bloc.reset_index())

    df = pd.concat(blocs_par_chapitre, ignore_index=True)
    df = df.sort_values(["chapitre", "date"]).reset_index(drop=True)
    return df


def reindexer_mensuel(df_chapitre: pd.DataFrame, colonne_valeur: str = "taux_EngagementAE") -> pd.Series:
    """Reconstruit la série d'UN chapitre sur une grille mensuelle calendaire
    COMPLÈTE (fréquence 'MS'), en laissant `NaN` aux mois réellement absents
    des données sources.

    Utilitaire partagé par ARIMA et LSTM (en plus du calcul des lags déjà
    corrigé ci-dessus), pour que ces deux modèles respectent eux aussi la
    distance calendaire réelle entre observations plutôt que de traiter les
    lignes disponibles comme si elles étaient mensuelles consécutives —
    hypothèse fausse sur des données réelles où certains chapitres n'ont
    qu'une observation tous les 3 à 10 mois.

    `df_chapitre` doit déjà être filtré sur un seul chapitre et contenir une
    colonne `date`. Retourne une Series indexée par date (freq='MS'), avec
    des `NaN` explicites aux mois manquants — ne fabrique jamais de valeur.
    """
    serie = df_chapitre.set_index("date")[colonne_valeur].sort_index()
    grille_complete = pd.date_range(serie.index.min(), serie.index.max(), freq="MS")
    return serie.reindex(grille_complete)


def get_feature_columns() -> list[str]:
    """Liste des colonnes explicatives utilisées par les modèles tabulaires (XGBoost/LightGBM).

    IMPORTANT — ANTI-FUITE DE DONNÉES :
    - taux_EngagementAE n'apparaît jamais ici : c'est la cible, pas une feature.
    - dotation_revisee_ae et montant_engage_ae n'apparaissent JAMAIS ici : puisque
      taux_EngagementAE = montant_engage_ae / dotation_revisee_ae, les utiliser comme
      variables explicatives donnerait au modèle un accès déguisé à la réponse
      (fuite de données), rendant les métriques artificiellement excellentes mais
      la prévision future inexploitable (ces valeurs futures ne sont pas connues
      à l'avance — ce sont précisément elles que le taux futur dépend).
    - ex_libelle_francais n'apparaît pas ici (texte libre à haute cardinalité,
      encodage non pertinent pour ce volume de données).
    - ex_millesime N'EST PAS inclus par défaut : sa correspondance avec l'année
      civile n'est pas garantie constante sur tous les jeux de données (voir
      analyser_fichier -> coherence_exercice_budgetaire). L'inclure sans cette
      garantie risquerait d'introduire une variable non fiable en prévision future.
    """
    return ["chapitre", "annee", "mois", "trimestre", "trend_index"] + [
        f"lag_{lag}" for lag in LAG_PERIODS
    ]

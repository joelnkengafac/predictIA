# Plateforme intelligente de prévision du taux d'engagement des AE — DGB / MINFI

Application Django complète permettant à la Direction Générale du Budget de
consulter, analyser et prévoir le taux mensuel d'engagement des Autorisations
d'Engagement (AE), via quatre modèles de Machine Learning (XGBoost, LightGBM,
LSTM, ARIMA).

## 1. Installation

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Créez votre fichier `.env` à partir de l'exemple fourni :

```bash
cp .env.example .env
```

Puis renseignez au minimum :
- `DJANGO_SECRET_KEY` (générez-en une nouvelle, jamais celle d'exemple)
- `DB_*` (identifiants PostgreSQL)
- `GOOGLE_OAUTH_CLIENT_ID` / `GOOGLE_OAUTH_CLIENT_SECRET` (si l'auth Google est utilisée)

### Base de données PostgreSQL

```sql
CREATE DATABASE dgb_ae_db;
CREATE USER dgb_ae_user WITH PASSWORD 'votre_mot_de_passe';
GRANT ALL PRIVILEGES ON DATABASE dgb_ae_db TO dgb_ae_user;
```

> Pour un essai rapide sans PostgreSQL, réglez dans `.env` :
> `DB_ENGINE=django.db.backends.sqlite3` et `DB_NAME=db.sqlite3`.

### Migrations et compte administrateur

```bash
python manage.py migrate
python manage.py createsuperuser
```

Lors de la création, définissez le rôle `ADMIN` via l'admin Django
(`/admin/`) sur ce compte si le champ n'est pas proposé par défaut.

### Lancement (développement)

```bash
python manage.py runserver
```

Puis ouvrez `http://127.0.0.1:8000/`.

## 2. Structure du projet

```
config/          Réglages Django, URLs racines
accounts/        Utilisateur custom, rôles, auth, gestion des comptes
core/            Accueil, journal d'activité, pages d'erreur, navigation
datasets/        Import CSV, table des observations
forecasting/     Pipeline ML (services/) + entraînement/comparaison des modèles
predictions/     Génération et historique des prévisions futures
dashboard/       Redirection par rôle + 3 tableaux de bord
templates/       Tous les gabarits HTML (Bootstrap 5 + Chart.js)
static/          CSS (thème vert citron/vert doré) et JS
```

Le cœur data-science se trouve dans `forecasting/services/` :
- `preprocessing.py` — validation, nettoyage, lags par chapitre
- `split.py` — séparation chronologique train/test
- `model_xgboost.py`, `model_lightgbm.py`, `model_lstm.py`, `model_arima.py`
- `metrics.py` — MAE, RMSE, R², MAPE robuste + sélection du meilleur modèle
- `pipeline.py` — orchestrateur appelé depuis les vues Django

## 3. Format du fichier importé attendu (CSV ou Excel .xlsx)

Deux formats sont acceptés, détectés automatiquement à l'import :

**Format simplifié (historique, 3 colonnes)** :
```
Mois_EngagementAE,chapitre,taux_EngagementAE
01-2020,1,0.125
02-2020,1,0.138
```

**Format complet (7 colonnes)** :
```
exLibelleFrancais;exMillesime;chapitre;DotationReviseAE;montantEngageAE;Mois_EngagementAE;taux_EngagementAE_mensuel
BUDGET 2017;51;20;38635742857;66020000;01-2017;0,0017
```

Le séparateur (`,` ou `;`) et la convention décimale (`.` ou `,`) sont détectés
automatiquement — les exports Excel français (point-virgule + virgule
décimale) sont pris en charge nativement.

**Important — anti-fuite de données** : `DotationReviseAE` et
`montantEngageAE` ne sont jamais utilisées comme variables explicatives des
modèles (puisque `taux = montantEngageAE / DotationReviseAE`, les utiliser
donnerait la réponse au modèle). Elles sont conservées uniquement pour
stockage, affichage et vérification de cohérence du taux fourni.

**Important — distance calendaire réelle** : si un chapitre a des mois
manquants (fréquent en pratique — jusqu'à 90% de mois manquants observés sur
certains chapitres réels), les variables retardées (lags), ARIMA et LSTM
respectent strictement le vrai calendrier plutôt que de traiter les lignes
disponibles comme mensuelles consécutives. Voir
`forecasting/services/preprocessing.py::reindexer_mensuel`.

## 4. Diagnostic statistique (ADF / ACF / PACF)

Accessible depuis le dashboard Analyste (`/modeles/diagnostic/`), ce module
affiche pour un chapitre donné :
- le test de stationnarité ADF (statistique, p-value, conclusion) ;
- les graphiques ACF et PACF avec seuil de significativité ;
- la couverture mensuelle réelle du chapitre (avertissement si trop de mois manquants).

Sert à justifier objectivement les choix de modélisation ARIMA plutôt que de
laisser la sélection automatique des ordres (p, d, q) agir comme une boîte noire.

## 5. Assistant IA (interprétation des prévisions)

Le Décideur (et désormais l'Analyste — voir §6) dispose d'un chat
contextualisé sous chaque prévision générée
(`predictions/services/grok_service.py`), basé sur l'API officielle **xAI
(Grok)**, compatible OpenAI. Pour l'activer :
```
XAI_API_KEY=xai-votre-cle
XAI_API_URL=https://api.x.ai/v1/chat/completions
XAI_MODEL=grok-4-latest
```
Limité à 20 questions/heure/utilisateur par défaut (configurable via
`ASSISTANT_IA_LIMITE_PAR_HEURE`).

## 6. Rôles et accès

| Rôle          | Accès |
|---------------|-------|
| Administrateur | Tout, y compris gestion des utilisateurs et journal d'activité |
| Analyste       | Import de données, entraînement, comparaison, prévisions, résultats, assistant IA |
| Décideur       | Consultation des prévisions/résultats/comparaison (lecture) et assistant IA — pas d'import ni d'entraînement |

Voir `accounts/decorators.py` pour l'implémentation serveur (jamais une
simple restriction visuelle) et `core/context_processors.py` pour le menu
affiché à chaque rôle.

## 7. Points d'attention pour la mise en production

- Passez `DJANGO_DEBUG=False` et configurez `DJANGO_ALLOWED_HOSTS` avec votre domaine réel.
- Servez les fichiers statiques via `collectstatic` + un serveur web (nginx) ou `whitenoise`.
- Le cache des modèles ML entraînés est actuellement en mémoire process
  (`forecasting/views._CACHE_ARTEFACTS`) pour permettre la génération immédiate
  de prévisions sans ré-entraînement. En production avec plusieurs workers/process,
  envisagez un stockage partagé (Redis, fichier pickle sur disque partagé, ou
  relance systématique depuis `SessionEntrainement.artefacts_pickle`).
- Le LSTM peut prendre plusieurs minutes à entraîner selon le volume de données ;
  pour une volumétrie importante, envisagez de déporter l'entraînement vers
  une tâche asynchrone (Celery) plutôt que de bloquer la requête HTTP.

## 8. Tests réalisés

Le pipeline a été testé de bout en bout avec un jeu de données synthétique
(5 chapitres, 7 ans d'historique, saisonnalité + tendance) via le flux
applicatif réel (import CSV → entraînement → comparaison → génération de
prévisions), avec des résultats cohérents (R² du meilleur modèle ≈ 0.88).
Toutes les URLs nommées ont été vérifiées (aucun NoReverseMatch), et le
contrôle d'accès par rôle a été validé (200/302/403 attendus selon les cas).

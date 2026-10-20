# Onboarding : du skill installé à la première collecte

À dérouler quand `~/Documents/jobsearch/config.json` n'existe pas, quand un script
répond « config encore vierge » ou « lance init », ou quand l'utilisateur dit qu'il
démarre. Compte 15 à 20 minutes, dont l'essentiel pour l'entretien. Chaque étape est
idempotente : on peut reprendre au milieu.

```bash
JS=~/.claude/skills/jobsearch/scripts
python3 $JS/init.py --check      # où en est-on ? (code retour 0 = prêt)
```

## Dépendances

| Outil | Pourquoi | Installation |
|---|---|---|
| `python3` ≥ 3.10 | tous les scripts | paquet système (`python3 --version`) |
| `requests` | appels HTTP des sources | `pip install --user requests`, ou rien si l'on passe par `uv run` |
| `uv` | installe `python-jobspy` à la volée pour LinkedIn et Indeed | `curl -LsSf https://astral.sh/uv/install.sh \| sh` (voir docs.astral.sh/uv) |
| `python-jobspy` | source `jobspy` (LinkedIn, Indeed) | automatique avec `uv run $JS/run.py` |
| skill **cv** | produit `~/Documents/cv/cv-master.md`, base du profil | même dépôt que ce skill |
| skill **candidature** | envoi des candidatures et fiches récap | même dépôt que ce skill |

`init.py` n'utilise que la bibliothèque standard : il marche avant toute installation.
Sans `uv`, lancer `python3 $JS/run.py --no-scrape` : tout fonctionne sauf LinkedIn et Indeed.
Aucune clé API n'est obligatoire : les sources sans clé couvrent déjà WTTJ, APEC,
Free-Work, les remote boards et les pages carrières.

## 1. Installer les fichiers

```bash
python3 $JS/init.py
```

Crée `~/Documents/jobsearch/{review,offres,candidatures}/`, `config.json` et
`profile.json` (modèles vierges, commentés par leurs champs `_doc`) et
`~/.config/jobsearch/.env` (chmod 600, noms de variables sans valeur). Ne remplace
jamais un fichier existant.

## 2. Vérifier le CV maître

Le profil de score et la revue des offres s'appuient sur `~/Documents/cv/cv-master.md`.
`init.py --check` dit s'il est absent, presque vide ou encore plein de marqueurs
« À REMPLIR ». Dans ce cas, **arrête l'onboarding ici** et passe par le skill **cv** en
mode premier lancement ; reviens ensuite à l'étape 3. Ne dérive jamais profile.json
d'un CV incomplet : le classement serait faux dès le départ.

## 3. Entretien

Court, une question à la fois, avec une proposition par défaut quand c'est possible.
Lis d'abord le CV maître : il répond souvent déjà aux questions 6 et 7 (à faire confirmer).

1. **Domicile** : commune (et code postal s'il existe des homonymes).
2. **Zone acceptée pour le présentiel ou l'hybride** : « Jusqu'où es-tu prêt à aller au
   bureau, et comment (voiture, train, vélo) ? » Traduis la réponse en lieux concrets,
   puis fais valider la liste : une agglomération (un cercle de 10 à 20 km), un
   département entier, ou un axe de train (un cercle de 4 à 8 km autour de chaque gare
   desservie, en excluant les villes proches à vol d'oiseau mais mal reliées).
3. **Jours sur site maximum** par semaine dans cette zone (5 = peu importe).
4. **Remote** : le full remote est-il souhaité ? Depuis quel pays doit-il être ouvert
   (France par défaut) ? Une offre « remote Europe » sans mention de la France convient-elle ?
5. **Contrats** : CDI, freelance / portage, CDD, alternance… (on garde `unknown` pour ne
   pas perdre les annonces muettes).
6. **Métiers visés** : 2 ou 3 intitulés, la spécialité qui compte le plus (stack, outil,
   domaine), et ce qui est moins pertinent ou à éviter.
7. **Salaire** : cible et minimum, en brut annuel (et TJM si freelance). Le minimum n'est
   jamais un filtre : il baisse seulement le score d'une offre qui affiche moins.
8. **ESN / régie** acceptées ?
9. Optionnel : LinkedIn / Indeed (plus lent, ~10 min par collecte) ? Entreprises précises à suivre ?

## 4. Remplir config.json

| Réponse | Clés |
|---|---|
| Domicile | `home.city`, `home.postcode` |
| Zone | `onsite.zone` (cercles `{"name", "city", "radius_km"}`), `onsite.zone_departments`, `onsite.zone_postcodes`, `onsite.zone_patterns` |
| Jours sur site | `onsite.max_days_on_site` (0 = aucun présentiel) |
| Remote | `remote.accepted`, `remote.countries`, `remote.scope_patterns` (ajouter `"\\beurope\\b"` si Europe convient) |
| Où chercher | `search_areas` : 1 à 3 lieux qui couvrent la zone, rayon 25-40 km (un appel par lieu, par requête et par plateforme : rester sobre) |
| Contrats | `contracts_allowed` |
| Métiers | `queries.fr` (4 à 8 intitulés tels qu'écrits dans les annonces, le plus important d'abord : certaines sources n'en prennent que 2 ou 3), `queries.en` (variantes anglaises), `queries.freework` (mots courts, métiers IT seulement) |
| Tri des flux | `prefilter.title` (le métier dans un titre), `prefilter.title_exclude` (faux positifs), `prefilter.stack` / `stack_text` (spécialité) ; regex en minuscules sans accents |
| Salaire | `salary_target.year`, `.day`, `.min_year`, `.min_day` |
| ESN | `esn_ok` |
| LinkedIn / Indeed | `scrape` |
| Entreprises | `ats_companies` (méthode : `references/ats-companies.md`) |

Puis complète les coordonnées des lieux (geo.api.gouv.fr, sans clé) et contrôle :

```bash
python3 $JS/init.py --geocode    # ajoute lat/lon, code postal, INSEE, département, région
python3 $JS/init.py --check
```

Métier hors développement : les remote boards (Remotive, Remote OK, We Work Remotely,
Jobicy, HN) et Free-Work sont orientés tech. Règle `jobicy_industry` et
`weworkremotely_feeds` si une catégorie existe pour le métier, sinon ajoute ces sources à
`sources_disabled`. France Travail, APEC, WTTJ, LinkedIn, Indeed, Adzuna et Google Jobs
couvrent tous les métiers.

### Exemple (fictif) : développeur backend à Nantes, remote France accepté

```json
{
  "home": {"city": "Nantes", "postcode": "44000"},
  "onsite": {"max_days_on_site": 3,
             "zone": [{"name": "Nantes agglo", "city": "Nantes", "radius_km": 15}],
             "zone_departments": [], "zone_postcodes": [], "zone_patterns": []},
  "remote": {"accepted": true, "countries": ["FR"],
             "scope_patterns": ["\\bfran(ce|cia)\\b", "\\bfrench\\b", "\\bfr\\b"]},
  "search_areas": [{"name": "Nantes", "city": "Nantes", "radius_km": 30}],
  "queries": {"fr": ["développeur backend python", "développeur python", "ingénieur backend"],
              "en": ["backend engineer", "python developer"],
              "freework": ["python", "django"]},
  "prefilter": {"title": ["back[ -]?end|backend|python|developpeur|developer|engineer|ingenieur|software"],
                "title_exclude": ["sales|business develop|recruit|marketing|account"],
                "stack": ["python|django|fastapi|back[ -]?end|backend"],
                "stack_text": ["\\bpython\\b|django|fastapi"]},
  "contracts_allowed": ["cdi", "freelance", "unknown"],
  "salary_target": {"year": 50000, "day": 450, "min_year": 40000, "min_day": null},
  "esn_ok": true
}
```

Les autres clés gardent les valeurs du modèle. Variante « chef de projet digital à
Bordeaux, 2 jours sur site max, pas de remote » : `onsite.max_days_on_site: 2`,
`remote.accepted: false`, `queries.fr: ["chef de projet digital", "chef de projet web",
"product owner"]`, `prefilter.title: ["chef de projet|project manager|product owner"]`,
remote boards et Free-Work dans `sources_disabled`.

## 5. Dériver profile.json du CV maître

Relis `~/Documents/cv/cv-master.md` et écris `~/Documents/jobsearch/profile.json`
(le modèle `_doc` rappelle le format ; motifs en minuscules sans accents) :

- `roles` : un rôle par métier visé, reconnu dans le titre. 40 points pour la cible exacte,
  20 à 30 pour un voisin, 10 à 15 pour un titre générique du domaine. `needs` sert quand un
  titre ne suffit pas (« full stack » sans la stack du CV → `points_if_missing`).
- `skills` : chaque compétence du CV qui peut apparaître dans une annonce, avec un poids
  qui suit les **preuves** du CV : 5-6 pour ce qui est exercé en production et au cœur
  du profil, 3-4 pour le solide, 1-2 pour le secondaire. Plafond `skills_cap` (35).
- `penalties` : stack principale concurrente, poste junior pour un profil senior, métiers
  voisins non voulus (chacun avec `unless` / `unless_title` pour ne pas pénaliser à tort).
- `experience_years` : années d'expérience pertinentes.

Montre le résultat à l'utilisateur en 5 lignes (métiers, 5 compétences les plus lourdes,
pénalités) et ajuste. Après la première collecte, regarde le détail du pré-score des 10
premières offres dans le rapport : si le classement surprend, corrige les poids puis
`run.py --rescore`.

## 6. Clés API optionnelles

Liste-les avec `init.py --check` (état présent / absent, noms seulement) :

| Variables | Plateforme | Inscription | Note |
|---|---|---|---|
| FRANCETRAVAIL_CLIENT_ID, FRANCETRAVAIL_CLIENT_SECRET | France Travail | https://francetravail.io/data/api/offres-emploi | créer une application abonnée à « API Offres d'emploi v2 » ; le plus gros volume français |
| ADZUNA_APP_ID, ADZUNA_APP_KEY | Adzuna | https://developer.adzuna.com/signup | gratuit |
| SERPAPI_KEY | Google Jobs (SerpApi) | https://serpapi.com/users/sign_up | 250 recherches/mois gratuites |
| JOOBLE_API_KEY | Jooble | https://jooble.org/api/about | 500 requêtes à vie ; parfois bloqué par Cloudflare |
| CAREERJET_API_KEY | Careerjet | https://www.careerjet.com/partners/register/as-publisher | compte éditeur |

**Ne demande jamais la valeur d'une clé dans le chat et n'affiche jamais `.env`.**
Donne le lien et le nom de la variable ; l'utilisateur ouvre lui-même
`~/.config/jobsearch/.env` et colle la clé après le `=`. Une source sans clé est
simplement sautée (`run.py --list` dit pourquoi).

## 7. Première collecte

```bash
python3 $JS/init.py --check                  # doit finir par « Prêt »
python3 $JS/run.py --no-scrape               # ~1 min : vérifie que tout tourne
uv run $JS/run.py --sources jobspy           # LinkedIn / Indeed, ~10 min, en arrière-plan
```

Puis revue de la file (`references/scoring.md`) et présentation du top (SKILL.md).
Si presque tout est exclu, lis `jobs.py stats` : « hors zone » massif = zone trop étroite
ou `search_areas` trop larges ; « remote hors France » massif = normal sur les remote boards.

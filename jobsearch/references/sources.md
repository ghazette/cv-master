# Sources : état, quotas, points fragiles

À lire quand une source est en erreur (`run.py --list`) ou ramène un volume anormal.
Chaque module vit dans `scripts/sources/<nom>.py` et se teste seul :
`uv run scripts/run.py --sources <nom> --force`.

État au 15/09/2026. « T » = testé en live ce jour-là, sur un profil développeur (les volumes
dépendent des requêtes et de la zone).

Aucune source ne code de lieu ni de métier : les familles géographiques partent de
`search_areas` (commune, coordonnées, INSEE, département, région, complétés par
`init.py --geocode`), les familles remote ne tournent que si `remote.accepted`, et les
sources qui ramènent un flux entier (remote boards, ATS, HN, Codeur) trient avec
`prefilter` (ou, à défaut, les mots des requêtes).

## Sans clé

| NAME | Plateforme | Accès | Délai mini | Volume test | Points fragiles |
|---|---|---|---|---|---|
| wttj | Welcome to the Jungle | Algolia public (clé relue sur `/api/env`, fallback codé) | 4 h | T 137 | Clé/app Algolia qui change ; index `wttj_jobs_production_fr` codé en dur ; description partielle (résumé + missions + profil) |
| freework | Free-Work | JSON `/api/job_postings` (Hydra, non documenté) | 4 h | T 73 | Métiers IT seulement ; recherche = ET entre les mots → requêtes courtes dans `queries.freework` ; `q` sans effet ; filtre de date ignoré (âge filtré côté client) ; clé de lieu = slug de la région du lieu de recherche (forçable par `freework_location`) |
| apec | APEC | POST `/cms/webservices/rechercheOffre` (non documenté) | 12 h | T 163 | Champ inconnu → 500 ; id de commune résolu par `lieuautocomplete` (code postal du lieu), repli sur le département ; détail d'offre bloqué par DataDome → description ≈ 280 car. ; pas de freelance (CDI, et CDD si accepté) |
| jobgether | Jobgether | API documentée `/api/v1/jobs` | 12 h | T 52 | Tout est full remote ; filtres hybrides/villes sans effet ; description lue page par page (≤ 80) ; salaires USD ignorés |
| himalayas | Himalayas | JSON `/jobs/api/search?country=FR` | 6 h | T 110 | Pas de tri par date, bruit (AI Sales…) ; `remote_scope` = liste de pays (peut en lister 150) |
| jobicy | Jobicy | JSON `/api/v2/remote-jobs?geo=france` | 1 h | T 50 | 1 appel/h max ; `geo=france` renvoie aussi Europe/EMEA/Anywhere ; catégorie `jobicy_industry` (défaut `dev`) |
| remotive | Remotive | JSON `/api/remote-jobs` | 6 h | T 16 bruts | API publique figée à ~16 offres quelle que soit la catégorie ; 4 appels/jour max ; offres décalées de 24 h |
| remoteok | Remote OK | JSON `/api` | 6 h | T 3 retenues / 99 | Tags peu fiables, préfiltre strict ; mojibake réparé ; lien retour obligatoire (on garde l'URL Remote OK) |
| weworkremotely | We Work Remotely | RSS par catégorie | 6 h | T 29 | Surtout US ; offres anciennes dans les flux (filtrées par âge) ; flux « programmation » par défaut, `weworkremotely_feeds` pour un autre métier |
| hn_hiring | HN « Who is hiring » | hn.algolia.com | 24 h | T 50 | Parsing heuristique de la 1re ligne ; quasi jamais de poste ouvert en France |
| codeur | Codeur.com | RSS global | 2 h | T 12 | Missions freelance seulement (sautée si `freelance` n'est pas accepté) ; flux ≈ 24 h de projets : collecter au moins chaque jour ; entreprise toujours vide ; petits projets bruités |

## Avec clé (`~/.config/jobsearch/.env`)

Écrits d'après la doc officielle, **pas encore testés avec une vraie clé**. Au premier run
avec clé, vérifier le volume et le remplissage des champs, puis mettre cette section à jour.

| NAME | Plateforme | Variables | Quota | Délai mini | À valider avec la clé |
|---|---|---|---|---|---|
| francetravail | France Travail Offres v2 | FRANCETRAVAIL_CLIENT_ID, FRANCETRAVAIL_CLIENT_SECRET | 10 appels/s | 6 h | Valeurs de `publieeDepuis` ; ponctuation dans motsCles (« node.js » : repli sans ponctuation sur 400) ; `commune` = INSEE du lieu + `distance` = son rayon, repli sur `departement` ; pas de champ télétravail (détection texte) |
| adzuna | Adzuna | ADZUNA_APP_ID, ADZUNA_APP_KEY | 250/jour, 2 500/mois | 12 h | Salaires annuels ; contrat « contract » ambigu → unknown |
| serpapi_gjobs | Google Jobs via SerpApi | SERPAPI_KEY | 250 recherches/mois | 24 h | Libellés `schedule_type` en français ; lit le solde (account.json, gratuit) avant de chercher ; ≤ 6 recherches/run |
| jooble | Jooble | JOOBLE_API_KEY | **500 requêtes à vie** | 72 h | Cloudflare 403 depuis l'IP locale même avant la clé : peut rester inutilisable ; 2 requêtes/run |
| careerjet | Careerjet v4 | CAREERJET_API_KEY (+ CAREERJET_USER_IP, CAREERJET_REFERER optionnels) | non documenté | 12 h | Locale `fr_FR` ; `user_ip` 127.0.0.1 accepté ? ; pas d'id → empreinte titre+entreprise+lieu |

## Pages carrières d'entreprises (sans clé)

| NAME | Accès | Délai mini | Volume test | Points fragiles |
|---|---|---|---|---|
| ats | JSON publics Lever (+ hôte EU), Greenhouse, Ashby, Workable (v3 POST), Recruitee, SmartRecruiters ; entreprises dans `ats_companies` (slug seul ou `{"slug","name"}`) | 12 h | T 385 offres / 52 entreprises en 164 s | Workable bloque l'IP (429) après ~80 appels rapprochés ; Greenhouse sans champ remote et pays parfois faux ; `isRemote` Ashby vrai aussi pour l'hybride (seul `workplaceType` compte) ; SmartRecruiters = 1 appel détail par offre ; âge filtré sur `ats_max_age_days` (défaut 90 j, la date ATS est celle de 1re publication) |

Liste et méthode de vérification des slugs : `references/ats-companies.md`. Un slug qui répond
404 est signalé dans les logs (« slug à corriger dans la config »).

## Scraping (config `scrape: true`)

| NAME | Accès | Délai mini | Volume test | Points fragiles |
|---|---|---|---|---|
| jobspy | python-jobspy 1.1.82 (`uv run` l'installe) : LinkedIn + Indeed en mode invité | 12 h | T 265 offres en ~8 min | Le plus lent de la collecte (une page par offre LinkedIn) ; remote toujours `unknown` (détection texte) ; distance en miles (15 ≈ 24 km) ; Indeed ignore le filtre remote si `hours_old` est passé (âge filtré localement) ; site coupé après 4 appels vides d'affilée ; Glassdoor (400/403) et Google (0 résultat) désactivés, réactivables via `jobspy_sites` dans config.json |

Clés optionnelles de config.json non présentes par défaut : `jobspy_sites` (ex. `["linkedin", "indeed"]`),
`ats_max_age_days` (défaut 90), `jobicy_industry`, `weworkremotely_feeds`. Par lieu de
`search_areas` : `serpapi_location` (nom canonique SerpApi), `freework_location` (clé Free-Work).

## Pistes non branchées

HelloWork, Cadremploi, Meteojob, Leboncoin (scraping interdit par les CGU ou anti-bot : couverts
en partie par Google Jobs) ; LesJeudis, WeLoveDevs, RemoteFR, EU Remote Jobs (scraping HTML
simple, à ajouter si le volume manque) ; jobboards régionaux (French Tech locales, clusters
numériques : petits volumes) ; Malt, Crème de la Crème, Comet (aucun accès : alertes à régler
dans leurs apps).

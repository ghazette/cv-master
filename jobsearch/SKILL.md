---
name: jobsearch
description: Veille et recherche d'emploi automatisée pour l'utilisateur. Collecte les offres sur les plateformes françaises (France Travail, Welcome to the Jungle, Free-Work, APEC, LinkedIn, Indeed, Google Jobs, Adzuna, remote boards, pages carrières Lever/Greenhouse/Ashby…), applique sa règle de lieu lue dans sa config (présentiel ou hybride seulement dans la zone qu'il accepte, sinon full remote ouvert depuis son pays), classe par score de matching avec son CV, et suit ses candidatures dans une page HTML. Au premier lancement, installe ses fichiers et mène un court entretien. Utilise ce skill dès que l'utilisateur veut chercher un job, voir les nouvelles offres, lancer la veille, parle de jobboards, LinkedIn/Indeed/WTTJ, de score d'offres, de suivi de candidatures (« j'ai postulé chez X », « écarte celle-là »), ou demande « quoi de neuf côté boulot », même sans dire « jobsearch ». Pour adapter le CV ou la lettre à une offre, passe la main au skill cv ; pour envoyer une candidature, au skill candidature.
---

# Recherche d'emploi : collecte, filtre, score, suivi

Ce skill sert une personne à la fois. Ses règles (domicile, zone acceptée pour le
présentiel, jours sur site, remote, contrats, métiers, salaire) sortent d'un entretien
avec elle et sont **lues dans `~/Documents/jobsearch/config.json`** ; ses compétences
et leurs poids, dans `profile.json`, dérivé de son CV maître. Les respecter à la lettre
est ce qui rend le classement utile. Rien de personnel n'est écrit dans le code du skill.

Prérequis : `python3` ≥ 3.10 avec `requests`, et `uv` (installe `python-jobspy` pour
LinkedIn et Indeed). Sans `uv`, tout marche sauf ces deux sites. Détail et installation :
`references/onboarding.md`, section Dépendances.

```bash
JS=~/.claude/skills/jobsearch/scripts
```

## Premier lancement (à vérifier avant tout le reste)

Si `~/Documents/jobsearch/config.json` n'existe pas, ou si un script répond « config
encore vierge » / « lance init », ne lance aucune collecte : déroule l'onboarding de
`references/onboarding.md`. En bref :

1. `python3 $JS/init.py` : crée les dossiers, `config.json` et `profile.json` (modèles
   vierges) et `~/.config/jobsearch/.env` (chmod 600). N'écrase jamais rien.
2. Vérifie que `~/Documents/cv/cv-master.md` existe et est rempli
   (`python3 $JS/init.py --check` le dit). Si `~/.claude/skills/cv/config.json`
   existe, le master est dans son `workspace` plutôt que dans `~/Documents/cv` :
   les scripts le résolvent seuls, fais de même pour les chemins `~/Documents/cv/`. Sinon, passe d'abord par le skill **cv**
   en mode premier lancement, puis reviens ici.
3. Entretien court, une question à la fois : domicile, zone acceptée pour le présentiel,
   jours sur site max, remote, contrats, métiers visés, salaire cible et minimum, ESN.
4. Remplis `config.json`, puis `python3 $JS/init.py --geocode` (coordonnées des lieux).
5. Dérive `profile.json` du CV maître (métiers, compétences, poids, pénalités).
6. Liste les clés API optionnelles avec leur lien d'inscription. **Ne demande jamais une
   clé dans le chat** : l'utilisateur édite `.env` lui-même.
7. `python3 $JS/init.py --check` doit dire « Prêt », puis première collecte (ci-dessous).

## Où vivent les choses

```
~/.claude/skills/jobsearch/          # le skill (code, ne pas y mettre de données)
├── scripts/init.py                  # premier lancement ; --check (quoi remplir) ; --geocode
├── scripts/run.py                   # collecte → filtre → score → historique → rapport
├── scripts/jobs.py                  # top, find, queue, import-review, show, status, offer, stats
├── scripts/report.py                # rapport HTML ; --serve pour enregistrer les statuts
├── scripts/recap.py                 # récap des candidatures envoyées ; --find, --check
├── scripts/config.py · filters.py · score.py · prefilter.py · db.py · common.py
├── scripts/sources/<nom>.py         # un module par plateforme
├── assets/  config.default.json · profile.default.json   # modèles neutres commentés (_doc)
└── references/  onboarding.md · scoring.md (barème de revue) · recap.md (fiche candidature)
                 · sources.md (état des sources) · ats-companies.md (pages carrières)

~/Documents/jobsearch/               # données de l'utilisateur
├── config.json      # domicile, zone, remote, lieux et requêtes de recherche, contrats, salaire…
├── profile.json     # poids du pré-score, dérivés du CV maître
├── jobs.db          # historique SQLite
├── rapport.html     # page de classement
├── candidatures.html, candidatures/   # fiches récap des candidatures
├── review/          # queue.json (à relire) + fichiers de revue horodatés
└── offres/          # offres exportées en markdown pour le skill cv

~/Documents/cv/cv-master.md          # CV maître (skill cv) : source de vérité du profil
~/.config/jobsearch/.env             # clés API (chmod 600)
```

Clés : ne jamais afficher le contenu de `.env`, ne jamais demander à l'utilisateur de coller
une clé dans le chat. S'il faut une clé, donner le lien d'inscription et le nom de la variable,
et le laisser éditer le fichier. Pour vérifier qu'une clé est présente : `run.py --list` ou
`init.py --check` (noms seulement).

## La règle de lieu (lue dans config.json)

- `onsite` : présentiel ou hybride accepté seulement si le bureau tombe dans la zone
  (cercles, départements, préfixes de code postal ou motifs) et sans dépasser
  `max_days_on_site` jours sur site par semaine. Rythme non précisé alors que la limite
  est inférieure à 5 → « à confirmer ».
- `remote` : hors zone, seul le full remote passe, et seulement s'il est ouvert depuis un
  pays de `remote.countries`. « Europe » ou « worldwide » ne suffit pas, sauf motif ajouté
  exprès dans `remote.scope_patterns`.
- `contracts_allowed` filtre ; `salary_target` n'est qu'un bonus (ou un malus sous le
  minimum), jamais un filtre ; `esn_ok` est appliqué à la revue.

## Lancer une recherche

```bash
uv run $JS/run.py            # 1 min sans LinkedIn/Indeed, ~10 min avec (uv installe python-jobspy)
```

Lance-le avec un timeout long (10 min) ou en arrière-plan : LinkedIn et Indeed (source `jobspy`)
représentent l'essentiel de la durée. La sortie donne, par source : offres ramenées,
nouvelles, nouvelles éligibles, doublons fusionnés, erreur éventuelle. Chaque source a un
délai minimal entre deux collectes (quotas : SerpApi 250/mois, Jooble 500 à vie, Remotive
4/jour…) ; les sources sautées sont listées avec la raison (clé absente, délai, désactivée).
N'utilise `--force` que sur une source précise et pour une bonne raison, jamais en boucle sur
SerpApi ou Jooble.

Options utiles : `--sources wttj,freework` · `--no-scrape` · `--rescore` (après avoir modifié
config.json ou profile.json, recalcule tout sans collecter) · `--list` (état et clés des sources).
Sans `uv` : `python3 $JS/run.py --no-scrape`.

## Relire le haut du panier

Le pré-score trie par mots-clés ; il ne sait pas lire. Après chaque collecte, relis les offres
de `~/Documents/jobsearch/review/queue.json` (les meilleures jamais relues, plus les offres
« à confirmer » dont le remote ou le rythme est ambigu) en suivant `references/scoring.md` :
lecture du CV maître, barème, vérification du lieu et du remote, format du fichier. Puis :

```bash
python3 $JS/jobs.py import-review ~/Documents/jobsearch/review/<AAAA-MM-JJ-HHMM>.json
```

Si la file dépasse une trentaine d'offres, répartis la lecture entre plusieurs sous-agents
(un lot par agent, chacun lit le CV maître, config.json et `scoring.md` et écrit son propre
fichier de revue) : chaque offre compte jusqu'à 6 000 caractères, les lire toutes dans le
fil principal le sature.

## Présenter le résultat

1. `python3 $JS/jobs.py top --n 15` : tableau markdown des éligibles, score en gras = relu.
2. En quelques lignes : combien de nouvelles offres éligibles, les 3 à 5 à regarder en premier
   et pourquoi (une phrase chacune), les sources en erreur s'il y en a.
3. Le chemin du rapport `~/Documents/jobsearch/rapport.html`. Propose de lancer
   `python3 $JS/report.py --serve` en arrière-plan : sur http://127.0.0.1:8765, les statuts
   et notes modifiés dans la page sont écrits dans l'historique (en `file://`, ils restent
   dans le navigateur).

## Suivi des candidatures

Quand l'utilisateur dit « j'ai postulé chez X », « écarte l'offre Y », « entretien jeudi chez Z » :
retrouve l'uid (`python3 $JS/jobs.py find "X"`, qui cherche dans l'entreprise, l'intitulé et le lieu),
puis `jobs.py status <uid> postule|entretien|refuse|ecarte|favori [--notes "…"]`. Le rapport se régénère.

« Adapte mon CV à l'offre jobsearch <uid> » (bouton du rapport) : `jobs.py offer <uid>` écrit
l'annonce et l'analyse dans `~/Documents/jobsearch/offres/…md`, puis utilise le skill **cv**
en mode offre avec ce fichier. Passe l'offre au statut `favori` si elle ne l'est pas.

« Envoie la candidature » : passe la main au skill **candidature**, qui gère le mandat
d'envoi, le navigateur et la fiche récap. Ce skill-ci n'envoie rien lui-même.

## Récap des candidatures

L'utilisateur doit pouvoir relire ce qui a été envoyé, surtout quand un recruteur rappelle
et qu'il ne sait plus qui c'est. Chaque dossier a sa fiche dans
`~/Documents/jobsearch/candidatures/<dossier>.json`, au format de `references/recap.md`.
Le skill **candidature** l'écrit après chaque envoi ; si l'utilisateur a postulé seul,
complète-la ici avec la même référence. Ensuite :

```bash
python3 $JS/jobs.py status <uid> postule      # régénère aussi candidatures.html
python3 $JS/recap.py --check
```

La page `~/Documents/jobsearch/candidatures.html` cherche par entreprise, intermédiaire,
client final, nom de contact ou numéro. Depuis le mobile : `report.py --serve --host 0.0.0.0`,
puis `http://<ip-du-pc>:8765/candidatures` sur le même wifi.
« C'est qui X ? » dans le terminal : `python3 $JS/recap.py --find "X"`. Quand l'utilisateur
raconte un appel ou un entretien, ajoute la ligne dans `suivi` et le contact dans `contacts`.

## Maintenance

- **Une source casse** (changement d'API, clé Algolia WTTJ, blocage) : `run.py --list` affiche
  la dernière erreur ; `references/sources.md` décrit chaque source et ses points fragiles.
  Corrige le module concerné et teste-le seul avec `run.py --sources <nom> --force`.
  Si c'est durable, ajoute le nom à `sources_disabled` dans config.json plutôt que de laisser
  une erreur à chaque run.
- **Trop d'offres hors sujet** : regarde `jobs.py stats` et le détail du pré-score dans le
  rapport, ajuste les requêtes ou le `prefilter` (config.json) ou les poids (profile.json),
  puis `--rescore`.
- **Offre exclue à tort** : l'onglet « Exclues » du rapport affiche la raison. Si c'est la
  zone, corrige `onsite` (un cercle, un département, un motif) ; si c'est la détection du
  remote ou des jours sur site, corrige les motifs de `filters.py` plutôt que d'élargir la règle.
- **Nouvelles entreprises à surveiller** : ajoute leur slug dans `ats_companies` (config.json) ;
  `references/ats-companies.md` explique comment trouver et vérifier un slug.
- **Le CV change** (nouvelle expérience, nouvelle techno) : mets à jour `profile.json` depuis
  `~/Documents/cv/cv-master.md`, puis `--rescore`.
- **L'utilisateur déménage ou change de cible** : refais les étapes 3 à 5 de l'onboarding
  sur les seules clés concernées, puis `--rescore`.

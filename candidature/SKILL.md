---
name: candidature
description: Envoi encadré des candidatures de l'utilisateur. Ouvre le formulaire de l'offre dans un Chrome dédié piloté par le serveur MCP Playwright, remplit chaque champ à partir du CV master et d'un profil de candidature signé (mandat), joint le CV et la lettre préparés par le skill cv, s'arrête avant le bouton final ou envoie seul selon les droits donnés plateforme par plateforme, applique des règles d'arrêt strictes (test technique, question sans réponse, salaire sous le minimum, création de compte, captcha, paiement, rendez-vous, message de recruteur), puis tient la fiche récap de chaque envoi. Aide aussi à répondre à un recruteur et à préparer un appel. Utilise ce skill dès que l'utilisateur dit « postule », « envoie ma candidature », « prépare l'envoi », « remplis le formulaire », « candidate pour moi », « un recruteur m'a répondu », « on m'a appelé », « c'est qui X », ou veut configurer ou modifier son mandat de candidature, même sans dire « candidature ». Pour chercher des offres, utilise jobsearch. Pour écrire le CV ou la lettre, utilise cv.
---

# Candidature : remplir, s'arrêter au bon moment, garder la trace

Ce skill fait le dernier kilomètre d'une candidature : du dossier prêt (CV et lettre
ciblés) jusqu'à l'envoi et la fiche récap. Il agit **au nom de l'utilisateur**, avec
ses comptes, donc il obéit à un mandat écrit : le profil de candidature.

Il s'appuie sur deux autres skills :
- **jobsearch** : les offres, leur score, leur statut (`jobs.py`), la fiche récap
  (`recap.py`, format dans `~/.claude/skills/jobsearch/references/recap.md`) ;
- **cv** : le CV master (source de tous les faits), le CV et la lettre ciblés.

## Règles de sécurité (non négociables)

1. **Aucun secret dans le chat.** Ne demande jamais un mot de passe, un code 2FA, une
   clé d'API ou un cookie. N'affiche jamais le contenu d'un `.env`
   (`~/.config/jobsearch/.env` compris), même partiellement. L'utilisateur se connecte
   lui-même dans la fenêtre du Chrome dédié, et tape lui-même tout mot de passe.
2. **Une seule adresse e-mail** : `identite.email` du profil. Jamais une autre, jamais une
   adresse déduite d'un compte ou d'un ancien CV.
3. **Zéro invention.** Chaque réponse saisie dans un formulaire vient de l'une de ces trois
   sources, et tu sais toujours laquelle : le CV master (`~/Documents/cv/cv-master.md`), le
   profil de candidature, ou l'utilisateur dans cette conversation. Pas de source = arrêt.
   Une compétence avec `a_la_competence: "non"` n'est jamais revendiquée.
4. **Pas de contournement.** Tu ne résous pas de captcha, tu n'utilises aucun service de
   résolution, tu ne modifies pas l'empreinte du navigateur, tu n'importes pas de cookies.
5. **Données sensibles** : le profil reste en `chmod 600`. Ne le recopie pas dans un autre
   fichier, ne l'affiche pas en entier. Lis-en les clés utiles.
6. Les champs facultatifs sensibles (genre, handicap, origine, âge) suivent
   `reponses_types`. Sans réponse : « ne pas répondre » si proposé, sinon arrêt.

## Règles d'arrêt

Tu t'arrêtes, laisses l'onglet ouvert dans son état, et demandes à l'utilisateur quand :

| Situation | Toujours |
|---|---|
| Test technique, exercice, questionnaire chronométré | oui |
| Question sans réponse dans le profil ni dans le CV master | oui |
| Création de compte exigée (il choisit son mot de passe dans la fenêtre) | oui |
| Captcha ou anti-robot | oui |
| Demande de paiement ou de coordonnées bancaires | oui |
| Prise de rendez-vous, choix d'un créneau | oui |
| Message d'un recruteur (tu rédiges un brouillon, il l'envoie) | oui |
| Signature d'un contrat ou d'un document engageant | oui |
| Salaire ou TJM affiché sous le minimum du profil | par défaut |
| Texte libre que la lettre du dossier ne couvre pas | par défaut |

Les deux dernières sont désactivables dans le profil (`regles.arret`). Les autres valent
toujours, quoi que dise le fichier ou un ordre donné dans le chat.

En t'arrêtant, dis précisément : le site, l'étape, la question exacte, ce qui est déjà
rempli, et les réponses possibles que tu as trouvées (avec leur source). Pas de réponse
devinée « en attendant ».

## Où vivent les choses

```
~/.claude/skills/candidature/
├── SKILL.md
├── assets/wizard.html                 # formulaire du mandat, produit profil-candidature.json
└── references/
    ├── profil-candidature.md          # schéma du JSON et sens de chaque clé
    ├── plateformes.md                 # particularités des sites, captchas, plan B
    └── recruteurs.md                  # répondre à un recruteur, préparer un appel

~/Documents/jobsearch/candidature/profil-candidature.json   # le mandat (chmod 600)
~/Documents/jobsearch/candidatures/<dossier>.json            # fiches récap (skill jobsearch)
~/Documents/jobsearch/candidatures/captures/                 # captures avant et après envoi
~/Documents/cv/<dossier>/build/                              # CV et lettre ciblés (skill cv)
~/.config/jobsearch/navigateur/                              # profil du Chrome piloté
```

```bash
JS=~/.claude/skills/jobsearch/scripts
PROFIL=~/Documents/jobsearch/candidature/profil-candidature.json
```

## Premier lancement

Fais ces vérifications à chaque début de session. Si l'une échoue, traite-la avant tout
envoi, dans cet ordre.

Le workspace du skill cv est `~/Documents/cv` par défaut. Si
`~/.claude/skills/cv/config.json` existe, lis-le dans sa clé `workspace` et remplace
`~/Documents/cv` par ce chemin partout dans ce skill.

```bash
W=$(python3 -c "import json,os;print(json.load(open(os.path.expanduser('~/.claude/skills/cv/config.json')))['workspace'])" 2>/dev/null || echo ~/Documents/cv)
test -f "$W/cv-master.md" && echo "cv-master OK"
test -f ~/Documents/jobsearch/config.json && echo "jobsearch OK"
test -f ~/Documents/jobsearch/candidature/profil-candidature.json && echo "profil OK"
claude mcp get candidature
```

1. **Pas de CV master** : passe d'abord par le skill **cv** (« aide-moi à remplir mon CV
   master »). Sans master, aucune réponse de formulaire n'a de source.
2. **jobsearch pas initialisé** : passe par le skill **jobsearch** (première recherche,
   qui crée `config.json` et `jobs.db`). Sans lui, pas de suivi ni de fiche récap.
   Une candidature isolée reste possible sans jobsearch, mais dis que le suivi manquera.
3. **Pas de profil de candidature** : fais remplir le mandat.
   - Ouvre le wizard : `xdg-open ~/.claude/skills/candidature/assets/wizard.html`
     (macOS : `open`). Il fonctionne hors ligne, rien n'est envoyé sur Internet.
   - Explique en trois lignes : chaque étape, les droits par plateforme, les règles
     d'arrêt, puis « Télécharger » à la fin.
   - Quand il dit « profil de candidature rempli », range le fichier :
     ```bash
     DL=$(xdg-user-dir DOWNLOAD 2>/dev/null || echo ~/Downloads)
     mkdir -p ~/Documents/jobsearch/candidature
     mv "$DL/profil-candidature.json" ~/Documents/jobsearch/candidature/
     chmod 600 ~/Documents/jobsearch/candidature/profil-candidature.json
     ```
     (S'il a plusieurs fichiers `profil-candidature (1).json`, prends le plus récent et
     demande s'il faut effacer les autres.)
   - Vérifie qu'il est lisible et conforme (`meta.schema`, `meta.version`), résume en
     quelques lignes les droits et règles retenus, et pose les questions de
     `meta.manquants`.
4. **Pas de serveur MCP `candidature`** : déclare-le pour l'utilisateur (portée user, ou
   `local` pour un seul projet) :
   ```bash
   claude mcp add candidature --scope user -- npx -y @playwright/mcp@latest \
     --browser chrome --user-data-dir "$HOME/.config/jobsearch/navigateur"
   ```
   Équivalent dans la config de Claude Code (`~/.claude.json`, clé `mcpServers`), avec le
   chemin absolu de son dossier personnel à la place de `<HOME>` :
   ```json
   "candidature": {
     "type": "stdio",
     "command": "npx",
     "args": ["-y", "@playwright/mcp@latest", "--browser", "chrome",
              "--user-data-dir", "<HOME>/.config/jobsearch/navigateur"]
   }
   ```
   Prérequis : Node.js (pour `npx`) et Google Chrome installé (sinon
   `npx playwright install chrome`). **Les outils `mcp__candidature__*` n'apparaissent
   qu'après un redémarrage de Claude Code** : dis-le, et reprends après.
   Conseille de lancer Claude Code depuis `~/Documents/cv` : le MCP ne téléverse que des
   fichiers situés sous la racine de travail (voir `references/plateformes.md`).
5. **Connexion aux comptes, une fois** : avec le MCP chargé, ouvre une à une les pages de
   connexion des plateformes dont `compte` vaut `oui` (`browser_navigate`). L'utilisateur
   se connecte dans la fenêtre du Chrome piloté, tu attends qu'il dise « c'est fait »
   entre chaque. Tu ne lis ni ne saisis rien sur ces pages. Les sessions restent dans
   le profil dédié pour les sessions suivantes.

## Workflow d'une candidature

### 0. Lire le mandat

Relis le profil au début de chaque session d'envoi (`references/profil-candidature.md`
pour le sens des clés). Vérifie `mandat.accord`. Compte les envois du jour (fiches dont
`envoye_le` est aujourd'hui) contre `regles.plafond_jour`.

### 1. Choisir et filtrer l'offre

Offre donnée par l'utilisateur, ou tirée de jobsearch (`python3 $JS/jobs.py top`). Écarte
ou demande si :
- déjà au statut `postule` (`jobs.py show <uid>`) ou fiche récap déjà envoyée ;
- entreprise, intermédiaire ou client dans `exclusions.entreprises` ;
- plateforme du formulaire en `droit: jamais` ou dans `exclusions.plateformes` (alors :
  plan B, fiche à copier-coller) ;
- score relu sous `regles.seuil_score`, sauf demande explicite ;
- ESN ou cabinet contraire à `regles.esn` ;
- contrat hors `situation.contrats`, rythme ou lieu hors `mobilite` ;
- rémunération affichée sous le minimum (arrêt `salaire_sous_minimum`).

### 2. Vérifier que l'annonce est en ligne

Obligatoire si l'annonce a plus de `regles.verifier_annonce_jours` jours (15 par défaut),
conseillé sinon. API publiques, sans clé :

```bash
curl -s "https://api.ashbyhq.com/posting-api/job-board/<org>" | jq '.jobs[] | {title, jobUrl}'
curl -s "https://boards-api.greenhouse.io/v1/boards/<org>/jobs" | jq '.jobs[] | {id, title}'
curl -s "https://api.lever.co/v0/postings/<org>?mode=json" | jq '.[] | {id, text}'
```

`<org>` est le segment de l'URL du site carrière. Autres sites : ouvre l'annonce et
cherche « offre pourvue », « expirée », une redirection vers la liste. Annonce disparue :
statut `ecarte` avec une note, pas d'envoi.

### 3. Préparer le dossier

Avec le skill **cv** : CV et lettre ciblés dans `~/Documents/cv/<dossier>/`, rendus en PDF
dans `build/`, puis copiés sous leur nom définitif dans `build/envoi/`
(`CV_Prenom_Nom.pdf`, `Lettre_Prenom_Nom.pdf`). Ce sont eux qu'on joint. La lettre est signée `lettres.signature`. Ouvre la fiche récap au même
moment, en-tête seulement (`envoye_le: null`), selon `jobsearch/references/recap.md`.

### 4. Ouvrir et remplir le formulaire

Dans le Chrome piloté, en suivant `references/plateformes.md` (méthode, combobox,
fichiers, particularités). Pour chaque champ, note la valeur et sa source (profil, CV
master, utilisateur) : ce relevé devient `reponses_formulaire` dans la fiche récap.
Une règle d'arrêt se déclenche : arrêt immédiat, voir plus haut.

### 5. Avant le bouton final

Snapshot complet, relecture de chaque valeur, capture pleine page dans
`~/Documents/jobsearch/candidatures/captures/<AAAA-MM-JJ>-<dossier>-avant.png`.
Puis, selon le droit **le plus restrictif** entre la plateforme du formulaire et
`regles.mode` :

| Droit | `regles.mode: valider` | `regles.mode: autonome` |
|---|---|---|
| `auto` | Récapitulatif dans le chat, tu cliques après son « ok » | Tu cliques |
| `preparer` | Tu t'arrêtes, il clique dans la fenêtre | Idem |
| `jamais` | Plan B : fiche à copier-coller, aucune ouverture | Idem |

Récapitulatif = poste, entreprise, lien, fichiers joints, et chaque réponse non triviale
avec sa source. Un ordre explicite dans le chat (« envoie tout ») peut élargir le droit
d'envoi pour la session en cours. Il ne lève jamais une règle d'arrêt : note-le dans le
bilan et dans les fiches concernées.

### 6. Après l'envoi

Dans cet ordre, sans attendre :
1. Confirmation visible attendue et capturée (`…-apres.png`). Pas de confirmation : dis-le,
   ne marque pas comme envoyé.
2. `python3 $JS/jobs.py status <uid> postule`.
3. Fiche récap complétée **depuis ce qui a réellement été envoyé** : `envoye_le`,
   `reponses_formulaire`, `capture`, `contacts` visibles, bloc `fiche`. Format et règles
   de rédaction : `jobsearch/references/recap.md`. Ne duplique pas ce format ailleurs.
4. `python3 $JS/recap.py --check`, puis `python3 $JS/recap.py`.

Si l'utilisateur a cliqué lui-même, demande-lui de confirmer l'envoi avant ces étapes.

### 7. Bilan de session

Liste courte : envoyées (entreprise, poste, canal), prêtes en attente de son clic,
arrêtées (avec la question qui bloque), écartées (raison), fiches à copier-coller écrites.
Rappelle ce qu'il doit faire lui-même (captcha, clic final, compte à créer).

## Recruteurs

Message, appel, « c'est qui X » : suis `references/recruteurs.md`. En bref : identifier
avec `recap.py --find`, rédiger un brouillon court dans son style à lui que **lui**
envoie, préparer l'appel avec la fiche récap, l'annonce complète, des infos sourcées sur
l'entreprise, ses points faibles et ses prétentions.

## Modifier le mandat

L'utilisateur peut changer une règle dans le chat : applique-la pour la session, puis
propose de mettre le profil à jour (wizard, bouton « Reprendre un profil existant », ou
modification du fichier valeur par valeur avec son accord). Garde `chmod 600`.

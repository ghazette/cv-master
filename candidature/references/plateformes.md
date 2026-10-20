# Plateformes et navigateur piloté

Constats de terrain sur les formulaires de candidature remplis avec le serveur MCP
Playwright `candidature` (outils `mcp__candidature__browser_*`). Les sites changent :
quand un constat ne tient plus, corrige ce fichier.

## Le navigateur piloté

- Un Chrome à profil dédié (`~/.config/jobsearch/navigateur`), séparé du navigateur
  habituel. Les sessions (WTTJ, LinkedIn, Free-Work, webmail…) y persistent entre deux
  lancements. **L'utilisateur s'y connecte lui-même**, tu ne vois ni ne demandes jamais
  ses identifiants.
- Un profil Chrome ne s'ouvre que dans un seul processus. Si l'utilisateur a lancé ce
  Chrome à la main pour se connecter, il doit le fermer avant que le MCP l'utilise, sinon
  le lancement échoue (profil verrouillé).
- N'importe jamais de cookies d'un autre navigateur. Certaines plateformes (LinkedIn en
  tête) détectent l'import et coupent la session : il faut alors se reconnecter à la main.
- **Fichiers à téléverser** : par défaut, le MCP n'accède qu'aux fichiers de la racine
  de travail de Claude Code. Lance Claude Code depuis `~/Documents/cv` (ou un parent) pour
  que les PDF de `~/Documents/cv/<dossier>/build/` soient accessibles. Sinon l'envoi de
  fichier est refusé. L'option `--allow-unrestricted-file-access` du serveur lève la
  restriction, mais ouvre aussi tout le disque au navigateur : à éviter.

## Méthode de remplissage

1. `browser_navigate` vers l'annonce, puis `browser_snapshot`. Travaille à partir des
   `ref` du dernier snapshot : ils changent après chaque action qui modifie la page.
2. Repère d'abord tout le formulaire (champs, cases, fichiers, questions personnalisées,
   bouton final). Classe chaque champ : réponse dans le profil, dans le CV master,
   nulle part (= arrêt).
3. Remplis les champs texte par lots avec `browser_fill_form`, les `<select>` avec
   `browser_select_option`, les cases et radios avec `browser_click`.
4. Fichiers : `browser_click` sur le bouton d'envoi de fichier, puis `browser_file_upload`
   avec les chemins absolus. Vérifie dans le snapshot que le nom du fichier apparaît.
5. Avant le bouton final : `browser_snapshot` complet, relis chaque valeur, puis
   `browser_take_screenshot` (pleine page) pour la fiche récap.
6. Après le clic final : attends la page ou le message de confirmation
   (`browser_wait_for`), capture-la. Pas de confirmation visible = envoi non prouvé,
   dis-le.

### Piège du sélecteur de fichier dans `browser_run_code_unsafe`

Dans un script `browser_run_code_unsafe`, `page.waitForEvent('filechooser')` est
intercepté par le MCP : il transforme la fenêtre de choix en état « sélecteur de fichier
en attente » et le script ne reçoit jamais l'événement. Procède en deux appels :
le script (ou `browser_click`) ouvre le sélecteur, puis `browser_file_upload` fournit
les fichiers, puis un second appel continue. Alternative quand l'`input[type=file]`
est accessible : `locator.setInputFiles([...])` dans le script, qui n'ouvre pas de
sélecteur.

### Combobox de localisation

Les champs « Ville » ou « Localisation » à autocomplétion (WTTJ, Lever, Greenhouse,
Workday…) n'acceptent pas une valeur tapée sans sélection : le champ semble rempli
mais repart vide à l'envoi.
- Tape le début de la ville avec `browser_type` (option `slowly` si rien ne s'affiche),
  attends la liste (`browser_wait_for` ou snapshot), puis clique l'option exacte du
  `listbox`.
- Plusieurs villes homonymes : prends celle dont le département ou la région correspond
  à `identite.code_postal`. Doute : arrêt.
- Vérifie après sélection que la valeur affichée est l'option choisie.

## Particularités par plateforme

### Welcome to the Jungle

- Beaucoup d'annonces redirigent vers le site carrière de l'entreprise (Recruitee, Lever,
  Greenhouse…). Le droit applicable est celui de `ats`, pas de `wttj`.
- Le formulaire natif verrouille l'e-mail sur celui du compte WTTJ. Accepte-le (c'est le
  compte de l'utilisateur) et note-le dans la fiche récap.
- Le champ « Poste actuel » est prérempli depuis le profil WTTJ : remplace-le par
  `identite.poste_actuel` s'il diffère.
- Localisation : combobox, voir plus haut.

### Free-Work

- Le message, le « CV partagé » et un éventuel « document additionnel » partent ensemble.
  Le CV partagé est aussi celui que voient les recruteurs dans la CVthèque : si tu le
  remplaces par un CV ciblé pour une offre, remets le CV général en partagé à la fin de la
  session.
- Le profil Free-Work a un statut (salarié, freelance, ou les deux), des contrats et un
  salaire. S'il ne correspond pas à l'offre, une fenêtre avertit le recruteur d'un statut
  incompatible. Fais régler le profil par l'utilisateur selon `situation.contrats`, ne le
  modifie pas toi-même.
- Les annonces relayées depuis d'autres plateformes renvoient vers une offre externe,
  parfois clôturée : vérifie la cible avant de préparer le dossier.

### LinkedIn

- Les CGU interdisent l'automatisation. Droit conseillé : `preparer`.
- Session fragile : si la page de connexion apparaît, arrête-toi, l'utilisateur se
  reconnecte dans la fenêtre.
- « Candidature simplifiée » : formulaire en plusieurs étapes, chaque écran a ses
  questions. Les réponses mémorisées par LinkedIn sont préremplies : relis-les toutes
  contre le profil, elles peuvent être anciennes.
- Sinon, bouton « Postuler » qui ouvre le site de l'entreprise : droit `ats`.

### Indeed, APEC, HelloWork, France Travail

- Indeed : CGU hostiles à l'automatisation, captchas fréquents. Souvent une redirection.
- APEC : protection anti-robot qui bloque le navigateur piloté. Droit conseillé : `jamais`.
- HelloWork : compte souvent demandé avant le formulaire.
- France Travail : connexion par l'utilisateur (éventuellement FranceConnect).

### Plateformes freelance

Demandent TJM, disponibilité, structure juridique, parfois SIRET. Profil vérifié avant la
première mise en relation sur certaines. Création de compte = arrêt.

### Sites carrières (ATS)

| ATS | Constats |
|---|---|
| **Ashby** | Deux `input[type=file]` : le premier est l'« autofill » qui lit le CV pour préremplir le formulaire, le second est le vrai champ CV. Envoie le CV dans le second (ou dans les deux), puis vérifie tous les champs : l'autofill peut écrire des valeurs fausses. |
| **Lever** | hCaptcha au moment de l'envoi, parfois rejeté dans le navigateur piloté (« error verifying your application ») même résolu par un humain. Après deux échecs : plan B. |
| **Recruitee** | hCaptcha à l'envoi. Si le défi expire, le bouton tourne sans fin : recharger, tout remplir à nouveau, faire résoudre et envoyer tout de suite. |
| **Greenhouse** | Formulaire long, questions personnalisées en bas, souvent obligatoires. Localisation en combobox. reCAPTCHA invisible possible. |
| **SmartRecruiters** | Envoi possible sans compte jusqu'au bout. |
| **Teamtailor** | En général pas de captcha. Case vivier fréquente : `reponses_types.vivier`. |
| **Workday** | Compte par entreprise : arrêt `creation_compte`. |
| **Welcome Kit et autres** | Comme WTTJ quand c'est la même famille de formulaire. |

### Candidature par e-mail

Webmail de l'adresse `identite.email` ouvert dans le Chrome dédié. Objet clair (intitulé
et référence de l'annonce), corps court, CV et lettre en PDF joints, signature
`lettres.signature`. Droit conseillé : `preparer` (tu laisses le brouillon ouvert,
l'utilisateur clique sur Envoyer).

## Captchas

Règle absolue : **tu ne résous jamais un captcha et tu n'utilises aucun service de
résolution.** À l'apparition d'un captcha (hCaptcha, reCAPTCHA, Turnstile, DataDome) :

1. Arrête-toi, laisse l'onglet ouvert, préviens l'utilisateur : quel site, quel captcha,
   tout le reste est rempli.
2. Il résout dans la fenêtre du Chrome piloté. S'il passe, il clique sur le bouton final
   lui-même (ou te dit de le faire si le droit est `auto`).
3. Les captchas invisibles (reCAPTCHA v3) peuvent rejeter le navigateur piloté sans rien
   afficher : un envoi refusé sans message clair après le clic est probablement ça.

Résultat variable selon les sites : certains passent quand l'humain résout, d'autres
rejettent le navigateur piloté quoi qu'il arrive. Ne boucle pas : après deux échecs, plan B.

### Plan B : fiche à copier-coller

Quand un captcha ou un anti-robot bloque, écris
`~/Documents/jobsearch/a-envoyer-<AAAA-MM-JJ>.md` (une section par candidature), pour que
l'utilisateur postule depuis son navigateur habituel :

- lien direct vers le formulaire ;
- chemins absolus du CV et de la lettre à joindre ;
- chaque champ dans l'ordre du formulaire, avec la valeur exacte à coller ;
- questions personnalisées avec leur réponse validée ;
- cases à cocher et à laisser décochées ;
- ce qui reste à décider par lui, en tête de section.

Après son envoi, il te le dit, et tu fais la suite habituelle (statut, fiche récap).

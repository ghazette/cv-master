# Profil de candidature : `profil-candidature.json`

Produit par `assets/wizard.html`, rangé dans
`~/Documents/jobsearch/candidature/profil-candidature.json` avec `chmod 600`.
Il ne contient ni mot de passe, ni clé d'API, ni cookie. Relis-le au début de chaque
session d'envoi : c'est le mandat de l'utilisateur, il prime sur tes habitudes.

## Règles de lecture

- **Valeur `null`, chaîne vide ou clé absente = pas de réponse.** Ce n'est jamais « non »
  ni « peu importe ». Si un formulaire a besoin de cette valeur : cherche dans le CV
  master, sinon arrête-toi et demande.
- **`meta.manquants`** liste ce que l'utilisateur n'a pas rempli. Pose ces questions avant
  la première candidature de la session, puis mets le fichier à jour (avec son accord) ou
  relance le wizard (« Reprendre un profil existant »).
- **Tout est formulé positivement.** Aucune clé ne décrit une phrase négative.
  `competences.<cle>.a_la_competence: "non"` veut dire « il n'a pas cette compétence »,
  sans autre lecture possible.
- **Le plus restrictif gagne** : entre `regles.mode`, `plateformes.<id>.droit` et une
  consigne donnée dans le chat, applique celle qui donne le moins d'autonomie, sauf
  consigne explicite de l'utilisateur dans le chat qui élargit le droit d'envoi pour la
  session en cours (jamais les règles d'arrêt).
- Un `mandat.accord` différent de `true` : aucun envoi, seulement de la préparation.

## Schéma (version 1)

```json
{
  "meta": {
    "schema": "profil-candidature",
    "version": 1,
    "genere_le": "2026-01-31T09:12:00.000Z",
    "manquants": ["étape 3 : TJM minimum (freelance ou portage accepté)"]
  },
  "identite": {
    "prenom": "", "nom": "",
    "email": "",
    "telephone": "",
    "ville": "", "code_postal": "",
    "linkedin": "", "github": "", "site": "",
    "poste_actuel": "", "entreprise_actuelle": ""
  },
  "situation": {
    "contrats": ["cdi", "freelance"],
    "disponibilite": "immediate | preavis | date",
    "preavis": "",
    "date_dispo": "AAAA-MM-JJ",
    "droit_travail": "nationalite_fr | ue | titre_sejour | sponsoring",
    "permis": "oui_vehicule | oui_sans_vehicule | non",
    "accroche": ""
  },
  "parcours": {
    "annees_experience": 0,
    "diplome": "",
    "anglais": "notions | technique | professionnel | courant | bilingue"
  },
  "remuneration": {
    "cdi_cible": 0, "cdi_min": 0,
    "tjm_cible": 0, "tjm_min": 0,
    "reponse": "cible | fourchette | discuter",
    "structure": "micro | societe | portage | a_creer",
    "siret": ""
  },
  "mobilite": {
    "rythme": "full_remote | hybride | sur_site",
    "jours_site_max": 0,
    "zone": "",
    "deplacements": "non | occasionnels | frequents",
    "demenagement": "non | a_discuter | oui"
  },
  "reponses_types": {
    "genre": "ne_pas_repondre | homme | femme | autre",
    "handicap": "ne_pas_repondre | oui | non",
    "source": "plateforme | site_entreprise | texte",
    "source_texte": "",
    "vivier": "oui | non",
    "newsletters": "non | oui"
  },
  "competences": {
    "kubernetes": { "nom": "Kubernetes", "a_la_competence": "oui | non | en_cours", "precision": "" }
  },
  "plateformes": {
    "linkedin":      { "compte": "oui | a_creer | non", "droit": "auto | preparer | jamais" },
    "wttj":          { "compte": "…", "droit": "…" },
    "freework":      { "compte": "…", "droit": "…" },
    "indeed":        { "compte": "…", "droit": "…" },
    "hellowork":     { "compte": "…", "droit": "…" },
    "apec":          { "compte": "…", "droit": "…" },
    "francetravail": { "compte": "…", "droit": "…" },
    "freelance":     { "compte": "…", "droit": "…" },
    "ats":           { "droit": "…" },
    "email":         { "compte": "…", "droit": "…" }
  },
  "exclusions": { "plateformes": [], "entreprises": [] },
  "lettres": { "signature": "" },
  "regles": {
    "mode": "valider | autonome",
    "plafond_jour": 5,
    "seuil_score": 70,
    "verifier_annonce_jours": 15,
    "esn": "oui | client_nomme | non",
    "arret": {
      "test_technique": true, "question_sans_reponse": true, "creation_compte": true,
      "captcha": true, "paiement": true, "rendez_vous": true,
      "message_recruteur": true, "signature_contrat": true,
      "salaire_sous_minimum": true, "texte_libre": true
    }
  },
  "mandat": { "accord": true, "signature": "", "date": "AAAA-MM-JJ" }
}
```

Les nombres valent `null` quand le champ est vide. Les valeurs séparées par `|`
ci-dessus sont les choix possibles, le fichier n'en contient qu'un.

## Sens de chaque clé

### `identite`

| Clé | Sens et usage |
|---|---|
| `prenom`, `nom` | Champs d'identité des formulaires. |
| `email` | **La seule adresse que tu saisis**, partout. Si une plateforme impose l'adresse de son compte (champ verrouillé), c'est le compte de l'utilisateur, connecté par lui : accepte, et note-le dans la fiche récap. N'en tape jamais une autre. |
| `telephone` | Format tel quel. Si le formulaire impose un indicatif séparé, découpe sans changer le numéro. |
| `ville`, `code_postal` | Champ « ville » ou « localisation ». Combobox : voir `plateformes.md`. |
| `linkedin`, `github`, `site` | Champs URL. Vide : laisse vide, même si le champ est proposé. |
| `poste_actuel` | Ce qui va dans « Poste actuel » / « Current title ». Vide : dernier poste du CV master. |
| `entreprise_actuelle` | « Entreprise actuelle ». Vide : CV master, ou vide si le champ est facultatif. |

### `situation` et `parcours`

| Clé | Sens et usage |
|---|---|
| `contrats` | Contrats acceptés (`cdi`, `cdd`, `freelance`, `portage`). Une offre hors liste ne se prépare pas sans accord. |
| `disponibilite` | `immediate`, `preavis` (alors `preavis` en texte libre, ex. « 3 mois »), `date` (alors `date_dispo`). |
| `droit_travail` | Questions « êtes-vous autorisé à travailler en France / dans l'UE ». `sponsoring` = répondre qu'un visa est nécessaire. |
| `permis` | Question permis et véhicule. |
| `accroche` | Phrase écrite par l'utilisateur pour les champs courts « Présentez-vous ». À recopier telle quelle. |
| `annees_experience` | Le chiffre assumé. Ne le recalcule pas depuis le CV, ne l'arrondis pas vers le haut. Menu à tranches : prends la tranche qui le contient. |
| `diplome`, `anglais` | Questions fermées correspondantes. `technique` = lu et écrit, pas d'oral courant. |

### `remuneration`

| Clé | Sens et usage |
|---|---|
| `cdi_cible`, `cdi_min` | k€ brut annuel. Saisis selon `reponse`. |
| `tjm_cible`, `tjm_min` | € HT par jour, freelance et portage. |
| `reponse` | `cible` = le montant visé, `fourchette` = « min à cible », `discuter` = « à discuter » si le champ accepte du texte, sinon le montant visé. |
| `structure` | Question « sous quel statut » en freelance. `a_creer` = le dire tel quel. |
| `siret` | Seulement si un formulaire freelance l'exige. Vide : arrête-toi. |

Une offre dont le salaire ou le TJM **affiché** est sous `cdi_min` ou `tjm_min` déclenche
l'arrêt `salaire_sous_minimum` (s'il est coché).

### `mobilite`

`rythme` est le maximum accepté : `full_remote` exclut l'hybride, `hybride` accepte
jusqu'à `jours_site_max` jours par semaine dans `zone`, `sur_site` accepte le temps plein
dans `zone`. `zone` est une phrase : compare-la au lieu de l'offre, et en cas de doute,
demande. `deplacements` et `demenagement` répondent aux questions du même nom.

### `reponses_types`

| Clé | Sens et usage |
|---|---|
| `genre`, `handicap` | Questions facultatives. `null` : choisis « je préfère ne pas répondre » s'il existe, sinon arrête-toi. N'infère jamais ces données. |
| `source` | « Comment avez-vous connu cette offre ? » : `plateforme` = le site où l'offre a été trouvée (WTTJ, LinkedIn…), `site_entreprise`, `texte` = recopier `source_texte`. |
| `vivier` | Case « conserver mon profil pour d'autres offres ». |
| `newsletters` | `non` = décocher toute case marketing, newsletter ou partenaire. |

Les cases de consentement **obligatoires** au traitement des données de candidature
peuvent être cochées : elles sont la condition de l'envoi que l'utilisateur a mandaté.

### `competences`

Une entrée par technologie ou méthode que l'utilisateur a tranchée. La clé est un nom
normalisé (minuscules, sans accent, `_`), `nom` est le libellé saisi.

| `a_la_competence` | Ce que tu fais |
|---|---|
| `oui` | Tu peux répondre oui à « avez-vous de l'expérience avec X ». Pour un nombre d'années ou un niveau, prends-le dans `precision` ou le CV master, sinon arrête-toi. |
| `non` | Tu ne la revendiques jamais : ni case cochée, ni mot dans un texte libre. À une question fermée, réponds non. Si la question est présentée comme un prérequis, réponds non quand même et signale-le dans le récapitulatif avant l'envoi. |
| `en_cours` | Réponds selon `precision` (ex. « en cours d'apprentissage, projet personnel »). Sans précision, arrête-toi. |
| `null` | Pas de réponse : comme une compétence absente de la liste. |

Compétence absente de la liste : cherche-la dans le CV master. Présente dans le master,
tu peux t'appuyer dessus. Absente des deux : arrête-toi et demande, n'invente pas.

### `plateformes`

`<id>` parmi `linkedin`, `wttj` (Welcome to the Jungle), `freework`, `indeed`, `hellowork`,
`apec`, `francetravail`, `freelance` (Malt et autres plateformes freelance), `ats` (sites
carrières : Lever, Greenhouse, Ashby, SmartRecruiters, Teamtailor, Recruitee, Workday…),
`email` (candidature par mail depuis le webmail ouvert dans le navigateur dédié).

| Clé | Valeurs |
|---|---|
| `compte` | `oui` = l'utilisateur a un compte et s'y connecte lui-même dans le Chrome dédié. `a_creer` = création à faire avec lui (arrêt `creation_compte`). `non` = pas de compte, ne pas en créer. |
| `droit` | `auto` = remplir et cliquer sur le bouton final (selon `regles.mode`). `preparer` = tout remplir, s'arrêter avant le bouton final, l'utilisateur clique. `jamais` = ne pas ouvrir la plateforme, produire une fiche à copier-coller. `null` = `preparer`. |

Une offre vue sur une plateforme mais postulée ailleurs (redirection vers le site
carrière) suit le droit de la plateforme **où se trouve le formulaire**.

### `exclusions`

`plateformes` : noms libres de sites interdits, en plus des `droit: jamais`.
`entreprises` : sociétés à ne jamais contacter. Compare aussi l'intermédiaire et le client
final, et les autres noms connus de l'entreprise (marque, groupe).

### `lettres`

`signature` : texte exact sous la lettre et sous un mail de candidature. Transmets-le au
skill cv quand il rédige la lettre.

### `regles`

| Clé | Sens |
|---|---|
| `mode` | `valider` : montre le récapitulatif et attends « ok » avant chaque clic final, même sur une plateforme `auto`. `autonome` : clique sur les plateformes `auto`, bilan en fin de session. |
| `plafond_jour` | Nombre maximum d'envois par jour, toutes plateformes. `null` : 5. |
| `seuil_score` | Score relu (jobsearch) minimum pour préparer une offre de soi-même. En dessous, seulement sur demande explicite. `null` : demander. |
| `verifier_annonce_jours` | Au-delà de cet âge, vérifie que l'annonce est encore en ligne avant d'envoyer. `null` : 15. |
| `esn` | ESN et cabinets : `oui`, `client_nomme` (seulement si le client final est nommé dans l'annonce), `non`. |
| `arret.*` | Règles d'arrêt. Huit valent toujours `true`, quoi que dise le fichier : `test_technique`, `question_sans_reponse`, `creation_compte`, `captcha`, `paiement`, `rendez_vous`, `message_recruteur`, `signature_contrat`. Seules `salaire_sous_minimum` et `texte_libre` peuvent valoir `false`. |

`texte_libre: false` autorise un texte libre court tiré de la lettre envoyée et du CV
master, sans fait nouveau. Il reste interdit d'écrire sur un sujet qu'aucun des deux ne
couvre.

### `mandat`

`accord: true`, `signature` et `date` attestent que l'utilisateur a lu et accepté le
mandat. Sans `accord: true`, prépare seulement, n'envoie rien. Une modification des
règles demandée dans le chat vaut pour la session, propose ensuite de mettre le
fichier à jour pour qu'elle dure.

## Mettre à jour le profil

Deux voies : rouvrir le wizard et « Reprendre un profil existant » (il recharge le JSON,
puis on retélécharge), ou modifier le fichier avec l'accord explicite de l'utilisateur
sur chaque valeur. Dans les deux cas, garde `chmod 600`.

# Fiche récap d'une candidature

L'utilisateur peut envoyer beaucoup de candidatures, et un recruteur peut rappeler des
semaines plus tard, souvent depuis un cabinet ou une ESN dont il n'a jamais retenu le
nom. La fiche sert ce moment-là : en 30 secondes, il doit savoir qui appelle, pour quel
poste, ce qu'il leur a écrit et quoi répondre aux questions évidentes.

Une fiche par dossier : `~/Documents/jobsearch/candidatures/<dossier>.json`, où
`<dossier>` est le nom du dossier de candidature dans `~/Documents/cv/` (créé par le
skill cv). Les infos de l'offre (titre, lieu, salaire, lien, revue) sont lues dans
jobs.db par `recap.py` : ne pas les recopier.

Le skill **candidature** écrit et complète ces fiches pendant l'envoi ; ce fichier en
est la référence de format. Si l'utilisateur a postulé seul, complète la fiche avec les
mêmes règles.

## Quand l'écrire

- **Au moment où le dossier est prêt** : l'en-tête seulement (`uid`, `dossier`, `canal`,
  `intermediaire`, `client_final`, `aussi_appele`), avec `envoye_le: null`.
- **Juste après l'envoi**, dans la même séquence que `jobs.py status <uid> postule` :
  `envoye_le`, `reponses_formulaire`, `capture`, `contacts` s'ils sont visibles, et
  tout le bloc `fiche`, rédigé depuis la lettre **réellement envoyée** (pas une version
  antérieure). Puis `python3 recap.py --check` et `python3 recap.py`.
- **À chaque nouvelle** (appel, mail, entretien, refus) : une ligne dans `suivi`, et le
  contact dans `contacts` avec son numéro, pour que la recherche par numéro marche.

## Format

Exemple fictif :

```json
{
  "uid": "freework:123456",
  "dossier": "acme-dev-backend",
  "canal": "Free-Work / Cabinet Exemple",
  "intermediaire": "Cabinet Exemple",
  "client_final": "Acme Assurances",
  "aussi_appele": ["Acme"],
  "envoye_le": "2026-10-15T10:32",
  "contacts": [{"nom": "Camille Durand", "role": "chargée de recrutement", "tel": "06 12 34 56 78", "email": ""}],
  "reponses_formulaire": {"Prétentions": "48 k€ brut annuel", "Disponibilité": "immédiate"},
  "capture": "captures/2026-10-15-acme-dev-backend.png",
  "fiche": {
    "en_bref": "2 ou 3 phrases : qui ils sont, quel poste, contrat, lieu, rythme.",
    "pourquoi_moi": ["l'angle de la lettre, en une phrase chacun"],
    "ce_que_jai_dit": ["chaque affirmation factuelle de la lettre et du formulaire"],
    "points_faibles": ["le manque, puis « Ta réponse : … »"],
    "questions_probables": [{"q": "la question telle qu'un recruteur la pose", "r": "la réponse, à la première personne"}],
    "a_leur_demander": ["2 ou 3 questions qui montrent que l'annonce a été lue"]
  },
  "suivi": [{"date": "2026-10-20", "evenement": "appel de qualification", "qui": "Camille Durand", "notes": "entretien client jeudi 14 h"}]
}
```

`capture` est relatif au dossier `candidatures/` (les captures vont dans `candidatures/captures/`).

## Règles de rédaction

- **Zéro invention**, comme pour le CV : chaque ligne de `ce_que_jai_dit` doit se
  retrouver dans la lettre, le CV ou les réponses du formulaire envoyés. C'est la liste
  de ce que l'utilisateur devra assumer quand on le rappellera.
- **`intermediaire` et `client_final` toujours remplis quand ils existent.** C'est la
  première chose qu'il cherchera : l'appel vient presque toujours de l'intermédiaire.
  Client non nommé : le décrire (« assureur nantais (non nommé) »).
- **`aussi_appele`** : tout autre nom sous lequel l'entreprise peut se présenter
  (marque produit, groupe, ancien nom, filiale).
- **`questions_probables`** : toujours celle sur le point du parcours le plus susceptible
  d'être creusé (trou, reconversion, activité en parallèle : reprendre la posture définie
  dans le CV maître ou le skill cv), celle sur les prétentions (reprendre la réponse
  donnée), et une ou deux sur le plus gros manque. Si un point n'est pas tranché dans le
  profil de candidature, l'écrire comme tel plutôt que d'improviser une réponse.
- Phrases courtes, tutoiement, ni tiret cadratin ni point-virgule (règle du skill cv).

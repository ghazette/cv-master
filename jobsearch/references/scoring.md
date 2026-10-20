# Revue des offres par Claude

Le pré-score automatique compte des mots-clés. Il ne sait pas si la compétence clé du
profil est le cœur du poste ou une ligne perdue dans « connaissances appréciées », ni si
« télétravail flexible » veut dire 1 jour ou 5. La revue sert à ça : lire l'annonce
entière comme le ferait l'utilisateur, face à son CV réel, et donner une note qui
justifie le temps d'une candidature.

**Avant la série** (une fois, pas à chaque offre), lis :
- `~/Documents/cv/cv-master.md` : métiers, stack, réalisations chiffrées, années
  d'expérience. C'est la seule source des « preuves » ci-dessous ; n'en invente aucune.
- `~/Documents/jobsearch/config.json` : `home`, `onsite` (zone et `max_days_on_site`),
  `remote` (pays et portées acceptés), `contracts_allowed`, `salary_target`, `esn_ok`.
- `~/Documents/jobsearch/profile.json` : métiers visés (`roles`) et pénalités, pour savoir
  ce que l'utilisateur cherche en priorité et ce qu'il évite.

## Barème (0-100)

| Score | Signification | Repères |
|---|---|---|
| 85-100 | Cible exacte, postuler vite | Métier visé (premier rôle de profile.json) ; l'essentiel de la stack ou des compétences demandées est dans le CV avec preuve concrète ; séniorité alignée ; lieu ou remote sans ambiguïté |
| 70-84 | Très bon, candidature naturelle | Métier visé, un ou deux manques secondaires (un framework différent, un outil précis) |
| 50-69 | Plausible avec adaptation | Métier voisin, ou compétence principale partiellement différente |
| 30-49 | Faible | Métier ou compétence principale éloignés ; ne vaut le coup que si l'entreprise attire particulièrement |
| 0-29 | Hors cible | Le pré-score s'est trompé (homonymie, autre métier…) |

Ce qui compte, par ordre de poids :
1. **Le cœur du poste** : ce que la personne fera 80 % du temps. Les « plus » ne comptent qu'un peu.
2. **Preuves du CV** : une compétence exercée en production ou sur un vrai projet, avec un
   résultat (chiffre, utilisateurs, mise en service) dans le CV maître, vaut plus qu'une
   simple mention dans une liste de compétences.
3. **Spécialité prioritaire** : si profile.json pénalise une stack concurrente (pénalité
   « stack différente » ou équivalente), une offre centrée sur cette stack plafonne vers 55,
   sauf autre atout fort pour le profil.
4. **Séniorité** : face à `experience_years` du profil. Un écart net (bien plus d'années
   demandées, ou poste junior pour un profil senior) fait perdre des points.
5. **Salaire** : bonus seulement si affiché et au niveau de `salary_target` ; son absence ne
   pénalise pas. Affiché sous `min_year` / `min_day` : le signaler dans `manques`.

Signaler sans pénaliser d'office : cabinet de recrutement anonyme, annonce très vague.
ESN ou régie (préciser « mission chez client ») : si `esn_ok` est `false`, `exclude: true` ;
sinon, simple mention.

## Vérifier le lieu et le remote à la lecture

Le filtre automatique a pu se tromper. La règle de l'utilisateur est stricte et se lit
dans config.json : présentiel ou hybride seulement dans la zone `onsite`, sans dépasser
`max_days_on_site` jours sur site par semaine ; ailleurs, full remote ouvert depuis un pays
de `remote.countries` (et seulement si `remote.accepted`). Pour chaque offre :

- Bureau hors zone et l'annonce impose une présence (même 1 jour/semaine ou « séminaires mensuels obligatoires au siège ») → `exclude: true`.
  Quelques déplacements ponctuels par an restent acceptables : le signaler dans `manques`.
- Bureau hors zone et l'annonce décrit un rythme hybride (« 2-3 j de télétravail », « hybrid workplace ») → c'est une présence imposée : `exclude: true`, même si un tag de la plateforme dit « remote ».
- Bureau dans la zone mais plus de jours sur site que `max_days_on_site` → `exclude: true`.
- Bureau hors zone et le texte laisse un vrai doute (« remote possible, siège préféré », page inaccessible pour vérifier), ou bureau en zone avec un rythme non précisé alors que `max_days_on_site` < 5 → `remote_doubt: true`. L'offre passe dans l'onglet « À confirmer » au lieu d'être classée parmi les offres sûres ; note-la normalement sur le fond.
- Offre déjà « à confirmer » (niveau `douteux`) : si le texte établit un full remote ouvert depuis le pays de l'utilisateur, ou un rythme compatible en zone → `remote_confirmed: true` ; s'il établit une présence incompatible → `exclude: true` ; sinon → `remote_doubt: true`.
- Remote réservé à un autre pays, ou à « Europe » sans mention du pays de l'utilisateur (sauf si `remote.scope_patterns` l'accepte) → `exclude: true`.
- Contrat absent de `contracts_allowed` découvert à la lecture → `exclude: true`.
- Offre visiblement expirée ou pourvue → `exclude: true`.

`reason` explique en une phrase courte ce qui a décidé (affichée dans le rapport).

## Format du fichier de revue

Écris `~/Documents/jobsearch/review/<AAAA-MM-JJ-HHMM>.json`, une liste :

```json
[
  {
    "uid": "wttj:abc123",
    "score": 82,
    "verdict": "Backend Python / Django dans une scale-up logistique, hybride 2 j : très proche du projet X du CV.",
    "forces": ["Django + PostgreSQL en production (projet X)", "API publique à fort trafic déjà livrée"],
    "manques": ["AWS demandé, CV orienté autre cloud"],
    "exclude": false,
    "remote_confirmed": false,
    "remote_doubt": false,
    "reason": "hybride 2 j/sem, bureau dans la zone"
  }
]
```

Puis : `python3 ~/.claude/skills/jobsearch/scripts/jobs.py import-review <fichier>`.

`forces` et `manques` : 1 à 4 éléments chacun, concrets, reliés à un fait du CV maître
ou de l'annonce. Jamais de compétence inventée. Ces lignes alimenteront ensuite le
skill `cv` pour la lettre et le CV ciblé : leur honnêteté compte.

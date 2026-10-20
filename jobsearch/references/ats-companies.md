# Entreprises suivies via leurs ATS publics

La source `ats` (`scripts/sources/ats.py`) lit directement les offres publiées sur la page
carrières d'entreprises choisies par l'utilisateur, via les API publiques (sans clé) de six
ATS. Elle complète les jobboards : beaucoup d'offres n'y sont jamais relayées, ou le sont
avec retard. La liste vit dans `config.json`, clé `ats_companies` ; elle est vide au départ.

## Quelles entreprises ajouter

Celles que l'utilisateur citerait spontanément : employeurs de sa zone `onsite`, entreprises
connues pour recruter en full remote dans son pays, acteurs de son domaine qu'il admire.
Demande-lui 5 à 15 noms pendant l'onboarding ou plus tard ; ajoute aussi une entreprise qui
revient souvent dans les meilleures offres du rapport. Inutile d'y mettre les grandes ESN :
des centaines d'offres, surtout du bruit.

## Trouver le slug

Ouvre la page carrières de l'entreprise et regarde où mène le bouton « Postuler » :

| ATS | URL vue sur le site | Slug | Endpoint de vérification (doit répondre 200 avec au moins une offre) |
|---|---|---|---|
| Lever | `jobs.lever.co/<slug>` (ou `jobs.eu.lever.co`) | `<slug>` | `https://api.lever.co/v0/postings/<slug>?mode=json` (repli `api.eu.lever.co`) |
| Greenhouse | `boards.greenhouse.io/<slug>` ou `job-boards.greenhouse.io/<slug>` | `<slug>` | `https://boards-api.greenhouse.io/v1/boards/<slug>/jobs` |
| Ashby | `jobs.ashbyhq.com/<slug>` | `<slug>` (peut contenir un point) | `https://api.ashbyhq.com/posting-api/job-board/<slug>` |
| Workable | `apply.workable.com/<slug>` | `<slug>` | `https://apply.workable.com/api/v1/widget/accounts/<slug>` |
| Recruitee | `<slug>.recruitee.com` | `<slug>` | `https://<slug>.recruitee.com/api/offers/` |
| SmartRecruiters | `jobs.smartrecruiters.com/<Id>` | `<Id>` (sensible à la casse) | `https://api.smartrecruiters.com/v1/companies/<Id>/postings?limit=1` |

Vérifie chaque slug avant de l'ajouter :

```bash
curl -s -o /dev/null -w '%{http_code}\n' 'https://api.ashbyhq.com/posting-api/job-board/<slug>'
```

Un 404 = slug faux (deviner à partir du nom marche rarement : suivre le lien « Postuler »).
Une entreprise qui recrute via Welcome to the Jungle, Teamtailor, join.com ou son propre
site n'est pas couverte ici, mais l'est déjà par les autres sources.

## Format dans config.json

Pour Lever et Ashby, dont l'API ne renvoie pas le nom de l'entreprise, préférer l'objet
`{"slug", "name"}` ; une simple chaîne est aussi acceptée. Exemple (slugs vérifiés en
octobre 2026, à remplacer par les entreprises de l'utilisateur) :

```json
"ats_companies": {
  "lever": [{"slug": "malt", "name": "Malt"}, {"slug": "brevo", "name": "Brevo"}],
  "greenhouse": ["datadog", "gitlab"],
  "ashby": [{"slug": "alan", "name": "Alan"}, {"slug": "pennylane", "name": "Pennylane"}],
  "workable": ["huggingface"],
  "recruitee": ["centreon"],
  "smartrecruiters": ["Devoteam"]
}
```

## Ce que le module garde

- titre conforme au pré-filtre métier (`prefilter.title` / `title_exclude` de config.json,
  ou mots des requêtes) ;
- poste situé en France (pays structuré, grande ville, région, ou un lieu de l'utilisateur),
  en remote pouvant inclure la France (« Europe », « EMEA », « Anywhere »), ou de lieu
  inconnu ; un remote réservé à un autre pays est écarté ;
- publication de moins de `ats_max_age_days` jours (90 par défaut : la date ATS est celle
  de la première publication, un poste encore listé est encore ouvert) ;
- au plus `per_query` offres par entreprise.

Le filtre de zone et de remote de l'utilisateur s'applique ensuite, comme pour toute source.

## Limites connues

- **Workable** bloque temporairement l'IP (429 sur tous ses endpoints) après quelques
  dizaines d'appels rapprochés : le module saute alors le reste de cet ATS pour la collecte.
- **Greenhouse** n'a pas de champ remote, et le pays y est parfois faux.
- **Ashby** : `isRemote` est vrai aussi pour l'hybride ; seul `workplaceType` compte.
- **SmartRecruiters** : un appel de détail par offre, donc lent sur les gros comptes.
- Un slug qui répond 404 est signalé dans les logs (« slug à corriger dans la config »).

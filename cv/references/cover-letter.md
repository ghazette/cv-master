# Lettre de motivation

La lettre existe pour dire ce que le CV ne peut pas dire honnêtement. Le CV est
un document de faits ordonnés. La lettre est le seul endroit où l'on peut écrire
« je n'ai pas exactement ça, voici pourquoi ce n'est pas un problème ». C'est donc
en priorité un instrument de traitement des gaps, pas un résumé du CV en prose.

## Structure

Quatre paragraphes, une page maximum, jamais plus de 350 mots.

**1. L'accroche factuelle.** Pourquoi cette entreprise et pas une autre, un
élément concret de l'offre ou du produit, pas une flatterie générique. Une phrase
sur ce qui, dans le parcours, répond directement au cœur du poste.

**2. La preuve.** Deux ou trois faits du CV développés avec le contexte que le
format CV interdit : le problème rencontré, la décision technique, le résultat.
Choisis les faits qui matchent l'offre, pas les plus impressionnants dans l'absolu.

**3. Le gap, traité de front.** Nomme la techno manquante avant que le recruteur
ne la remarque, et montre le pont : « Je n'ai pas pratiqué SQL Server, mon SQL
avancé s'est construit sur PostgreSQL et MariaDB (requêtes complexes,
optimisation, migrations de schéma). Les concepts sont transposables et la
montée en compétence sur le dialecte T-SQL est une affaire de semaines. » Traiter le gap
soi-même le désamorce. Le laisser découvrir le transforme en objection.

**4. La disponibilité et la clôture.** C'est le paragraphe qui porte l'objection
principale identifiée dans `profil.md` : activité annexe qui tourne en autonomie,
trou d'emploi déjà rempli, reconversion assumée. Un exemple concret. Le CDD
de 2026 le prouve factuellement. Puis une phrase de disponibilité et d'ouverture
à l'échange.

## Ton

Direct, sans emphase, sans superlatif. Les formules de politesse françaises
attendues, mais courtes. Pas de « passionné depuis toujours », pas de « votre
entreprise leader sur son marché ». Un recruteur technique lit vingt lettres
identiques par semaine : la seule façon de sortir du lot est d'être concret.

Elle se lit en moins d'une minute. Chaque phrase qui n'apporte pas un fait ou ne
lève pas une objection doit disparaître.

## Signature

Par défaut, une lettre se signe du seul nom de l'utilisateur.

Certains préfèrent une co-signature assumée du type **« Prénom Nom & Claude »**,
pour revendiquer publiquement le travail avec une IA plutôt que de le taire. Ce
n'est jamais à décider à sa place : la consigne doit figurer explicitement dans
`profil.md`. En son absence, signature simple.

Ne la retire jamais, et ne la signale pas non plus comme un problème à chaque
passe. Elle ne contredit pas `anti-ia.md` : ce fichier combat les marqueurs
*involontaires*, ceux qui trahissent un texte que l'auteur fait passer pour
entièrement sien. Une signature revendiquée est l'inverse, un choix assumé. Le
travail sur le lexique et les structures reste entièrement pertinent, parce qu'il
ne sert pas à cacher l'outil mais à produire une lettre qui dit quelque chose.

## Livrable

`~/Documents/cv/<societe>/lettre.md`, en texte brut prêt à coller dans un corps
de mail si l'offre donne une adresse directe, souvent le meilleur canal car il
court-circuite l'ATS et atteint un humain. Si l'offre demande une pièce jointe :

```bash
python3 $CV/scripts/build_cv.py <societe>/lettre.md --pdf --no-photo --letter
```

Le front matter se limite à `name` et `contact`, sans `title` ni `photo`. Le bloc
destinataire et la ligne d'objet sont des paragraphes ordinaires, séparés par des
lignes vides pour qu'ils ne fusionnent pas.

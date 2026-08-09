# Syntaxe du markdown CV

`build_cv.py` lit un markdown volontairement restreint. La restriction est le but :
tout ce que le format ne peut pas exprimer (colonnes, tableaux, encadrés) est
précisément ce qui casse les ATS.

## En-tête (front matter)

```markdown
---
name: Prénom Nom
title: Développeur Full Stack · JavaScript / TypeScript · Vue.js · Node.js · Python
contact: prenom.nom@example.com · 06 12 34 56 78 · France · Disponible immédiatement
photo: photo.png
---
```

Clés reconnues : `name` (obligatoire), `title`, `contact`, `photo`.
`photo` est résolu relativement au dossier du fichier markdown, puis au workspace
`~/Documents/cv/`. L'omettre (ou passer `--no-photo`) produit un CV sans photo.

Le `title` est le premier signal de matching ATS : il doit reprendre l'intitulé de
l'offre visée, pas décrire une identité intemporelle.

## Corps

| Syntaxe | Rendu |
|---|---|
| `## PROFIL` | Titre de section, majuscules, filet horizontal |
| `### Employeur \| Dates · Contrat` | Employeur en gras à gauche, dates alignées à droite |
| `#### Intitulé du poste` | Ligne de poste, italique |
| `- texte` | Puce |
| `> Stack : A · B · C` | Ligne de stack, petite et grise |
| `**Backend** : PHP, SQL` | Ligne de compétence, libellé en gras |
| texte simple | Paragraphe |
| `<!-- pagebreak -->` | Saut de page forcé |

`**gras**` fonctionne à l'intérieur des puces et des paragraphes.

Les lignes simples consécutives fusionnent en un seul paragraphe, et une ligne vide
sépare deux paragraphes. C'est ce qui permet de garder le fichier à 100 colonnes
sans créer de faux retours à la ligne dans le rendu.

## Exemple minimal

```markdown
---
name: Prénom Nom
title: Développeur Web PHP / Full Stack · PHP · SQL · JavaScript · API REST
contact: prenom.nom@example.com · 06 12 34 56 78 · Région lyonnaise
---

## PROFIL

Développeur full stack, 6+ ans d'expérience, autonome de la conception à la mise
en production.

## COMPÉTENCES TECHNIQUES

**Backend** : PHP 8, API REST, Composer, PSR-4
**Bases de données** : PostgreSQL, MariaDB / MySQL, SQL avancé

## EXPÉRIENCE PROFESSIONNELLE

### Nom de l'employeur | Juil 2020 – Fév 2024 · CDI · 3 ans 7 mois
#### Développeur Full Stack

- Développement backend PHP / SQL du produit de GED (Gestion Électronique de Documents).
- Mise en place d'une architecture distribuée (RabbitMQ, microservices).

> Stack : PHP · PostgreSQL · Vue 2 · TypeScript · RabbitMQ · Unity 3D · C++
```

## Contrôler la pagination

Deux pages sont la cible au-delà de cinq ans d'expérience, une seule en dessous. Le point de coupure propre est la fin
d'une entrée d'expérience, jamais entre un intitulé de poste et ses puces.
Si `ats_check.py` signale une troisième page ou une coupure laide, agis dans cet
ordre : couper du texte déclaratif, puis fusionner deux puces, et seulement en
dernier recours poser un `<!-- pagebreak -->`.

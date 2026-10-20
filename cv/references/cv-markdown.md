# Syntaxe du markdown CV

`build_cv.py` lit un markdown volontairement restreint. La restriction est le but :
tout ce que le format ne peut pas exprimer (colonnes, tableaux, encadrés) est
précisément ce qui casse les ATS.

## En-tête (front matter)

```markdown
---
name: Prénom Nom
title: Chargée de clientèle · Relation client · CRM Salesforce · Anglais
contact: prenom.nom@example.com · 06 12 34 56 78 · France · Disponible immédiatement
photo: photo.png
---
```

Clés reconnues : `name` (obligatoire), `title`, `contact`, `photo`.
Une première ligne `<!-- TEMPLATE ... -->` signale le modèle vide des assets :
`build_cv.py` refuse alors de rendre, et le skill lance l'onboarding.
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
| `**Logiciels** : Sage, Excel` | Ligne de compétence, libellé en gras |
| texte simple | Paragraphe |
| `<!-- pagebreak -->` | Saut de page forcé |
| `<!-- commentaire -->` | Ignoré au rendu, sur une ou plusieurs lignes |

`**gras**` fonctionne à l'intérieur des puces et des paragraphes.

Les lignes simples consécutives fusionnent en un seul paragraphe, et une ligne vide
sépare deux paragraphes. C'est ce qui permet de garder le fichier à 100 colonnes
sans créer de faux retours à la ligne dans le rendu.

## Exemple minimal

```markdown
---
name: Prénom Nom
title: Technicien de maintenance industrielle · Électrotechnique · Automatismes · GMAO
contact: prenom.nom@example.com · 06 12 34 56 78 · Région nantaise
---

## PROFIL

Technicien de maintenance, 8 ans en agroalimentaire, dépannage électrique et
pneumatique sur lignes de conditionnement, astreintes de nuit.

## COMPÉTENCES TECHNIQUES

**Électrotechnique** : armoires de commande, variateurs, habilitation BR
**Logiciels** : GMAO (Gestion de Maintenance Assistée par Ordinateur), Excel

## EXPÉRIENCE PROFESSIONNELLE

### Entreprise A, Nantes | Mars 2019 – Sept 2023 · CDI · 4 ans 6 mois
#### Technicien de maintenance

- Dépannage de 6 lignes de conditionnement en 3x8, une astreinte de nuit par semaine.
- Les arrêts de la ligne 4 revenaient chaque lundi : remplacement du capteur
  incriminé et plan de graissage revu, 3 arrêts par mois au lieu de 11.

> Outils : GMAO · Schneider · Siemens S7 · caméra thermique
```

## Contrôler la pagination

Deux pages sont la cible au-delà de cinq ans d'expérience, une seule en dessous. Le point de coupure propre est la fin
d'une entrée d'expérience, jamais entre un intitulé de poste et ses puces.
Si `ats_check.py` signale une troisième page ou une coupure laide, agis dans cet
ordre : couper du texte déclaratif, puis fusionner deux puces, et seulement en
dernier recours poser un `<!-- pagebreak -->`.

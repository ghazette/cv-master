<!-- TEMPLATE : master pas encore rempli. Tant que cette ligne existe, le skill cv lance l'onboarding (references/onboarding.md) au lieu de l'audit, et build_cv.py refuse de rendre. La supprimer une fois le master rempli. -->
---
name: Prénom Nom
title: Intitulé du poste visé · Compétence clé 1 · Compétence clé 2 · Compétence clé 3
contact: prenom.nom@example.com · 06 12 34 56 78 · Ville ou zone · Disponibilité
photo: photo.png
---

<!--
Ceci est le MASTER. Il contient tous les faits vérifiables et ne rétrécit jamais.
On n'envoie jamais ce fichier tel quel : chaque candidature en dérive une
projection dans ~/Documents/cv/<societe>/cv.md.

Front matter :
- name : prénom et nom, rien d'autre.
- title : l'intitulé du poste visé, suivi de 3 ou 4 compétences que les offres
  de ce métier citent. C'est le premier signal lu par un ATS.
- contact : e-mail, téléphone, ville ou zone (jamais l'adresse complète),
  disponibilité. Un lien LinkedIn ou portfolio peut s'ajouter, séparé par « · ».
- photo : nom du fichier image posé dans ~/Documents/cv/. Retirer la ligne s'il
  n'y a pas de photo. Sur le marché anglo-saxon, ni photo ni date de naissance.

Les commentaires HTML comme celui-ci ne sont jamais rendus dans le .docx.
Syntaxe complète : references/cv-markdown.md
Ni tiret cadratin, ni point-virgule, nulle part.
-->

## PROFIL

<!--
Deux à quatre lignes. Le métier, le nombre d'années, ce que la personne sait
faire seule de bout en bout, et le secteur si la cible est stable. Aucun
adjectif non prouvé (« rigoureux », « passionné ») : ils ne disent rien.
Exemple de forme : « Technicien de maintenance, 7 ans en agroalimentaire.
Dépannage électrique et pneumatique sur lignes de conditionnement, astreintes
de nuit, habilitation BR. »
-->

## COMPÉTENCES TECHNIQUES

<!--
Une ligne par famille, libellé en gras suivi de « : ». Les familles dépendent du
métier. Quelques exemples :
- développeur : Langages, Frameworks, Bases de données, Outils
- comptable : Logiciels, Comptabilité, Fiscalité, Paie
- soignant : Soins techniques, Logiciels, Hygiène et sécurité
- logistique : Équipements, Logiciels (WMS), Habilitations
- commercial : Prospection, Outils (CRM), Secteurs connus
Une compétence n'apparaît que dans une seule famille. C'est le seul endroit où
gloser un acronyme, et seulement si son développement est lui-même un terme
recherché. Titre « COMPÉTENCES » seul possible pour un métier non technique.
-->

**Famille 1** : 
**Famille 2** : 
**Famille 3** : 

## EXPÉRIENCE PROFESSIONNELLE

<!--
Ordre chronologique inverse, le poste le plus récent en premier.
Ligne d'employeur : « ### Employeur, Ville | Mois AAAA – Mois AAAA · Contrat · durée »
Ligne de poste    : « #### Intitulé du poste »
Puces : un verbe ou une attaque concrète, un objet, un chiffre quand il existe
et que l'utilisateur l'a confirmé. Trois à six puces pour un poste récent, une
ou deux pour un poste ancien. Pas de « participation à ».
Ligne « > Outils : » ou « > Stack : » facultative, petite et grise au rendu.
-->

### Entreprise A, Ville | Mois AAAA – Présent · Contrat
#### Intitulé du poste

- 

> Outils : 

### Entreprise B, Ville | Mois AAAA – Mois AAAA · Contrat · durée
#### Intitulé du poste

- 

## FORMATION

<!--
« ### Établissement, Ville | AAAA » puis « #### Diplôme obtenu ».
Certifications, habilitations et permis utiles au métier (CACES, permis C,
habilitation électrique, certification éditeur) vont ici ou dans une ligne
« **Certifications** : » des compétences.
-->

### Établissement, Ville | AAAA
#### Diplôme obtenu

## LANGUES

<!--
Une ligne par langue, niveau et preuve d'usage plutôt qu'un score seul.
Exemple : « **Anglais** : professionnel, échanges écrits quotidiens avec des
fournisseurs. »
-->

**Français** : langue maternelle
**Anglais** : 

## CENTRES D'INTÉRÊT

<!--
Optionnel. À garder seulement si un élément dit quelque chose du métier ou donne
une accroche d'entretien concrète (« trail, 3 courses de 40 km par an »).
Sinon, supprimer la section entière.
-->

---
name: cv
description: Itération rapide sur le CV de l'utilisateur. Audit ATS noté sur 20, adaptation ciblée à une offre d'emploi, matching des mots-clés recruteur, génération .docx + .pdf ATS-safe, et rédaction de lettre de motivation. Utilise ce skill dès que l'utilisateur parle de son CV, de son resume, d'une candidature, d'un entretien à préparer, d'une offre d'emploi qu'il colle dans le chat, d'ATS, de mots-clés recruteur, de lettre de motivation, ou demande simplement « est-ce que je matche ? », même s'il ne prononce jamais le mot « CV ».
---

# CV, boucle d'itération rapide

Ce skill sert un seul humain à la fois : l'utilisateur, dont le profil complet vit
dans `cv-master.md`. Il est calibré pour le marché français, mais rien dans les
scripts n'est spécifique à un pays.

L'idée directrice : **le CV n'est pas un document, c'est une base de données de
faits plus un rendu ciblé**. Le master contient tous les faits vérifiables. Chaque
candidature en extrait une projection réordonnée. On n'invente jamais un fait
pour une offre, on choisit lesquels remonter.

## Première utilisation

```bash
CV=~/.claude/skills/cv
cat $CV/config.json          # {"workspace": "..."}, écrit par l'init
```

**`config.json` absent** : le skill n'est pas initialisé. Demande à l'utilisateur
où se trouve son CV actuel, puis lance
`python3 $CV/scripts/init.py --yes --workspace <dossier> --cv <fichier>`
(`--workspace` vaut `~/Documents/cv` par défaut, `--cv` est facultatif). L'init
crée le workspace, copie les deux templates, copie le CV d'origine dans
`import/` et en extrait le texte dans `import/cv-extrait.txt`.

**`cv-master.md` contient encore `<!-- TEMPLATE`** : le master n'est pas rempli.
Si `import/cv-extrait.txt` existe, construis le master à partir de ce texte en
respectant `references/cv-markdown.md`, puis retire la ligne marqueur. Sinon,
interroge l'utilisateur : identité, contact, chaque poste avec dates et stack,
formation, langues. Un fait par question quand il hésite. Tant qu'une case reste
vide, elle reste vide : un CV avec un trou déclaré vaut mieux qu'un CV avec un
trou comblé par le modèle. Un extrait PDF mélange parfois l'ordre des blocs,
fais valider dates et intitulés avant de passer à la suite.

`profil.md` porte ce qui n'est pas un fait de CV mais oriente chaque rendu : cible
de poste, secteurs visés, contraintes de mobilité, objections à traiter en
lettre, préférences de ton, signature. Relis-le avant chaque adaptation, et
remplis ses sections vides en interrogeant l'utilisateur.

## Où vivent les fichiers

Workspace : le chemin de `$CV/config.json`, noté `$W` ci-dessous.

```
$W/
├── cv-master.md           # source de vérité, tous les faits, jamais tronquée
├── profil.md              # préférences et posture, lu à chaque session
├── photo.png              # photo, optionnelle
├── import/                # CV d'origine + cv-extrait.txt, lecture seule
├── build/                 # rendu du master (cv.docx, cv.pdf)
└── <societe>/
    ├── cv.md              # projection ciblée (dérivée du master)
    ├── mots-cles.md       # matching offre / CV et gaps honnêtes
    ├── lettre.md          # lettre de motivation
    └── build/             # cv.docx, cv.pdf de la variante
```

Le master ne rétrécit jamais. Si un fait est coupé d'une variante, il reste dans
le master : la prochaine offre en aura peut-être besoin.

## La boucle

```bash
CV=~/.claude/skills/cv
W=$(python3 -c "import json;print(json.load(open('$CV/config.json'))['workspace'])")

# 1. rendre (docx + pdf + vérification d'extraction ATS)
python3 $CV/scripts/build_cv.py $W/cv-master.md --pdf

# 2. auditer mécaniquement le rendu (--letter sur une lettre : pas de rubriques de CV)
python3 $CV/scripts/ats_check.py $W/build/cv.pdf

# 3. auditer la signature IA des sources markdown, avant rendu
python3 $CV/scripts/anti_ia_check.py $W/<societe>/cv.md $W/<societe>/lettre.md
```

`build_cv.py` refuse structurellement de produire du non-ATS : une seule colonne,
zéro tableau, zéro zone de texte, styles nommés standards. La photo est ancrée en
flottant (le seul élément décoratif toléré) et se retire avec `--no-photo`. Une
lettre se rend avec `--letter --no-photo` : mêmes contraintes de structure, mais
marges larges, paragraphes espacés et justifiés, parce qu'un CV cherche la
densité là où une lettre a besoin d'air.

`ats_check.py` vérifie ce qu'une machine verrait : texte extractible, nombre de
pages, tableaux, zones de texte, images, sections détectées, tirets cadratins. Il
ne juge pas le contenu, c'est ton travail, avec la grille.

`anti_ia_check.py` travaille sur le markdown source, pas sur le rendu, parce
qu'un marqueur se corrige à la source. Il compte la ponctuation interdite, le
lexique généré, les adverbes d'emphase, les énumérations ternaires, les
adjectifs non quantifiés, la densité de métriques, la part de puces au style
nominal, l'isométrie des paragraphes, et les phrases dupliquées entre le CV et
la lettre quand on lui passe les deux fichiers. Il signale, il ne corrige pas.
La grille de jugement est dans `references/anti-ia.md`.

## Les deux modes

**Mode 1, CV seul.** L'utilisateur demande un audit, ou colle son CV sans offre.
Lis `references/ats-audit.md` : grille de 6 items notés sur 5, somme ramenée sur
20, plus un point d'amélioration par item.

**Mode 2, CV et offre d'emploi.** L'utilisateur colle une annonce. Lis
`references/tailoring.md` : extraction des 40 mots-clés dominants du poste,
matching, réécriture ciblée, fichier de gaps. Puis la même grille d'audit, mais
notée face à l'offre.

**Lettre de motivation.** Lis `references/cover-letter.md`. Elle existe surtout
pour traiter frontalement les gaps que le CV ne peut pas combler honnêtement.

**Signature IA.** `references/anti-ia.md` est à lire dans les trois cas, CV seul,
CV plus offre, et lettre. C'est le seul fichier de référence qui s'applique
systématiquement. Il détaille les marqueurs qui trahissent un texte généré et les
textures qui font l'inverse.

La syntaxe du markdown CV est spécifiée dans `references/cv-markdown.md`, à lire
avant toute édition du master ou d'une variante.

## Quatre règles non négociables

**Zéro invention.** Ne jamais ajouter au CV une techno, un chiffre ou une
responsabilité que l'utilisateur n'a pas. Si l'offre exige SQL Server et qu'il n'a
fait que PostgreSQL, SQL Server n'entre pas dans le CV : il va dans le fichier de
gaps et se traite en lettre de motivation (« SQL avancé sur PostgreSQL, concepts
transposables »). La raison est pragmatique autant qu'éthique : un mot-clé bluffé
passe l'ATS puis explose en entretien technique, ce qui coûte plus cher que de ne
pas avoir été retenu. Le levier légitime, c'est de **réordonner le récit**, faire
remonter la compétence que l'offre réclame avant celle qui plaît à l'utilisateur.

**Traiter les objections de face.** Tout ce qui est vérifiable en trente secondes
par un recruteur ne se masque pas : une société dont il est gérant se lit sur un
registre public, un trou de six mois se calcule à partir des dates, une
reconversion se voit à la formation. Masquer transforme un fait neutre en
soupçon. La conduite est de contrôler le récit à la place, en une ligne qui
survit à toutes les variantes et qui répond à la peur réelle du recruteur, pas à
la version polie qu'il posera en entretien.

Le canevas : nommer le fait, donner la preuve factuelle qu'il ne coûtera rien à
l'employeur, passer à autre chose. Une activité annexe se déclare avec sa charge
réelle (« en production autonome, quelques heures de maintenance par mois ») et,
si elle existe, avec la preuve qu'un emploi à temps plein a déjà coexisté avec
elle. Un trou se déclare avec ce qui l'a rempli. Ce que l'utilisateur veut mettre
en avant ou désamorcer est noté dans `profil.md`.

Corollaire pour un profil entrepreneur : privilégier les métriques d'ingénierie
(débit, disponibilité, volumétrie) aux métriques business (clients, revenus). Les
premières prouvent la compétence, les secondes nourrissent la peur du départ.

**Ponctuation : ni tiret cadratin, ni point-virgule.** Les caractères `—`
(U+2014) et `;` ne doivent apparaître dans aucun document produit, ni dans les
fichiers source qui les génèrent. Les deux sont typographiquement corrects en
français, le point-virgule est même parfaitement académique, mais leur emploi
répété est devenu la signature du texte écrit par une IA. Un recruteur qui repère
cette signature lit tout le dossier avec ce soupçon, y compris les faits qu'il
aurait crus autrement, et le coût est sans commune mesure avec le confort
stylistique qu'ils apportent.

Écris comme quelqu'un qui rédige vite et clairement : point pour séparer deux
idées, virgule pour l'apposition, deux-points pour introduire, parenthèses pour
l'incise. Si une phrase réclame vraiment un point-virgule, c'est presque toujours
qu'elle doit devenir deux phrases. Le tiret demi-cadratin `–` reste autorisé dans
les plages de dates (« Juil 2020 – Fév 2024 »), c'est son usage normal.

Contrôle avant livraison : `LC_ALL=C.UTF-8 grep -c '[—;]' <fichier>` doit
renvoyer 0. Sans le préfixe de locale, la classe est évaluée octet par octet et
chaque `À` déclenche un faux positif, parce que `À` (C3 80) et `—` (E2 80 94)
partagent l'octet 80. `ats_check.py` et `anti_ia_check.py` font la même
vérification en Python, où le problème ne se pose pas. Attention aux .odt et
.docx reçus, où ces caractères sont invisibles à l'œil dans un diff.

**Contraintes ATS.** Une seule colonne. Aucun tableau, aucune zone de texte,
aucune information portée par une image. Abréviations explicitées au plus une
fois, dans COMPÉTENCES TECHNIQUES, et uniquement quand le développement est
lui-même un terme qu'un recruteur taperait dans une barre de recherche :
« GED (Gestion Électronique de Documents) » oui, « ELO (classement par niveau) »
non. L'ATS lit tout le fichier, l'endroit lui est indifférent. Le recruteur
humain lit les puces d'expérience et bute sur chaque parenthèse. Jamais de glose
dans une lettre de motivation, qui n'est pas parsée. Tableau de décision dans
`references/anti-ia.md`. Titres de section standards et en majuscules. PDF à texte extractible,
jamais un PDF scanné ni une image exportée. Ces contraintes sont déjà appliquées
par `build_cv.py`. Le risque vient des éditions manuelles dans Word.

## Format des livrables

Toujours produire **.docx ET .pdf**. Le .docx est la source éditable (l'utilisateur
corrige une virgule sans repasser par toi). Le PDF est ce qu'on envoie, il fige la
mise en page. Si un portail refuse le PDF, le .docx est déjà prêt. Après
génération, annonce les chemins exacts des deux fichiers, sans capture ni recopie
du contenu dans le chat.

Ne réécris jamais `cv-master.md` en réponse à une offre. Copie-le vers
`<societe>/cv.md` et travaille là. La variante générique reste intacte.

## Réflexes utiles

Quand l'utilisateur demande un changement de fond (« ajoute Redis », « j'ai fini
une mission »), il vise le **master**. Répercute ensuite dans les variantes actives
si elles sont encore en jeu.

Quand il demande « pourquoi tu as écrit X ? », il teste sa capacité à défendre la
ligne en entretien. Réponds par l'explication technique complète et donne-lui la
formulation de trois phrases qu'il peut resservir au recruteur.

Quand un chiffre est ajouté au CV, vérifie qu'il correspond à sa réalité avant de
l'écrire : c'est lui qui devra le confirmer en face.

Quand un document existant doit être retouché (un .odt, un .docx reçu), édite le
XML interne plutôt que de le régénérer, et ne fais jamais de remplacement global
sur le fichier entier : les codes couleur `#RRGGBB` des styles vivent dans le même
fichier que le texte et une substitution aveugle les casse silencieusement.

---
name: cv
description: Création et itération rapide sur le CV de l'utilisateur, y compris à partir de zéro (entretien guidé, ou import d'un CV existant en PDF, Word ou export LinkedIn). Audit ATS noté sur 20, adaptation ciblée à une offre d'emploi, matching des mots-clés recruteur, génération .docx + .pdf ATS-safe, et rédaction de lettre de motivation. Utilise ce skill dès que l'utilisateur parle de son CV, de son resume, d'une candidature, d'un entretien à préparer, d'une offre d'emploi qu'il colle dans le chat, d'ATS, de mots-clés recruteur, de lettre de motivation, dit qu'il n'a pas encore de CV ou veut en créer un, ou demande simplement « est-ce que je matche ? », même s'il ne prononce jamais le mot « CV ».
---

# CV, boucle d'itération rapide

Ce skill sert un seul humain à la fois : l'utilisateur, dont le profil complet vit
dans `cv-master.md`. Il est calibré pour le marché français, mais rien dans les
scripts n'est spécifique à un pays.

L'idée directrice : **le CV n'est pas un document, c'est une base de données de
faits plus un rendu ciblé**. Le master contient tous les faits vérifiables. Chaque
candidature en extrait une projection réordonnée. On n'invente jamais un fait
pour une offre, on choisit lesquels remonter.

## Premier lancement (à vérifier avant toute autre action)

Avant un audit, une adaptation ou une lettre, trouve le workspace et vérifie que
le master est rempli :

```bash
CV=~/.claude/skills/cv
cat $CV/config.json 2>/dev/null   # {"workspace": "..."}, écrit par init.py
W=$(python3 -c "import json;print(json.load(open('$CV/config.json'))['workspace'])" 2>/dev/null || echo ~/Documents/cv)
f=$W/cv-master.md
[ ! -s "$f" ] || head -n 1 "$f" | grep -q '^<!-- TEMPLATE' && echo "onboarding"
```

**`config.json` absent** : le skill n'est pas initialisé. Demande à
l'utilisateur s'il a déjà un CV (PDF, Word, texte, export LinkedIn en .zip ou
dossier) et où il se trouve, puis lance :

```bash
python3 $CV/scripts/init.py --yes --cv <fichier>   # --cv facultatif, --workspace vaut ~/Documents/cv par défaut
```

C'est le seul point d'entrée : l'init crée le workspace, y dépose
`cv-master.md` et `profil.md` avec leur marqueur `<!-- TEMPLATE` en première
ligne, copie le CV d'origine dans `import/`, en extrait le texte dans
`import/cv-extrait.txt` (via `scripts/extract_cv.py`, `--ocr` pour un scan) et
écrit `config.json`. Un master déjà rempli n'est jamais écrasé.

**La commande affiche `onboarding`** : le master est absent ou encore le modèle
vide. **Ne lance pas l'audit**, lis `references/onboarding.md` et déroule-le :

- **A, `import/cv-extrait.txt` existe** (ou l'utilisateur fournit un CV après
  coup, à importer en relançant `init.py --cv`) : construction du master à
  partir de ce texte, puis questions ciblées sur les trous seulement.
- **B, il n'a rien** : entretien guidé en sept blocs courts (identité et
  contact, poste visé, expériences une par une, formation, compétences,
  langues, préférences), avec AskUserQuestion pour les choix fermés.

Dans les deux cas : aucun fait inventé, chaque chiffre confirmé par
l'utilisateur, écriture de `cv-master.md` et `profil.md` dans `$W` (en retirant
la ligne `<!-- TEMPLATE`), puis premier rendu et audit ATS.

Si l'utilisateur colle une offre alors que le master est vide, dis-le-lui : on
construit d'abord le master, l'offre servira juste après. Si seul `profil.md`
est absent ou modèle, fais seulement le bloc 7 de l'onboarding.

## Où vivent les fichiers

Workspace : le chemin de `$CV/config.json` (`~/Documents/cv` par défaut), noté
`$W` ci-dessous.

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

`profil.md` porte ce qui n'est pas un fait de CV mais oriente chaque rendu : cible
de poste, secteurs visés, contraintes de mobilité, objections à traiter en
lettre, préférences de ton, signature. Relis-le avant chaque adaptation, et
remplis ses sections vides en interrogeant l'utilisateur.

## La boucle

```bash
CV=~/.claude/skills/cv
W=$(python3 -c "import json;print(json.load(open('$CV/config.json'))['workspace'])" 2>/dev/null || echo ~/Documents/cv)

# 1. rendre (docx + pdf + vérification d'extraction ATS)
python3 $CV/scripts/build_cv.py $W/cv-master.md --pdf

# 2. auditer mécaniquement le rendu (--letter sur une lettre : pas de rubriques de CV)
python3 $CV/scripts/ats_check.py $W/build/cv.pdf

# 3. auditer la signature IA des sources markdown, avant rendu
python3 $CV/scripts/anti_ia_check.py $W/<societe>/cv.md $W/<societe>/lettre.md

# hors init : relire un autre document, comparer avec --layout, passer un scan en --ocr
python3 $CV/scripts/extract_cv.py ~/chemin/ancien-cv.pdf
```

`build_cv.py` refuse structurellement de produire du non-ATS : une seule colonne,
zéro tableau, zéro zone de texte, styles nommés standards. La photo est ancrée en
flottant (le seul élément décoratif toléré) et se retire avec `--no-photo`. Sans
clé `photo:` ou sans fichier image, le CV sort simplement sans photo. Les
commentaires HTML du markdown ne sont jamais rendus, et un fichier qui porte
encore le marqueur `<!-- TEMPLATE` est refusé. Une
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

**Passe stop-slop obligatoire** sur chaque `cv.md` et `lettre.md` avant le rendu :
charge le skill **stop-slop** (installé par `install.sh`) et applique-le au texte
français. Cible prioritaire, le contraste binaire par négation : « X, pas Y »,
« ce n'est pas X, c'est Y », « non pas X mais Y », « pas seulement X, aussi Y ».
On énonce Y directement. `les décisions qui comptaient étaient des décisions de
coût ou de fiabilité, pas de modèle` devient `les décisions qui comptaient
portaient sur le coût et la fiabilité`. Les aveux de gaps (« jamais utilisé
l'outil X ») restent : ce sont des faits. Si le skill n'est pas installé :
`npx skills add hardikpandya/stop-slop -g -y`.

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
responsabilité que l'utilisateur n'a pas. Si l'offre exige SAP et qu'il n'a utilisé
que Sage, SAP n'entre pas dans le CV : il va dans le fichier de gaps et se traite
en lettre de motivation (« comptabilité fournisseurs sur Sage, logique d'ERP
transposable »). La raison est pragmatique autant qu'éthique : un mot-clé bluffé
passe l'ATS puis explose en entretien, ce qui coûte plus cher que de ne
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

Corollaire pour un profil entrepreneur : privilégier les métriques de métier
(volumes traités, délais, fiabilité) aux métriques business (clients, chiffre
d'affaires). Les premières prouvent la compétence, les secondes nourrissent la
peur du départ.

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
« GMAO (Gestion de Maintenance Assistée par Ordinateur) » oui, « RAF (reste à
faire) » non. L'ATS lit tout le fichier, l'endroit lui est indifférent. Le recruteur
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

Quand l'utilisateur demande un changement de fond (« ajoute mon CACES », « j'ai
fini une mission »), il vise le **master**. Répercute ensuite dans les variantes actives
si elles sont encore en jeu.

Quand il demande « pourquoi tu as écrit X ? », il teste sa capacité à défendre la
ligne en entretien. Réponds par l'explication complète et donne-lui la
formulation de trois phrases qu'il peut resservir au recruteur.

Quand un chiffre est ajouté au CV, vérifie qu'il correspond à sa réalité avant de
l'écrire : c'est lui qui devra le confirmer en face.

Quand un document existant doit être retouché (un .odt, un .docx reçu), édite le
XML interne plutôt que de le régénérer, et ne fais jamais de remplacement global
sur le fichier entier : les codes couleur `#RRGGBB` des styles vivent dans le même
fichier que le texte et une substitution aveugle les casse silencieusement.

## Skills voisins

Le skill **jobsearch** trouve et classe les offres en se fondant sur
`cv-master.md` : un master rempli est donc le préalable à toute veille. Quand
l'utilisateur choisit une offre, l'adaptation du CV et la lettre se font ici.
L'envoi effectif de la candidature relève du skill **candidature**. Les
fichiers à joindre sont ceux de `$W/<societe>/build/`. Avant l'envoi,
copie-les sous leur nom définitif dans `build/envoi/` (`CV_Prenom_Nom.pdf`,
`Lettre_Prenom_Nom.pdf`) : le recruteur voit ce nom, pas `cv.pdf`.

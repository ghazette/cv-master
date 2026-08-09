# cv-master

Un skill [Claude Code](https://claude.com/claude-code) qui transforme la retouche
de CV en boucle courte : audit ATS noté sur 20, adaptation à une offre d'emploi
précise, détection de la signature IA, et génération de `.docx` + `.pdf`
structurellement compatibles ATS.

Français par défaut, calibré sur les usages du marché français.

Aucune donnée personnelle dans ce dépôt. Les exemples utilisent « Prénom Nom » et
des employeurs anonymes.

---

## Le principe

**Le CV n'est pas un document, c'est une base de données de faits plus un rendu
ciblé.** Un fichier `cv-master.md` contient tous les faits vérifiables et ne
rétrécit jamais. Chaque candidature en dérive une projection réordonnée dans son
propre dossier. Le master reste intact.

**Zéro invention.** Une techno absente du master n'entre pas dans le CV, même si
l'offre la réclame. Elle part dans un fichier de gaps et se traite en lettre de
motivation. Un mot-clé bluffé passe l'ATS puis explose en entretien technique, ce
qui coûte plus cher que de ne pas avoir été retenu. Le seul levier légitime est de
réordonner le récit.

**Vérifier plutôt que croire.** Trois scripts contrôlent mécaniquement ce qu'un
modèle ne peut qu'affirmer.

| Script | Entrée | Ce qu'il contrôle |
|---|---|---|
| `build_cv.py` | markdown | rend en docx puis pdf, une colonne, zéro tableau, zéro zone de texte, styles standards, et vérifie que le texte du PDF ressort réellement à l'extraction |
| `ats_check.py` | pdf | ce qu'une machine verrait : pages, tableaux, images, sections détectées, ponctuation interdite |
| `anti_ia_check.py` | markdown | marqueurs de texte généré : lexique, adverbes d'emphase, énumérations ternaires, adjectifs non quantifiés, densité de métriques, isométrie des paragraphes, doublons CV / lettre |

**Une doctrine anti-IA.** `cv/references/anti-ia.md` liste les marqueurs qui font
lire un dossier avec suspicion, et les textures qui font l'inverse. Ni tiret
cadratin, ni point-virgule, nulle part : les deux sont typographiquement corrects
en français, mais leur emploi répété est devenu la signature du texte généré, et
un recruteur qui la repère relit tout le dossier avec ce soupçon.

---

## Prérequis

```bash
pip install python-docx lxml

# Debian / Ubuntu
sudo apt install poppler-utils libreoffice-writer

# macOS
brew install poppler
brew install --cask libreoffice
```

`python-docx` est obligatoire. `pdftotext` (poppler-utils) et LibreOffice sont
facultatifs mais fortement recommandés : sans eux, pas de PDF et pas de
vérification d'extraction, seulement le `.docx`.

## Installation

```bash
git clone https://github.com/ghazette/cv-master.git
cd cv-master
./install.sh
```

Le script copie `cv/` vers `~/.claude/skills/cv`, crée `~/Documents/cv/` et y
dépose les deux templates. Il refuse d'écraser un `cv-master.md` existant, et
affiche l'état des quatre dépendances.

Pour n'installer le skill que sur un projet plutôt que globalement :

```bash
./install.sh --project     # vers ./.claude/skills/cv
```

Installation manuelle, équivalente :

```bash
mkdir -p ~/.claude/skills ~/Documents/cv
cp -r cv ~/.claude/skills/cv
cp cv/assets/cv-master.template.md ~/Documents/cv/cv-master.md
cp cv/assets/profil.template.md    ~/Documents/cv/profil.md
```

---

## Démarrage

Remplir `~/Documents/cv/cv-master.md` avec ses vrais faits, puis `profil.md` avec
sa cible et ses objections. Ou bien ouvrir Claude Code et dire :

> aide-moi à remplir mon CV master

Claude pose les questions une par une et écrit le fichier. Tant qu'une case reste
vide, elle reste vide : un CV avec un trou déclaré vaut mieux qu'un CV avec un
trou comblé par le modèle.

Ensuite :

| On veut | On dit |
|---|---|
| un audit noté sur 20 | « audite mon CV » |
| adapter à une offre | coller l'annonce dans le chat |
| une lettre de motivation | « écris la lettre pour cette offre » |
| régénérer les fichiers | « rends le CV en pdf » |
| comprendre un choix | « pourquoi tu as écrit ça ? » |

Le skill se déclenche seul dès qu'il est question de CV, de candidature, d'ATS ou
d'offre d'emploi. Pas besoin de le nommer.

## Les deux fichiers de travail

`cv-master.md` porte les **faits** : postes, dates, stack, chiffres. C'est la
source de vérité, elle ne rétrécit jamais.

`profil.md` porte ce qui **oriente le rendu** sans jamais apparaître tel quel dans
un document envoyé : postes visés, mobilité, faits à faire remonter, faits à
laisser au fond, préférences de ton, et surtout le tableau des objections. Une
objection est un fait qu'un recruteur découvre seul en trente secondes et qui
l'inquiétera si personne ne le nomme : une société dont on est gérant se lit sur
un registre public, un trou de six mois se calcule à partir des dates. Le masquer
transforme un fait neutre en soupçon, donc on le nomme et on donne en une phrase
la preuve qu'il ne coûtera rien à l'employeur.

## Arborescence produite

```
~/Documents/cv/
├── cv-master.md           # source de vérité, tous les faits
├── profil.md              # cible, objections, ton
├── photo.png              # optionnelle
├── build/                 # cv.docx, cv.pdf du master
└── <societe>/
    ├── cv.md              # projection ciblée
    ├── mots-cles.md       # matching offre / CV et gaps honnêtes
    ├── lettre.md
    └── build/
```

---

## Usage direct des scripts

Le skill s'en sert tout seul, mais ils tournent aussi en ligne de commande.

```bash
CV=~/.claude/skills/cv

# rendre un CV
python3 $CV/scripts/build_cv.py ~/Documents/cv/cv-master.md --pdf

# rendre une lettre (marges larges, paragraphes justifiés, pas de photo)
python3 $CV/scripts/build_cv.py ~/Documents/cv/societe/lettre.md --pdf --letter --no-photo

# auditer le rendu
python3 $CV/scripts/ats_check.py ~/Documents/cv/build/cv.pdf
python3 $CV/scripts/ats_check.py ~/Documents/cv/societe/build/lettre.pdf --letter

# auditer la signature IA des sources, avant rendu
python3 $CV/scripts/anti_ia_check.py ~/Documents/cv/societe/cv.md ~/Documents/cv/societe/lettre.md
```

Sortie type :

```
cv.pdf
  ✓ extraction : 4820 caractères, 712 mots
  · pages : 2
  ✓ sections : toutes détectées
  ✓ tiret cadratin : aucun
  ✓ point-virgule : aucun

✓ document parsable
```

## Contenu du dépôt

```
├── install.sh                     # installation globale ou par projet
├── LICENSE
└── cv/
    ├── SKILL.md                   # doctrine et boucle de travail
    ├── assets/
    │   ├── cv-master.template.md
    │   └── profil.template.md
    ├── references/
    │   ├── ats-audit.md           # grille de notation sur 20
    │   ├── tailoring.md           # adaptation à une offre, 40 mots-clés
    │   ├── cover-letter.md        # structure de lettre
    │   ├── anti-ia.md             # marqueurs de texte généré
    │   └── cv-markdown.md         # syntaxe du markdown accepté
    └── scripts/
        ├── build_cv.py
        ├── ats_check.py
        └── anti_ia_check.py
```

Le `.gitignore` exclut agressivement `cv-master.md`, `profil.md`, les `.docx`,
`.pdf` et les images, pour qu'un utilisateur qui travaille depuis un clone ne
puisse pas committer son CV réel par accident. Les deux templates sont
réintroduits par une négation en fin de fichier.

---

## Adapter à un autre marché

Le contenu est écrit pour la France. Trois points à changer pour un CV
anglo-saxon, tous dans les fichiers markdown, aucun dans les scripts :

- retirer la clé `photo:` du front matter, et la date de naissance si présente,
  les deux étant un motif d'écartement,
- traduire les titres de sections dans `cv/references/cv-markdown.md`
  (`EXPÉRIENCE PROFESSIONNELLE` vers `PROFESSIONAL EXPERIENCE`, etc.),
- assouplir la règle du point-virgule dans `cv/SKILL.md`, le marqueur n'ayant pas
  la même valeur en anglais. La règle sur le tiret cadratin, elle, reste valable.

## Limites

Les scripts vérifient la **structure**, pas la pertinence. Un CV peut passer tous
les contrôles et rester mauvais sur le fond. La grille de
`cv/references/ats-audit.md` sert à juger le contenu, et c'est un jugement, pas
une mesure.

Aucun outil ne peut certifier qu'un ATS particulier parsera correctement un
fichier : chaque éditeur a son moteur, et aucun ne publie sa spécification. Ce que
ce skill garantit, c'est l'absence des constructions qui cassent connues
(colonnes, tableaux, zones de texte, information portée par une image) et un PDF
dont le texte ressort réellement à l'extraction.

Le détecteur de signature IA compte des marqueurs, il ne comprend pas le texte. Il
signale, il ne corrige pas, et il produit des faux positifs qu'il faut savoir
ignorer.

## Licence

MIT. Voir [LICENSE](LICENSE).

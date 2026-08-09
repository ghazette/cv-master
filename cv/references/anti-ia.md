# Anti-signature IA

Un recruteur repère une candidature générée en trois secondes. La détection ne
porte pas sur le fond mais sur la texture : rythme trop régulier, absence de
détail non-généralisable, vocabulaire d'inflation. Ce fichier impose la texture.

Il complète la règle de ponctuation du SKILL.md, qui ne traite que deux
caractères. Les marqueurs ci-dessous survivent très bien à un texte sans tiret
cadratin et sans point-virgule.

Priorité en cas d'hésitation : **entre une phrase élégante et une phrase
spécifique, prendre la spécifique**. L'objectif n'est pas un texte bien écrit,
c'est un texte que seul l'utilisateur aurait pu écrire.

Contrôle mécanique : `python3 $CV/scripts/anti_ia_check.py <fichier.md>`.
Le script compte ce qui se compte. Le reste relève du jugement, avec ce fichier.

---

## Articulation avec « Zéro invention »

Rien ici n'autorise à fabriquer. Le détail concret qui rend un texte humain doit
sortir de l'utilisateur, pas du modèle. Quand il manque, la conduite est de **poser
une question**, jamais de combler avec un adjectif ou un chiffre plausible.

Un chiffre halluciné détruit plus de crédibilité que dix lignes plates, et il
explose en entretien exactement comme un mot-clé bluffé.

Banque de questions qui produisent de la matière exploitable, par ordre de
rendement décroissant :

1. Sur ce projet, qu'est-ce qui a cassé, et comment tu l'as réglé ?
2. Quelle décision technique tu as prise que quelqu'un d'autre aurait prise
   autrement ?
3. Combien de temps ça prenait avant, combien après ?
4. Qu'est-ce qui te paraissait facile et qui ne l'était pas ?
5. Quelle contrainte matérielle ou métier a dicté l'architecture ?

La question 1 est la plus rentable. La question 5 est celle qui produit les
métriques d'ingénierie que la posture cofondateur privilégie.

---

## Conflit avec la règle ATS sur les acronymes, et sa résolution

Le SKILL.md impose d'expliciter les abréviations pour l'ATS. La glose d'acronyme
est par ailleurs le marqueur IA le plus fiable qui existe, parce qu'un candidat
n'explique jamais à un recruteur de son domaine ce qu'est un ELO.

Les deux règles sont toutes les deux justes. Elles portent sur des lecteurs
différents. La résolution tient en trois points.

**Un, la glose sert le matching de mots-clés, donc elle n'a de valeur que si son
développement est lui-même un terme de recherche.** Test : un recruteur
taperait-il ce développement dans une barre de recherche ?

| Acronyme | Développement | Terme de recherche ? | Verdict |
|---|---|---|---|
| GED | Gestion Électronique de Documents | oui, massivement | gloser |
| BIM | Building Information Modeling | oui | gloser |
| RGPD | Règlement Général sur la Protection des Données | l'acronyme suffit | ne pas gloser |
| ELO | classement par niveau | non, personne | ne pas gloser |
| CFD | mécanique des fluides numérique | marginal | ne pas gloser |
| revues de code | code review | oui, l'anglais est cherché | gloser une fois |

**Deux, la glose a lieu une seule fois dans le document, et de préférence dans
COMPÉTENCES TECHNIQUES.** L'ATS lit tout le fichier, il se moque de l'endroit.
Le recruteur humain, lui, lit les puces d'expérience et bute sur chaque
parenthèse. Mettre la glose dans la rubrique de compétences satisfait la machine
et laisse la prose respirer.

**Trois, jamais de glose dans une lettre de motivation.** Une lettre n'est pas
parsée par un ATS. La glose y est du bruit pur.

Application au CV actuel :

- `viewer 3D BIM (Building Information Modeling)` devient `viewer BIM`, et
  `BIM (Building Information Modeling)` apparaît dans la ligne 3D de COMPÉTENCES.
- `classement ELO (classement par niveau)` devient `classement ELO`. Le
  développement répète le mot classement, ce qui est lisible à l'oeil nu comme
  une sortie de modèle.
- `CFD (mécanique des fluides numérique : StarCCM+, OpenFOAM)` devient
  `simulations CFD sous StarCCM+ et OpenFOAM`. Les deux noms de logiciels sont
  les vrais mots-clés, la traduction ne sert à rien.

---

## Lexique interdit

Ne jamais produire ces formulations ni leurs variantes proches.

**Ouvertures**
- C'est avec un grand intérêt que
- Votre annonce a retenu mon attention
- Fort de mes X années d'expérience, Riche de mon parcours, Doté d'une solide
  expertise
- Votre entreprise, reconnue pour son innovation, son excellence, son engagement
- En tant que développeur passionné par

**Auto-description**
- passionné par l'innovation, force de proposition, esprit d'équipe et autonomie,
  rigoureux et polyvalent, véritable atout, réelle valeur ajoutée, relever de
  nouveaux défis, environnement stimulant, mettre mes compétences au service de
- allie X et Y, conjugue X et Y, à la croisée de

**Vocabulaire**
- écosystème, levier, synergie, holistique, transversal, s'inscrire pleinement
  dans, en parfaite adéquation avec, au coeur de ma démarche, faire écho à,
  incarner, catalyser, orchestrer, piloter de bout en bout
- enjeux, orientations, problématiques, terrain que je connais, conditions
  réelles, avec la rigueur que X impose, exigences de robustesse

**Clôtures**
- Je reste à votre entière disposition pour tout complément d'information
- Je serais ravi ou heureux d'échanger de vive voix
- échanger sur vos enjeux produit et vos orientations techniques
- tout paragraphe de récapitulation finale, En somme, mon profil

**Titres de rubrique**
- Mes atouts, Mon parcours en bref, Ce que je peux vous apporter
- emojis dans les intitulés

---

## Structures interdites

Elles trahissent plus sûrement que le vocabulaire.

| Pattern | À ne pas produire |
|---|---|
| Rythme ternaire | conception, développement et déploiement. Maximum une énumération à trois termes par document, jamais deux d'affilée |
| Doublet d'adjectifs | réactif et scalable, développée et exploitée. Un adjectif suffit, ou zéro |
| Adverbe en -ment d'emphase | précisément, réellement, concrètement, pleinement, proprement. Maximum deux par document |
| Antithèse creuse | Je ne me contente pas de coder, je conçois |
| Négation-correction | Non pas X, mais Y |
| Balancement | tant sur le plan technique que humain |
| Clivage | Ce qui me motive, c'est |
| Participe présent en tête | Ayant piloté la refonte de |
| Marqueur de sujet | Concernant X :, S'agissant de Y : |
| Paragraphes isométriques | tous de 3 à 4 lignes, chacun avec sa phrase de conclusion |

Nuance sur l'adverbe : celui qui qualifie un adjectif est du remplissage
(`je connais concrètement`). Celui qui introduit un fait est acceptable
(`Concrètement, on est passé de 12 s à 3 s`).

Nuance sur le point médian : le `·` comme séparateur de liste dans une ligne
Stack ou dans l'en-tête est une convention de mise en page de CV, produite par
`build_cv.py`, et ne pose aucun problème. Le `·` en pleine phrase, lui, est un
marqueur. Le script ne compte que le second cas.

---

## Spécifique au CV

**Le style nominal intégral.** Vérifier que les puces ne commencent pas toutes
par un substantif (Conception, Architecture, Intégration, Mise en place,
Développement). Imposer au moins un tiers de puces commençant autrement : verbe
conjugué, complément, ou attaque directe sur le problème.

- Porté le viewer de Unity WebGL vers Three.js pour supprimer la dépendance au
  plugin.
- Le pipeline vidéo saturait la VRAM, d'où un découpage en tuiles VAE.

**L'adjectif d'inflation non quantifié.** Bannir scalable, haute performance,
faible latence, avancé, complet, robuste, optimisé, entièrement, pleinement dès
qu'aucun chiffre ne suit. Test : la phrase survit-elle à la question combien ?

- `infrastructure WebSocket temps réel à faible latence` devient
  `WebSocket, environ 40 ms de bout en bout sur un match à 10 joueurs`

**Le zéro-chiffre.** Un CV technique sans une seule métrique est aussi suspect
qu'un CV bourré de +40 %. Viser 3 à 6 nombres, non ronds ou contre-intuitifs.
Conformément à la posture cofondateur, prendre des métriques d'ingénierie
(débit, latence, volumétrie, disponibilité) et non des métriques business.

**La redondance de la liste de compétences.** Aucune techno dans deux rubriques.
Pas de compétence devenue triviale (interfaces responsive, HTML5). Pas de terme
fourre-tout ajouté en fin de liste après avoir déjà nommé les outils concrets
(`agents IA pour le développement` après Claude Code et Cursor).

**La parenthèse de rembourrage.** `PHP (Composer, autoloading PSR-4)`. Détailler
les sous-évidences d'une compétence de base signale qu'on l'étire. À distinguer
de la glose ATS, qui est légitime dans les conditions vues plus haut.

**La rubrique créée pour l'offre.** Une rubrique qui n'existe que dans une
variante, remplie du vocabulaire exact de l'annonce, se voit. Un mot-clé repris,
deux au maximum, et jamais une rubrique inventée pour l'occasion. Si la
compétence est réelle, elle doit déjà exister dans le master.

---

## Ce qui n'est pas un marqueur : la signature assumée

Une lettre peut se signer « Prénom Nom & Claude », si `profil.md` porte cette
consigne explicite.
Ce fichier traque les marqueurs involontaires, ceux d'un texte présenté comme
entièrement écrit par son auteur. Une mention revendiquée ne relève pas de cette
catégorie et ne se retire pas. Le reste du fichier s'applique sans changement :
l'objectif n'est pas de dissimuler l'outil, c'est d'écrire une lettre qui dise
quelque chose de spécifique.

## Spécifique à la lettre de motivation

**Le miroir d'annonce.** Reformuler l'offre et affirmer qu'elle correspond. Le
recruteur relit son propre texte et n'apprend rien. Remplacer par une phrase qui
prouve la lecture par une inférence, pas par une reprise.

- Ne pas écrire : Votre annonce décrit précisément l'environnement dans lequel je
  travaille le mieux, un produit métier complexe, une architecture maison, des
  données critiques, une équipe resserrée.
- Écrire plutôt : Une archi maison sans framework, ça veut dire que la doc c'est
  le code. C'est le contexte que je préfère.

**Le mapping paragraphe par exigence.** Un modèle traite les critères de
l'annonce dans l'ordre, un paragraphe chacun, longueurs égales. Trop propre.
Imposer un déséquilibre : un paragraphe long sur ce qui compte vraiment, un
court, et au moins une exigence traitée en une phrase ou pas du tout.

**La réfutation anticipée.** Le modèle devine l'objection et la nie.

- Ne pas écrire : L'autonomie de la conception à la mise en production n'est pas
  une formule sur mon CV, j'ai porté (...)
- Nier le soupçon l'installe. Supprimer la dénégation, garder la preuve.

**Le hedge confiant sur une compétence absente.** C'est le point où la lettre
peut coûter la candidature, et il touche directement le traitement des gaps
défini dans `cover-letter.md`.

- Ne pas écrire : La transposition à T-SQL devrait se faire sans encombre.
- Le conditionnel plus la litote signalent « je ne l'ai jamais fait » tout en
  prétendant le contraire, ce qui coûte plus cher que l'aveu.
- Choisir un des deux régimes : l'aveu net (`je n'ai jamais écrit de T-SQL`), ou
  la preuve de transfert (`sur la dernière migration MySQL vers PostgreSQL, j'ai
  réécrit environ 40 requêtes à la main`). Jamais l'entre-deux.

**Le recopiage du CV.** Une formulation identique dans les deux documents est une
ligne perdue, le recruteur lit deux fois la même chose. La lettre doit dire ce
que le CV ne peut pas dire : une cause, une décision, un contexte.

---

## Textures à imposer

Ce qui rend un texte humain n'est pas l'absence de tics, c'est la présence de
ceci. Au moins quatre par candidature, tous issus de faits réels du master.

1. **Le détail invérifiable mais crédible.** Un nom de SDK, une version, une
   contrainte matérielle, une durée bizarre. `maintenance limitée à quelques
   heures par mois` vaut mieux que trois lignes d'adjectifs.
2. **La limite assumée.** `missions confidentielles`, `Chinois : débutant`. Un
   modèle ne s'auto-limite pas spontanément, c'est pour ça que ça sonne vrai.
3. **La cause, pas le résultat.** Dire pourquoi la décision technique a été
   prise, pas qu'elle était bonne. `On est passé en blue-green parce qu'une
   migration Alembic coupait le chat en pleine conversation.`
4. **La variation de longueur.** Après deux phrases longues, une de six mots.
5. **L'attaque concrète.** Une phrase qui commence par Concrètement, En pratique,
   Le problème était que, suivie d'un fait et jamais d'une généralité.
6. **Le registre parlé maîtrisé.** Une tournure orale par lettre, pas plus.

Trois exemples du niveau de texture visé :

- `je suis à l'aise sans framework`, affirmation qui prend un risque
- l'enchaînement activité annexe autonome vers disponibilité pour un temps plein,
  qui répond à une objection que le recruteur n'a pas posée
- `Conversion de maquettes issues d'un SDK CAO propriétaire vers un format
  optimisé pour le web`, trop spécifique pour avoir été inventé

Le point commun : chacun sort d'un fait du master, aucun ne pourrait être écrit
par un modèle qui ne connaît pas le dossier.

---

## Passe de contrôle avant livraison

Exécuter, corriger, ne pas afficher la passe sauf demande explicite de relecture.

1. **Test de la négation.** Pour chaque phrase d'auto-description, son inverse
   est-il absurde ? « Je ne suis pas rigoureux » est absurde, donc la phrase ne
   dit rien, donc elle saute.
2. **Test de substitution.** Remplacer le nom de la société par un concurrent. Si
   le texte tient encore, il est générique.
3. **Test de l'anecdote.** Compter les faits vérifiables. En dessous de quatre
   sur l'ensemble, réécrire ou poser des questions.
4. **Test du ternaire.** Plus d'une énumération à trois termes, casser en deux ou
   quatre, ou supprimer.
5. **Test de la glose.** Chercher tous les `(` du document. Chaque glose
   d'acronyme est confrontée au tableau plus haut, et déplacée vers COMPÉTENCES
   si elle survit.
6. **Test du doublon CV et lettre.** Toute phrase présente dans les deux est
   réécrite dans la lettre, ou coupée.
7. **Test du miroir.** Si le recruteur peut se relire lui-même dans la lettre,
   réécrire.
8. **Test des longueurs.** Si tous les paragraphes tiennent à 20 % les uns des
   autres, en couper un de moitié.

La ligne École 42 du master est le cas test de référence de ce fichier. Dans sa
version actuelle elle est du soft skill pur, interchangeable avec n'importe quel
candidat 42, et elle échoue aux tests 1 et 2. Version qui passe :
`C, C++, systèmes Unix, pas de cours magistraux.` Ou rien, 42 se passe de
commentaire.

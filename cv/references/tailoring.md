# Adapter le CV à une offre

Le principe est toujours le même : **réordonner le récit, jamais l'inventer**. Une
offre PHP-first face à un CV JavaScript-first, ou un poste de responsable de rayon
face à un CV de vendeuse, n'exige pas un autre candidat : elle exige que les faits
pertinents déjà présents remontent en surface.

## 1. Lire l'offre comme une machine

Extrais dans cet ordre :

- **l'intitulé exact** du poste (il deviendra le titre du CV),
- **les logiciels, technologies, normes et habilitations nommés**, avec leur
  version ou catégorie quand elle est précisée (« SAP S/4HANA », « CACES R489
  catégorie 3 », « PHP 8.3 »),
- **les verbes de mission** (concevoir, maintenir, encadrer, négocier, contrôler),
- **les exigences de profil** (années d'expérience, autonomie, anglais, permis),
- **le secteur et ses contraintes** (fintech, donc réglementaire, conformité,
  sécurité),
- **les outils de process** (ERP, CRM, Git, Jira, Teams, tableaux de bord),
- **les « nice to have »**, points gratuits quand le candidat les a.

Le secteur est le gisement le plus souvent raté. Une fintech « fortement
réglementée » cherche quelqu'un qui a déjà vécu la contrainte réglementaire.
Si l'utilisateur a géré du RGPD et des exigences de prestataires de paiement sur
un projet passé, ce fait dormait dans le master et vaut plus que trois technos.

## 2. Constituer les 40 mots-clés

Complète les termes de l'offre jusqu'à 40 avec les mots-clés dominants du marché
pour cet intitulé, ceux qui apparaissent dans la majorité des annonces du même
poste même s'ils manquent dans celle-ci (les ATS sont souvent configurés avec un
référentiel plus large que le texte publié). Puise dans ces familles, à adapter au métier :

intitulés voisins du poste · logiciels et versions · équipements et machines ·
normes, certifications et habilitations (ISO 9001, HACCP, CACES, habilitation
électrique) · méthodes et process (Lean, 5S, Agile) · qualité et sécurité ·
réglementation du secteur · outils transverses (ERP, CRM, Excel) · secteur et
type de clientèle · soft (autonomie, encadrement, anglais).

Pour un métier technique de l'informatique, les familles se précisent : langage
et versions · frameworks · base de données et dialecte SQL · architecture (API
REST, microservices) · qualité (tests, revue de code) · outils (Git, Docker,
CI/CD) · méthodes (Agile, Scrum).

Classe chaque mot-clé en trois catégories, et sois impitoyable sur la frontière :

- **Présent.** Le terme figure déjà dans le CV.
- **Ajoutable.** L'utilisateur a le fait, il manquait juste au CV. C'est là que se
  gagne le score.
- **Gap.** Il ne l'a pas. Il n'entre pas dans le CV. Point final.

## 3. Réécrire

Dans l'ordre d'impact décroissant :

**Le titre.** Il devient l'intitulé de l'offre, suivi des 3 ou 4 technos qu'elle
réclame. C'est le changement à plus fort effet de levier du document entier.

**Le profil.** Reprends les formulations de l'offre quand elles décrivent
véritablement l'utilisateur : « autonome de la conception à la mise en production »
repris quasi mot pour mot est un signal fort, pour la machine comme pour l'humain.
Fais apparaître le secteur.

**Les compétences.** Réordonne les lignes pour que la stack de l'offre soit lue en
premier. Ajoute une ligne dédiée si le secteur l'exige (« Réglementaire /
Sécurité »). Utilise le vocabulaire de l'offre : « gestion des réclamations »
plutôt que « SAV » si c'est le terme de l'annonce, « revues de code (pull
requests) » plutôt que « code review » si l'annonce dit « PR obligatoires ».

**Les puces d'expérience.** Réordonne à l'intérieur de chaque poste : la puce qui
matche l'offre passe en première position. Une entrée dont la première puce parle
de merchandising alors que l'offre porte sur la gestion des stocks gaspille son
meilleur emplacement.

**Les lignes d'outils ou de stack.** Commence par ce que l'offre nomme.

**La localisation.** Si le poste est en présentiel à Bordeaux, « France » devient
« Région bordelaise ». Un ATS filtre sur la géographie. Les contraintes de
mobilité de `profil.md` priment : ne jamais suggérer une proximité que
l'utilisateur n'a pas.

Rétrograde sans supprimer ce qui ne sert pas l'offre : un différenciateur (une
langue rare, une habilitation, un logiciel de niche) reste une raison de
rappeler, il descend simplement dans la hiérarchie de lecture.

## 4. Livrables

Dans `~/Documents/cv/<societe>/` :

- `cv.md` plus `build/cv.docx` et `build/cv.pdf`,
- `mots-cles.md`, les 40 mots-clés en trois colonnes (présent, ajouté, gap), les
  gaps assortis de leur stratégie de traitement, et les points que l'utilisateur doit
  vérifier lui-même avant envoi (« as-tu vraiment utilisé le module achats de
  SAP ? », « quelle version du logiciel chez cet employeur ? »),
- `lettre.md` si demandée.

Termine par la grille d'audit (`ats-audit.md`) notée **face à l'offre**, et
annonce le score projeté de la version adaptée. Signale explicitement les points
non vérifiables que l'utilisateur doit confirmer : le CV est envoyé sous sa signature,
pas la tienne.

## 5. Le piège des années d'expérience

Une offre qui demande « 5 ans en gestion de paie » face à un CV où la paie couvre
4 ans n'est pas disqualifiante : l'expérience totale du métier compte, et les
recruteurs lisent l'exigence comme un ordre de grandeur. Ne gonfle jamais les dates. Signale
l'écart dans `mots-cles.md` et prépare la réponse pour l'entretien.

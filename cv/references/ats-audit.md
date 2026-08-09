# Grille d'audit ATS

Un ATS lit un CV en deux temps : un parseur extrait des champs structurés (nom,
coordonnées, expériences, compétences, formations) via NLP, puis un moteur de
scoring compare le texte extrait aux mots-clés de l'offre. La grille ci-dessous
note les deux : la moitié des items porte sur la **parsabilité** (le document
survit-il à l'extraction), l'autre sur le **matching** (le texte extrait
contient-il les bons mots).

Avant de noter, lance toujours `scripts/ats_check.py` sur le fichier. Plusieurs
items se tranchent mécaniquement, et une note posée sans mesure n'a pas de valeur.

## Les 6 items

**1. Titre clair et lisible.** Une ligne d'intitulé sous le nom, reprenant un
intitulé de poste réel du marché. 5/5 si le titre correspond à l'offre visée (ou,
en mode CV seul, à un intitulé standard largement utilisé). Descendre à 2,5/5 si
le titre est générique ou décalé par rapport à la cible. Note 0 s'il n'y a pas de
titre du tout, car le parseur doit alors deviner le métier depuis les expériences.

**2. Format.** 5/5 pour un PDF à texte natif ou un .docx. Alerte immédiate et
note plancher pour une image (JPEG, PNG) ou un PDF plat ou scanné : le contenu est
alors littéralement invisible pour la machine. `ats_check.py` tranche cet item.

**3. Structure.** Titres de section standards et repérables (PROFIL, COMPÉTENCES,
EXPÉRIENCE PROFESSIONNELLE, FORMATION, LANGUES). Une seule colonne. Ordre
chronologique inverse. 5/5 si toutes les sections attendues sont détectées dans
le texte extrait.

**4. Mots-clés du poste.** L'item qui fait la différence, et le seul qui demande
un vrai travail. Recense les 40 mots-clés les plus fréquents dans les offres pour
cet intitulé (voir `tailoring.md` pour la méthode et les familles). Note :
proportion présente multipliée par 5. Liste explicitement **tous** les manquants
et génère le fichier `mots-cles.md`. Un CV structurellement parfait plafonne à
12/20 si cet item est faible, et c'est normal : c'est là que se joue le tri.

**5. Images et abréviations.** La photo de profil est tolérée, l'ATS l'ignore et
elle ne coûte rien. Toute autre image est une alerte : logo d'entreprise, barre de
niveau de compétence, icône remplaçant un intitulé, pictogramme portant une
information. Les barres de progression sont le piège classique, elles ne
produisent aucun texte extractible. Les abréviations non explicitées (GED, ELO,
CFD, BIM) coûtent aussi des points : l'ATS cherche le terme complet, pas le sigle.

**6. Éléments illisibles.** Tableaux, zones de texte, colonnes, en-têtes et pieds
de page contenant des informations. Un tableau se parse souvent cellule par
cellule dans un ordre imprévisible, et une zone de texte est fréquemment ignorée.
Les coordonnées placées dans un en-tête Word disparaissent chez certains parseurs,
d'où la règle : les coordonnées vivent dans le corps du document. `ats_check.py`
compte ces éléments.

## Notation

Somme des 6 notes sur 30, ramenée sur 20 : `score = somme / 30 × 20`, arrondi à
0,5. Annonce les deux (« 24,5/30 → 16/20 ») : la somme brute montre où ça coince,
la note sur 20 donne le verdict.

## Format de rendu

Ouvre par le constat stratégique en deux ou trois phrases : ce qui matche
réellement, ce qui bloque, et l'action à plus fort effet de levier. Le tableau
vient ensuite, car un tableau sans lecture est illisible.

```markdown
| Item | Note /5 | Constat & point d'amélioration |
|---|---|---|
| Titre clair et lisible | 2,5/5 | … → correction proposée |
| Format | 5/5 | ✔ PDF texte natif, extraction vérifiée |
| Structure | 5/5 | ✔ Sections standards, une colonne |
| Mots-clés du poste | 2,5/5 | Présents : … / Manquants : … |
| Images / abréviations | 4,5/5 | Photo tolérée, « GED » à expliciter |
| Éléments illisibles | 5/5 | ✔ Aucun tableau ni zone de texte |

**Score : 24,5/30 → 16/20**
```

Ferme sur les alertes d'honnêteté : ce que tu refuses d'écrire dans le CV parce
que ce serait faux, et comment le traiter ailleurs (lettre, entretien). Cette
section vaut souvent plus que la note.

## Ce qu'il ne faut pas faire

Ne gonfle pas les notes pour faire plaisir. Un 16/20 assorti de trois corrections
précises est infiniment plus utile qu'un 19/20 complaisant : la note n'a aucune
valeur en soi, elle sert uniquement à hiérarchiser le travail restant.

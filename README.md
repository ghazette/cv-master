# CV + recherche d'emploi pour Claude Code

Trois skills qui s'enchaînent en partant de zéro (pas de CV, aucune info), plus un skill tiers de relecture :

| Skill | Ce qu'il fait |
|---|---|
| `cv` | Crée ton CV par entretien ou depuis un ancien CV, puis l'adapte à chaque offre (CV + lettre en PDF compatibles ATS, sans rien inventer). |
| `jobsearch` | Collecte les offres sur les plateformes françaises, filtre selon ta zone et le télétravail, les classe par rapport à ton CV. |
| `stop-slop` | Skill tiers ([hardikpandya/stop-slop](https://github.com/hardikpandya/stop-slop)) installé avec les autres : retire les tournures IA des CV et lettres (« X, pas Y »…). |
| `candidature` | Remplit les formulaires dans un Chrome dédié. Tu cliques toi-même sur Envoyer. Garde une fiche par candidature pour savoir qui t'appelle. |

## Installation

```bash
git clone <url-du-depot> && cd <dossier>
./install.sh                      # sans CV
./install.sh --cv ~/mon-cv.pdf    # avec un ancien CV (pdf, docx, odt, txt)
```

Dépendances : `python3` et `python-docx` (installé si absent), LibreOffice et poppler-utils pour le PDF, `uv` pour LinkedIn/Indeed, Node.js pour le navigateur. `install.sh` dit ce qui manque.

## Utilisation

Lance Claude Code depuis `~/Documents/cv`, puis dans l'ordre :

1. « crée mon CV »
2. « lance la recherche d'emploi »
3. « postule à <offre> »

Chaque skill détecte qu'il démarre à vide et pose ses questions.

## Données

Rien de personnel dans ce dépôt. Tout reste chez toi :

- `~/Documents/cv/` : CV master et dossiers par candidature
- `~/Documents/jobsearch/` : config, offres, historique, fiches
- `~/.config/jobsearch/.env` : clés API facultatives (à remplir toi-même, jamais dans le chat)

## Licence

MIT

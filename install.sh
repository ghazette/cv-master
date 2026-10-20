#!/usr/bin/env bash
# Installe les trois skills (cv, jobsearch, candidature) pour Claude Code.
#   ./install.sh            installation globale dans ~/.claude/skills/
#   ./install.sh --project  installation locale dans ./.claude/skills/
#   ./install.sh --force    remplace les skills déjà installés sans demander
# Les données personnelles ne sont jamais touchées : ~/Documents/cv,
# ~/Documents/jobsearch et ~/.config/jobsearch sont seulement créés s'ils manquent.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_DIR="$HOME/.claude/skills"
FORCE=0
for arg in "$@"; do
  case "$arg" in
    --project) SKILLS_DIR="$PWD/.claude/skills" ;;
    --force)   FORCE=1 ;;
    *) echo "Option inconnue : $arg"; exit 1 ;;
  esac
done
CV_DIR="$HOME/Documents/cv"

echo "Skills      : $SKILLS_DIR"
echo "CV          : $CV_DIR"
echo "Recherche   : $HOME/Documents/jobsearch"
echo

mkdir -p "$SKILLS_DIR"
for skill in cv jobsearch candidature; do
  dest="$SKILLS_DIR/$skill"
  if [[ -e "$dest" && $FORCE -eq 0 ]]; then
    read -r -p "$dest existe déjà. Le remplacer ? [o/N] " reply
    [[ "$reply" =~ ^[oOyY]$ ]] || { echo "  $skill conservé"; continue; }
  fi
  rm -rf "$dest"
  cp -r "$ROOT/$skill" "$dest"
  find "$dest" -name __pycache__ -type d -prune -exec rm -rf {} +
  echo "  skill $skill installé"
done

# CV : templates à remplir, jamais écrasés.
mkdir -p "$CV_DIR"
for pair in "cv-master.template.md:cv-master.md" "profil.template.md:profil.md"; do
  tpl="${pair%%:*}"; target="$CV_DIR/${pair##*:}"
  if [[ -e "$target" ]]; then
    echo "  ${pair##*:} existe déjà, conservé"
  else
    cp "$ROOT/cv/assets/$tpl" "$target"
    echo "  ${pair##*:} créé (template vide)"
  fi
done

# Recherche d'emploi : dossiers, config et .env modèles, jamais écrasés.
python3 "$SKILLS_DIR/jobsearch/scripts/init.py"

echo
echo "Dépendances :"
check_py() {
  python3 -c "import $1" 2>/dev/null \
    && printf "  %-14s OK\n" "$2" \
    || printf "  %-14s manquant (%s)  ->  pip install %s\n" "$2" "$3" "$2"
}
check_cmd() {
  command -v "$1" >/dev/null \
    && printf "  %-14s OK\n" "$1" \
    || printf "  %-14s manquant (%s)  ->  %s\n" "$1" "$2" "$3"
}
check_py docx python-docx obligatoire
check_py lxml lxml recommandé
check_cmd pdftotext "recommandé, vérifie le PDF" "apt install poppler-utils / brew install poppler"
if command -v soffice >/dev/null || command -v libreoffice >/dev/null; then
  printf "  %-14s OK\n" libreoffice
else
  printf "  %-14s manquant (pas de PDF)  ->  apt install libreoffice-writer / brew install --cask libreoffice\n" libreoffice
fi
check_cmd uv "LinkedIn et Indeed" "https://docs.astral.sh/uv/"
check_cmd npx "navigateur de candidature" "installer Node.js"

cat <<EOF

Navigateur de candidature (facultatif, pour que Claude remplisse les formulaires) :
  claude mcp add candidature -- npx -y @playwright/mcp@latest --browser chrome --user-data-dir "$HOME/.config/jobsearch/navigateur"
  puis redémarrer Claude Code.

Prochaine étape : lancer Claude Code et dire « crée mon CV ».
Ensuite « lance la recherche d'emploi », puis « postule ».
EOF

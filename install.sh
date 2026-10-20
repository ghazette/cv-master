#!/usr/bin/env bash
# Installe les trois skills (cv, jobsearch, candidature) pour Claude Code, puis lance les inits.
#   ./install.sh                     installation globale dans ~/.claude/skills/
#   ./install.sh --project           installation locale dans ./.claude/skills/
#   ./install.sh --force             remplace les skills déjà installés sans demander
#   ./install.sh --cv ~/mon-cv.pdf   importe un CV existant pendant l'init
# Les autres options sont transmises à cv/scripts/init.py
# (--workspace, --cv, --photo, --name, --title, --contact, --signature, --yes).
# Les données personnelles ne sont jamais écrasées.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_DIR="$HOME/.claude/skills"
FORCE=0
INIT_ARGS=()
for arg in "$@"; do
  case "$arg" in
    --project) SKILLS_DIR="$PWD/.claude/skills" ;;
    --force)   FORCE=1 ;;
    *)         INIT_ARGS+=("$arg") ;;
  esac
done

echo "Skills : $SKILLS_DIR"
echo

mkdir -p "$SKILLS_DIR"
for skill in cv jobsearch candidature; do
  dest="$SKILLS_DIR/$skill"
  backup=""
  if [[ -e "$dest" ]]; then
    if [[ $FORCE -eq 0 && -t 0 ]]; then
      read -r -p "$dest existe déjà. Le remplacer ? (tes données ne sont pas touchées) [o/N] " reply
      [[ "$reply" =~ ^[oOyY]$ ]] || { echo "  $skill conservé"; continue; }
    fi
    # la config du skill cv pointe vers le workspace de l'utilisateur, on la garde
    [[ -f "$dest/config.json" ]] && backup="$(cat "$dest/config.json")"
    rm -rf "$dest"
  fi
  cp -r "$ROOT/$skill" "$dest"
  [[ -n "$backup" ]] && printf '%s\n' "$backup" > "$dest/config.json"
  find "$dest" -name __pycache__ -type d -prune -exec rm -rf {} +
  chmod +x "$dest"/scripts/*.py
  echo "  skill $skill installé"
done

python3 -c "import docx" 2>/dev/null || {
  echo "  python-docx manquant, installation..."
  python3 -m pip install --user python-docx lxml \
    || echo "  échec : lance « pip install python-docx lxml » à la main"
}

echo
python3 "$SKILLS_DIR/cv/scripts/init.py" ${INIT_ARGS[@]+"${INIT_ARGS[@]}"}
echo
python3 "$SKILLS_DIR/jobsearch/scripts/init.py"

echo
echo "Dépendances facultatives :"
check_cmd() {
  command -v "$1" >/dev/null \
    && printf "  %-12s OK\n" "$1" \
    || printf "  %-12s manquant (%s)  ->  %s\n" "$1" "$2" "$3"
}
check_cmd pdftotext "lecture des PDF" "apt install poppler-utils / brew install poppler"
if command -v soffice >/dev/null || command -v libreoffice >/dev/null; then
  printf "  %-12s OK\n" libreoffice
else
  printf "  %-12s manquant (pas de PDF)  ->  apt install libreoffice-writer / brew install --cask libreoffice\n" libreoffice
fi
check_cmd uv "LinkedIn et Indeed" "https://docs.astral.sh/uv/"
check_cmd npx "navigateur de candidature" "installer Node.js"

cat <<EOF

Navigateur de candidature (pour que Claude remplisse les formulaires) :
  claude mcp add candidature --scope user -- npx -y @playwright/mcp@latest --browser chrome --user-data-dir "$HOME/.config/jobsearch/navigateur"
  puis redémarrer Claude Code.

Prochaine étape : lancer Claude Code depuis ~/Documents/cv et dire « crée mon CV ».
EOF

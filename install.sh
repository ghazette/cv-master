#!/usr/bin/env bash
# Installe le skill CV pour Claude Code.
#   ./install.sh            installation globale dans ~/.claude/skills/cv
#   ./install.sh --project  installation locale dans ./.claude/skills/cv
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/cv"
DEST="$HOME/.claude/skills/cv"
[[ "${1:-}" == "--project" ]] && DEST="$PWD/.claude/skills/cv"
WORKSPACE="$HOME/Documents/cv"

echo "Source      : $SRC"
echo "Destination : $DEST"
echo "Workspace   : $WORKSPACE"
echo

if [[ -e "$DEST" ]]; then
  read -r -p "$DEST existe déjà. Le remplacer ? [o/N] " reply
  [[ "$reply" =~ ^[oOyY]$ ]] || { echo "Abandon."; exit 1; }
  rm -rf "$DEST"
fi

mkdir -p "$(dirname "$DEST")"
cp -r "$SRC" "$DEST"
echo "  skill installé"

mkdir -p "$WORKSPACE"
for pair in "cv-master.template.md:cv-master.md" "profil.template.md:profil.md"; do
  tpl="${pair%%:*}"; target="$WORKSPACE/${pair##*:}"
  if [[ -e "$target" ]]; then
    echo "  ${pair##*:} existe déjà, conservé"
  else
    cp "$DEST/assets/$tpl" "$target"
    echo "  ${pair##*:} créé"
  fi
done

echo
echo "Dépendances :"
python3 -c "import docx" 2>/dev/null \
  && echo "  python-docx    OK" \
  || echo "  python-docx    MANQUANT (obligatoire)  ->  pip install python-docx"
python3 -c "import lxml" 2>/dev/null \
  && echo "  lxml           OK" \
  || echo "  lxml           manquant (recommandé)   ->  pip install lxml"
command -v pdftotext >/dev/null \
  && echo "  pdftotext      OK" \
  || echo "  pdftotext      manquant (recommandé)   ->  apt install poppler-utils"
if command -v soffice >/dev/null || command -v libreoffice >/dev/null; then
  echo "  libreoffice    OK"
else
  echo "  libreoffice    manquant, pas de PDF    ->  apt install libreoffice-writer"
fi

echo
echo "Prochaine étape : remplir $WORKSPACE/cv-master.md,"
echo "ou lancer Claude Code et dire « aide-moi à remplir mon CV master »."

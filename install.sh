#!/usr/bin/env bash
# Installe le skill CV pour Claude Code, puis lance l'init.
#   ./install.sh                         installation globale dans ~/.claude/skills/cv
#   ./install.sh --project               installation locale dans ./.claude/skills/cv
#   ./install.sh --cv ~/mon-cv.pdf       importe le CV existant pendant l'init
# Toutes les options autres que --project sont transmises à cv/scripts/init.py
# (--workspace, --cv, --photo, --name, --title, --contact, --signature, --yes).
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/cv"
DEST="$HOME/.claude/skills/cv"
INIT_ARGS=()
for arg in "$@"; do
  if [[ "$arg" == "--project" ]]; then
    DEST="$PWD/.claude/skills/cv"
  else
    INIT_ARGS+=("$arg")
  fi
done

echo "Source      : $SRC"
echo "Destination : $DEST"
echo

CONFIG_BACKUP=""
if [[ -e "$DEST" ]]; then
  if [[ -t 0 ]]; then
    read -r -p "$DEST existe déjà. Le remplacer ? (ton workspace n'est pas touché) [o/N] " reply
    [[ "$reply" =~ ^[oOyY]$ ]] || { echo "Abandon."; exit 1; }
  else
    echo "$DEST existe déjà, remplacement (ton workspace n'est pas touché)"
  fi
  # la config pointe vers le workspace de l'utilisateur, on la garde
  [[ -f "$DEST/config.json" ]] && CONFIG_BACKUP="$(cat "$DEST/config.json")"
  rm -rf "$DEST"
fi

mkdir -p "$(dirname "$DEST")"
cp -r "$SRC" "$DEST"
[[ -n "$CONFIG_BACKUP" ]] && printf '%s\n' "$CONFIG_BACKUP" > "$DEST/config.json"
chmod +x "$DEST"/scripts/*.py
echo "  skill installé"

python3 -c "import docx" 2>/dev/null || {
  echo "  python-docx manquant, installation..."
  python3 -m pip install --user python-docx lxml \
    || echo "  échec : lance « pip install python-docx lxml » à la main"
}

echo
python3 "$DEST/scripts/init.py" ${INIT_ARGS[@]+"${INIT_ARGS[@]}"}

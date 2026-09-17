#!/usr/bin/env bash
# Install the Diet & Cheat carousel workflow as a Codex skill.
#   curl -fsSL https://raw.githubusercontent.com/abdullah-elbedwehy/diet-cheat-carousel-workflow/main/install.sh | bash
set -euo pipefail

REPO_URL="https://github.com/abdullah-elbedwehy/diet-cheat-carousel-workflow.git"
CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
DEST="$CODEX_HOME/skills/diet-cheat-carousel-workflow"

need() { command -v "$1" >/dev/null 2>&1 || { echo "ERROR: '$1' is required." >&2; exit 2; }; }
need git
need python3
need codex
[ "$(uname -s)" = "Darwin" ] || echo "WARN: export step uses macOS 'sips'. On other OS run generate.py --no-export." >&2

if [ -d "$DEST/.git" ]; then
  echo "Already installed at $DEST — updating instead."
  bash "$DEST/scripts/update.sh"
  exit 0
fi

mkdir -p "$CODEX_HOME/skills"
git clone --quiet "$REPO_URL" "$DEST"
chmod +x "$DEST"/scripts/*.py "$DEST"/scripts/*.sh
mkdir -p "$DEST/learnings/local"

echo "Installed → $DEST (version $(cat "$DEST/VERSION"))"
echo
if codex login status 2>&1 | grep -qi "logged in"; then
  echo "Codex login: OK"
else
  echo "Codex login: NOT logged in. Run: codex login"
fi
echo
echo "Open Codex in any folder and say:"
echo '  OLD. Slide 1: ... Slide 2: ...'
echo "Update later with: pull latest update"

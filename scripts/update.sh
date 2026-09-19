#!/usr/bin/env bash
# Pull the latest workflow version. Local learnings are gitignored and untouched.
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SKILL_DIR"

if [ ! -d .git ]; then
  echo "ERROR: $SKILL_DIR is not a git checkout. Reinstall with install.sh." >&2
  exit 2
fi

before="$(cat VERSION 2>/dev/null || echo unknown)"
before_sha="$(git rev-parse --short HEAD)"

if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "WARN: tracked files were modified locally. They will block a fast-forward pull:" >&2
  git status --short >&2
  echo "Run: git -C \"$SKILL_DIR\" stash   (or discard) then retry." >&2
  exit 3
fi

git fetch --quiet origin
if ! git pull --ff-only --quiet origin main; then
  echo "ERROR: fast-forward pull failed. Resolve manually in $SKILL_DIR" >&2
  exit 4
fi

after="$(cat VERSION 2>/dev/null || echo unknown)"
after_sha="$(git rev-parse --short HEAD)"

if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi
.venv/bin/python -m pip install --quiet -r requirements.txt

if [ "$before_sha" = "$after_sha" ]; then
  echo "Already up to date — version $after ($after_sha)"
  exit 0
fi

echo "Updated $before ($before_sha) → $after ($after_sha)"
echo
echo "Changes:"
git log --oneline "$before_sha..$after_sha"
echo
echo "Shared lessons now active:"
python3 scripts/learn.py list --rules-only | sed 's/^/  /' || true

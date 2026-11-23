#!/usr/bin/env bash
# Formatting and lint checks (run inside `nix develop`).
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== clang-format"
git ls-files -z '*.c' '*.h' | xargs -0 clang-format --dry-run --Werror
echo "== ruff"
ruff check .
ruff format --check .
echo "== nixfmt"
git ls-files -z '*.nix' | xargs -0 nixfmt --check
echo "== actionlint"
actionlint
echo "lint OK"

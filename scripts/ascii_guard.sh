#!/usr/bin/env bash
set -euo pipefail

found=0

while IFS= read -r -d '' file; do
  if LC_ALL=C grep -n '[^ -~[:space:]]' "$file" >/tmp/ascii_guard_match.txt; then
    echo "Non-ASCII characters found in $file"
    cat /tmp/ascii_guard_match.txt
    found=1
  fi
done < <(
  find . -type f \
    \( -name '*.py' \
      -o -name '*.md' \
      -o -name '*.toml' \
      -o -name '*.yml' \
      -o -name '*.yaml' \
      -o -name '*.sh' \
      -o -name 'Dockerfile' \
      -o -name '.env.example' \) \
    -not -path './.git/*' \
    -not -path './.venv/*' \
    -not -path './.cache/*' \
    -not -path './frontend/node_modules/*' \
    -not -path './frontend/dist/*' \
    -not -path '*/__pycache__/*' \
    -not -path './.pytest_cache/*' \
    -print0
)

if [[ "$found" -ne 0 ]]; then
  exit 1
fi

echo "ASCII guard passed"

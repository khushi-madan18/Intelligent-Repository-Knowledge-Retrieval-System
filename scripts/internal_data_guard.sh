#!/usr/bin/env bash
set -euo pipefail

found=0

if [[ -d "_internal" ]]; then
  while IFS= read -r -d '' file; do
    if [[ "$file" != "_internal/PROJECT_CONTEXT.md" ]]; then
      echo "Internal-only file is not allowed in commits: $file"
      found=1
    fi
  done < <(find _internal -type f -print0)
fi

if [[ "$found" -ne 0 ]]; then
  exit 1
fi

echo "Internal data guard passed"


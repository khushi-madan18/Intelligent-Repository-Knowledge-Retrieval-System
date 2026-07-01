#!/usr/bin/env bash
set -euo pipefail

found=0

for file in "$@"; do
  [[ -f "$file" ]] || continue

  if LC_ALL=C grep -n '[[:blank:]]$' "$file" >/tmp/trailing_whitespace_match.txt; then
    echo "Trailing whitespace found in $file"
    cat /tmp/trailing_whitespace_match.txt
    found=1
  fi
done

if [[ "$found" -ne 0 ]]; then
  exit 1
fi

exit 0


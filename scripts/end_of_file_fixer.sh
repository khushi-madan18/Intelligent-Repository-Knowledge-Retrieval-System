#!/usr/bin/env bash
set -euo pipefail

status=0

for file in "$@"; do
  [[ -f "$file" ]] || continue
  [[ -s "$file" ]] || continue

  if [[ "$(tail -c 1 "$file")" != "" ]]; then
    printf '\n' >> "$file"
    echo "Fixed missing end-of-file newline: $file"
    status=1
  fi
done

exit "$status"


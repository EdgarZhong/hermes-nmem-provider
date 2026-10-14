#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ ! -f "$HERE/install_personal.py" ]]; then
  echo "Clone EdgarZhong/hermes-nmem-provider and run this script from that checkout." >&2
  exit 1
fi
exec python3 "$HERE/install_personal.py" --home "${HERMES_HOME:-$HOME/.hermes}" --apply "$@"

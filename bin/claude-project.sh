#!/usr/bin/env bash
set -euo pipefail
cd /var/www/komunal-dom_ru

ARGS=("$@")
HAS_PERMISSION_MODE=0
for arg in "${ARGS[@]}"; do
  if [[ "$arg" == --permission-mode* ]]; then
    HAS_PERMISSION_MODE=1
    break
  fi
done

CMD=(claude
  --plugin-dir /var/www/komunal-dom_ru/plugins/komunal-dom-ui-ops
  --plugin-dir /var/www/komunal-dom_ru/plugins/frontend-design
  --plugin-dir /var/www/komunal-dom_ru/plugins/hookify)

if [[ $HAS_PERMISSION_MODE -eq 0 ]]; then
  CMD+=(--permission-mode dontAsk)
fi

exec "${CMD[@]}" "${ARGS[@]}"

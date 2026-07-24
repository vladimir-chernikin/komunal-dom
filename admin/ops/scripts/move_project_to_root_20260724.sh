#!/usr/bin/env bash
set -euo pipefail

source_path=/var/www/Kom_Dom_B
target_path=/Kom_Dom_B
bundle_path=/tmp/kom-dom-b-deploy.bundle
backup_path=/var/www/komunal-dom_ru/old/20260724_kom_dom_b_root_move

if [[ "$(realpath -m "$source_path")" != "/var/www/Kom_Dom_B" ]]; then
  echo "Unexpected source path" >&2
  exit 1
fi
if [[ "$(realpath -m "$target_path")" != "/Kom_Dom_B" ]]; then
  echo "Unexpected target path" >&2
  exit 1
fi
if [[ ! -d "$source_path/.git" ]]; then
  echo "Source checkout not found" >&2
  exit 1
fi
if [[ -e "$target_path" ]]; then
  echo "Target already exists" >&2
  exit 1
fi
if [[ ! -f "$bundle_path" ]]; then
  echo "Deployment bundle not found" >&2
  exit 1
fi
if [[ -n "$(git -C "$source_path" status --porcelain --untracked-files=no)" ]]; then
  echo "Tracked production files are dirty" >&2
  exit 1
fi

install -d -m 0700 "$backup_path"
tar \
  --exclude=venv \
  --exclude=.git \
  --exclude=media \
  -czf "$backup_path/Kom_Dom_B.before.tar.gz" \
  -C /var/www Kom_Dom_B
install -m 0600 "$source_path/.env" "$backup_path/Kom_Dom_B.env.before"
systemctl cat kom-dom-b-api.service \
  > "$backup_path/kom-dom-b-api.service.before"
cp -a \
  /etc/nginx/sites-available/aspect.komunal-dom.ru \
  "$backup_path/aspect.komunal-dom.ru.nginx.before"

git -C "$source_path" fetch \
  "$bundle_path" \
  HEAD:refs/remotes/bundle/deploy
git -C "$source_path" merge --ff-only refs/remotes/bundle/deploy

if [[ -f "$source_path/var/a-env-reference-20260722" ]]; then
  mv \
    "$source_path/var/a-env-reference-20260722" \
    "$backup_path/a-env-reference-20260722"
  chmod 0600 "$backup_path/a-env-reference-20260722"
fi
rmdir "$source_path/var" 2>/dev/null || true

systemctl stop kom-dom-b-api.service
mv "$source_path" "$target_path"
install -m 0644 \
  "$target_path/admin/ops/systemd/kom-dom-b-api.service" \
  /etc/systemd/system/kom-dom-b-api.service
systemctl daemon-reload
systemctl start kom-dom-b-api.service

test ! -e "$source_path"
test -d "$target_path/.git"
systemctl is-active --quiet kom-dom-b-api.service
echo "Kom_Dom_B moved to /Kom_Dom_B"
echo "Backup: $backup_path"

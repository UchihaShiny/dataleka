#!/usr/bin/env bash
# Publish a clean, scanned source snapshot; preserve the original repo, index and remotes.
set -euo pipefail
cd "$(dirname "$0")/.."
if ! command -v gh >/dev/null && [ -x bin/github-cli/gh_2.104.0_linux_amd64/bin/gh ]; then
  export PATH="$PWD/bin/github-cli/gh_2.104.0_linux_amd64/bin:$PATH"
fi
command -v gh >/dev/null || { echo 'Cần GitHub CLI (gh) từ https://cli.github.com/ và gh auth login.' >&2; exit 1; }
gh auth status >/dev/null 2>&1 || { echo 'Hãy chạy gh auth login bằng tài khoản GitHub cá nhân trước.' >&2; exit 1; }
.venv/bin/python scripts/prepare_release.py
publish_dir=$(mktemp -d -t dataleka-publish-XXXXXXXX)
.venv/bin/python - "$publish_dir" <<'PY'
import sys,zipfile
with zipfile.ZipFile('data/release/dataleka-source.zip') as archive:
    archive.extractall(sys.argv[1])
PY
publish_source="$publish_dir/dataleka"
account_login=$(gh api user --jq '.login')
account_id=$(gh api user --jq '.id')
git -C "$publish_source" init -b main
git -C "$publish_source" add .
git -C "$publish_source" -c user.name="$account_login" -c user.email="$account_id+$account_login@users.noreply.github.com" commit -m 'Build DEERLYS analytics application'
gh repo create "$account_login/dataleka" --private --source "$publish_source" --remote origin --push
local_sha=$(git -C "$publish_source" rev-parse HEAD)
remote_sha=$(git -C "$publish_source" ls-remote origin refs/heads/main | cut -f1)
[ "$local_sha" = "$remote_sha" ] || { echo 'Commit trên GitHub chưa khớp; không báo upload thành công.' >&2; exit 1; }
gh repo view "$account_login/dataleka" --json nameWithOwner,url,isPrivate --jq 'if .isPrivate then .url else error("Repository is not private") end'
echo "Verified main commit: $remote_sha"
echo "Bản nguồn đã đẩy được giữ tại: $publish_source"
echo 'Tiếp theo mở https://dash.cloudflare.com/ → Workers & Pages. Xem docs/cloudflare-handoff.md trước khi deploy.'

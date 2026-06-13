#!/usr/bin/env sh
set -eu

root="$(cd "$(dirname "$0")/.." && pwd)"
src="$root/scripts/git-hooks/pre-commit"
dest="$root/.git/hooks/pre-commit"

mkdir -p "$(dirname "$dest")"
cp "$src" "$dest"
chmod +x "$dest"
echo "Installed pre-commit hook -> $dest"
echo "Blocks: rawdata/, data/crawl/, .env*, *.pem, *.key"

#!/usr/bin/env bash
set -e

echo "=== Cross-Strait Signal — Deploy ==="

# 1. Build frontend
echo ""
echo "--- Building frontend ---"
cd "$(dirname "$0")/frontend"
npm run build
cd ..

# 2. Push to GitHub
echo ""
echo "--- Pushing to GitHub ---"
git push

# 3. Pull and restart on server
echo ""
echo "--- Deploying to server (password prompt incoming) ---"
ssh -t root@217.174.245.116 "cd /var/www/cross-strait-signal && ./deploy.sh"

echo ""
echo "=== Deploy complete ==="

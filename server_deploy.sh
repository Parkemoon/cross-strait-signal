#!/usr/bin/env bash
# Runs on the server. Called by the local deploy.sh via SSH.
set -e

cd /var/www/cross-strait-signal

echo "--- Pulling latest code ---"
git pull

echo "--- Building frontend ---"
cd frontend
npm run build
cd ..

echo "--- Restarting backend ---"
systemctl restart cross-strait-signal

echo "--- Done ---"

#!/bin/bash
# Draai als gewone gebruiker (niet als root): bash deploy/install.sh   (idempotent)
# DNS: geen record nodig (wildcard *.hydrargyrum.be).
set -euo pipefail
D=~/work/minimaple-live/deploy; TS=$(date +%Y%m%d-%H%M%S); B=~/nginx-backup-$TS
mkdir -p "$B"; sudo cp -a /etc/nginx/sites-available "$B/"; sudo cp -a /etc/nginx/sites-enabled "$B/"; echo "backup: $B"
# 1. app als user-service
mkdir -p ~/.config/systemd/user; cp "$D/maple.service" ~/.config/systemd/user/
systemctl --user daemon-reload; systemctl --user enable --now maple.service; sleep 1
curl -fs http://127.0.0.1:8750/ >/dev/null && echo "app ok"
# 2. certificaat (indien nog niet aanwezig): eerst tijdelijk enkel poort 80
if ! sudo test -e /etc/letsencrypt/live/maple.hydrargyrum.be/fullchain.pem; then
  printf 'server { listen 80; listen [::]:80; server_name maple.hydrargyrum.be; location /.well-known/acme-challenge/ { root /var/www/html; } location / { return 404; } }\n' | sudo tee /etc/nginx/sites-available/maple.conf >/dev/null
  sudo ln -sf /etc/nginx/sites-available/maple.conf /etc/nginx/sites-enabled/maple.conf
  sudo nginx -t && sudo systemctl reload nginx
  sudo certbot certonly --webroot -w /var/www/html -d maple.hydrargyrum.be
fi
# 3. echte vhost
sudo cp "$D/maple.conf" /etc/nginx/sites-available/maple.conf
sudo ln -sf /etc/nginx/sites-available/maple.conf /etc/nginx/sites-enabled/maple.conf
if sudo nginx -t; then sudo systemctl reload nginx; echo "klaar: https://maple.hydrargyrum.be"
else sudo rm -f /etc/nginx/sites-enabled/maple.conf; echo "nginx -t faalde; maple-vhost weer uitgeschakeld (backup: $B)"; exit 1; fi

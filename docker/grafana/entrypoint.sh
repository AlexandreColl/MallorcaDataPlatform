#!/bin/sh
# Grafana with optional notifications: the Telegram contact point is provisioned only when its token and chat id are
# set. Grafana refuses to start with a contact point that has no token, so it cannot always be in the provisioning
# folder (the E2E and a fresh clone run without one).
set -eu

src=/etc/grafana/provisioning
dst=/tmp/provisioning
rm -rf "$dst"
cp -r "$src" "$dst"
if [ -n "${TELEGRAM_BOT_TOKEN:-}" ] && [ -n "${TELEGRAM_CHAT_ID:-}" ]; then
  cp /etc/mdp/notifications/telegram.yml "$dst/alerting/telegram.yml"
  echo "mdp: alert notifications go to Telegram"
else
  echo "mdp: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set, alerts are only shown in Grafana"
fi
export GF_PATHS_PROVISIONING="$dst"
exec /run.sh "$@"

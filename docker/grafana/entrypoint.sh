#!/bin/sh
# Grafana with optional notifications: the Telegram contact point is provisioned only when its token and chat id are
# set. Grafana refuses to start with a contact point that has no token, so it cannot always be in the provisioning
# folder (the E2E and a fresh clone run without one).
set -eu

src=/etc/grafana/provisioning
dst=/tmp/provisioning
rm -rf "$dst"
cp -r "$src" "$dst"

token=${TELEGRAM_BOT_TOKEN:-}
chat=${TELEGRAM_CHAT_ID:-}
if [ -n "$token" ] && [ -n "$chat" ]; then
  # Check the shapes before they go into YAML: a bot token is <digits>:<letters, digits, _ and ->, a chat id an
  # integer (negative for groups).
  case "$token" in *[!0-9A-Za-z:_-]* | [!0-9]*) echo "mdp: TELEGRAM_BOT_TOKEN is not a bot token" >&2; exit 1 ;; esac
  case "$chat" in -*[!0-9]* | [!-0-9]* | *[!-0-9]*) echo "mdp: TELEGRAM_CHAT_ID is not a number" >&2; exit 1 ;; esac
  sed -e "s|__TELEGRAM_BOT_TOKEN__|$token|" -e "s|__TELEGRAM_CHAT_ID__|$chat|" \
    /etc/mdp/notifications/telegram.yml > "$dst/alerting/telegram.yml"
  echo "mdp: alert notifications go to Telegram"
else
  echo "mdp: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set, alerts are only shown in Grafana"
fi
export GF_PATHS_PROVISIONING="$dst"
exec /run.sh "$@"

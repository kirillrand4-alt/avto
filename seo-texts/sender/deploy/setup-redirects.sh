#!/usr/bin/env bash
# Установщик nginx-редиректора доменов-двойников — ОДНОЙ командой.
# Ставит/использует nginx, кладёт конфиг 301-редиректов, выпускает
# Let's Encrypt на доехавшие домены, включает https, ставит автопродление.
# Идемпотентен: повторный запуск безопасен (до-выпускает серты по мере
# доезда A-записей). Чужие сайты на сервере НЕ трогает — только наши
# server_name в отдельном conf.d-файле.
#
# Запуск на сервере (Linux, root/sudo, порты 80+443 наружу):
#   sudo bash setup-redirects.sh
#
# Требует рядом файл redirects-nginx.conf (сгенерирован из config/domains.json).
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
CONF_SRC="$HERE/redirects-nginx.conf"
CONF_DST="/etc/nginx/conf.d/rusprom-redirects.conf"
ACME_ROOT="/var/www/acme"
LE_LIVE="/etc/letsencrypt/live"

say() { printf "\n\033[1;34m==> %s\033[0m\n" "$*"; }
warn() { printf "\033[1;33m[!] %s\033[0m\n" "$*"; }
die() { printf "\033[1;31m[x] %s\033[0m\n" "$*" >&2; exit 1; }

[ "$(id -u)" = 0 ] || die "запусти под root: sudo bash setup-redirects.sh"
[ -f "$CONF_SRC" ] || die "нет $CONF_SRC (положи рядом redirects-nginx.conf)"

# --- список доменов из самого конфига (server_name блока 80) ---------------
mapfile -t NAMES < <(grep -oE '[a-z0-9.-]+\.ru' "$CONF_SRC" | sort -u)
[ "${#NAMES[@]}" -gt 0 ] || die "не нашёл доменов в конфиге"
say "Домены из конфига (${#NAMES[@]}): ${NAMES[*]}"

MYIP="$(curl -4 -sS --max-time 10 ifconfig.me 2>/dev/null || true)"
[ -n "$MYIP" ] && say "IP этого сервера: $MYIP (A-записи доменов должны вести сюда)"

# --- 1) nginx + certbot ----------------------------------------------------
say "1/6 Проверяю nginx и certbot"
if ! command -v nginx >/dev/null; then
  say "Ставлю nginx"
  apt-get update -qq && apt-get install -y -qq nginx
fi
if ! command -v certbot >/dev/null; then
  say "Ставлю certbot"
  apt-get install -y -qq certbot
fi
mkdir -p "$ACME_ROOT"

# --- 2) кладём конфиг, блок 443 пока комментируем --------------------------
say "2/6 Кладу конфиг редиректов (443 временно выключен до серта)"
cp "$CONF_SRC" "$CONF_DST"
# закомментировать блок 'server { listen 443 ...}' целиком, если серта ещё нет
FIRST="${NAMES[0]}"
if [ ! -s "$LE_LIVE/$FIRST/fullchain.pem" ]; then
  python3 - "$CONF_DST" <<'PY'
import re, sys
p = sys.argv[1]
s = open(p, encoding="utf-8").read()
# найти последний server{...} (443) и закомментировать построчно
idx = s.rfind("server {\n    listen 443")
if idx != -1:
    head, tail = s[:idx], s[idx:]
    tail = "\n".join(("# " + ln) if ln.strip() else ln for ln in tail.splitlines())
    open(p, "w", encoding="utf-8").write(head + tail + "\n")
PY
fi
nginx -t && systemctl reload nginx
say "HTTP-редирект поднят. Проверь: curl -I http://$FIRST/"

# --- 3) фаервол (если ufw активен) -----------------------------------------
if command -v ufw >/dev/null && ufw status | grep -q "Status: active"; then
  say "3/6 Открываю 80,443 в ufw"; ufw allow 80,443/tcp || true
else
  say "3/6 ufw не активен — пропускаю (проверь фаервол хостера: 80,443 открыты)"
fi

# --- 4) DNS-preflight: какие домены реально смотрят на этот сервер ----------
say "4/6 Проверяю, какие домены уже указывают на этот сервер (A-запись)"
READY=(); NOTREADY=()
for d in "${NAMES[@]}"; do
  # только apex, без www — www проверит certbot сам
  case "$d" in www.*) continue;; esac
  a="$(curl -sS --max-time 8 "https://dns.google/resolve?name=$d&type=A" \
       | python3 -c "import json,sys;print(''.join(x.get('data','') for x in json.load(sys.stdin).get('Answer',[])))" 2>/dev/null || true)"
  if [ -n "$MYIP" ] && echo "$a" | grep -q "$MYIP"; then
    READY+=("$d" "www.$d")
  else
    NOTREADY+=("$d"); warn "$d → A=$a (ждём $MYIP)"
  fi
done
say "Готовы к серту: ${#READY[@]} имён. Не доехали: ${NOTREADY[*]:-нет}"
[ "${#READY[@]}" -gt 0 ] || die "ни один домен не указывает на $MYIP — сначала A-записи, потом перезапусти скрипт"

# --- 5) выпуск сертификата (webroot) на доехавшие --------------------------
say "5/6 Выпускаю Let's Encrypt на доехавшие домены"
DARGS=(); for n in "${READY[@]}"; do DARGS+=(-d "$n"); done
EMAIL="${LE_EMAIL:-admin@${FIRST}}"
certbot certonly --webroot -w "$ACME_ROOT" \
  --non-interactive --agree-tos -m "$EMAIL" --expand \
  --cert-name "$FIRST" "${DARGS[@]}" \
  || die "certbot не смог — проверь, что 80 порт доступен снаружи и A-записи доехали"

# --- 6) включаем https-блок и автопродление --------------------------------
say "6/6 Включаю https-редирект и автопродление"
cp "$CONF_SRC" "$CONF_DST"   # свежая копия с раскомментированным 443
nginx -t && systemctl reload nginx
mkdir -p /etc/letsencrypt/renewal-hooks/deploy
cat > /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh <<'H'
#!/bin/sh
systemctl reload nginx
H
chmod +x /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh

say "ГОТОВО. Проверь: curl -I https://$FIRST/  → 301 на основной сайт"
if [ "${#NOTREADY[@]}" -gt 0 ]; then
  warn "Домены ${NOTREADY[*]} ещё не доехали в DNS."
  warn "Когда добавишь их A-записи на $MYIP — просто перезапусти этот скрипт,"
  warn "он до-выпустит серты и на них (idempotent)."
fi

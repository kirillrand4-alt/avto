#!/bin/bash
# Отдать владельцу всё готовое, чего он ещё не видел.
#
# ЗАЧЕМ ФАЙЛ, А НЕ ПАМЯТЬ. Список отданных страниц я держал в голове,
# и к шестнадцатой он перестал туда помещаться. Журнал otdano.txt -
# единственный способ не прислать одно и то же дважды после того,
# как контекст сессии свернётся.
set -u
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"
touch otdano.txt
python3 - <<'PY' > /tmp/k_otdache.txt
import json, os
otdano = set(open('otdano.txt', encoding='utf-8').read().split())
vidno, itog = set(), []
for l in open('konveyer.jsonl', encoding='utf-8'):
    try: z = json.loads(l)
    except Exception: continue
    if z.get('itog') not in ('чисто', 'нужен разбор') or not z.get('fajl'):
        continue
    p = os.path.join('statyi-final', z['fajl'])
    if z['slug'] in otdano or z['slug'] in vidno or not os.path.exists(p):
        continue
    vidno.add(z['slug']); itog.append((z['slug'], p))
for s, p in itog:
    print(f'{s}\t{p}')
PY
while IFS=$'\t' read -r slug put; do
    [ -z "${put:-}" ] && continue
    if bash ../server/drop_client.sh up "$put" > /dev/null 2>&1; then
        echo "$slug" >> otdano.txt
        echo "ОТДАНО $put"
    else
        echo "НЕ УШЛО $put"
    fi
done < /tmp/k_otdache.txt

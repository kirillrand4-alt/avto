#!/bin/bash
# Пакет фронта панели рассылки: web/dist -> zip -> дроп.
#
# Осторожность не лишняя: 26.07 панель легла именно из-за рассинхрона —
# index.html ссылался на файлы бандла, которых в пакете не было. Поэтому здесь
# ПРОВЕРКА: каждый /assets/... из index.html обязан существовать в dist,
# иначе пакет не собирается.
set -eu
WEB="/home/user/avto/seo-texts/sender/web"
DIST="$WEB/dist"
OUT="${1:-/tmp/web-dist-update.zip}"

[ -f "$DIST/index.html" ] || { echo "нет $DIST/index.html — сначала npm run build"; exit 1; }

echo "== проверка ссылок index.html =="
miss=0
while read -r ref; do
  [ -n "$ref" ] || continue
  f="$DIST${ref}"
  if [ -f "$f" ]; then
    echo "  ок: $ref ($(stat -c%s "$f") б)"
  else
    echo "  НЕТ ФАЙЛА: $ref"
    miss=$((miss + 1))
  fi
done < <(grep -oE '/assets/[A-Za-z0-9._-]+' "$DIST/index.html" | sort -u)

if [ "$miss" -gt 0 ]; then
  echo "ОТКАЗ: index.html ссылается на $miss отсутствующих файлов — это ровно тот"
  echo "       сценарий, из-за которого панель легла 26.07. Пакет не собран."
  exit 2
fi

# .map не кладём: 1.2 МБ мёртвого веса на боевой панели во внутренней сети
echo "== сборка пакета =="
rm -f "$OUT"
(cd "$DIST" && zip -q -r "$OUT" . -x '*.map')
echo "  пакет: $OUT ($(stat -c%s "$OUT") б)"
(cd "$DIST" && zip -sf "$OUT") | tail -n +2 | head -10

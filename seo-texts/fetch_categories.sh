#!/bin/bash
cd /tmp/claude-0/-home-user-avto/bcce55cd-293a-515c-9700-ae71a77daa5a/scratchpad
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0"
n=0
tail -n +2 inventory/categories-registry.csv | while IFS=';' read -r url rest; do
  n=$((n+1))
  slug=$(echo "$url" | sed 's|https://prokompressor.ru/catalog/||; s|/$||; s|/|__|g')
  [ -z "$slug" ] && slug=root
  out="inventory/pages/$slug.html"
  [ -s "$out" ] && continue
  code=$(curl -sS -m 40 -A "$UA" -w '%{http_code}' -o "$out" "$url" 2>/dev/null)
  # кэш-баг сайта: проверяем canonical, при несовпадении перекачиваем 1 раз
  if [ "$code" = "200" ] && ! grep -q "canonical\" href=\"$url" "$out" 2>/dev/null; then
    sleep 1
    curl -sS -m 40 -A "$UA" -o "$out" "$url" 2>/dev/null
  fi
  [ "$code" != "200" ] && echo "$code $url" >> inventory/fetch-errors.log
  [ $((n % 100)) -eq 0 ] && echo "скачано $n"
  sleep 0.4
done
echo "ОБХОД ЗАВЕРШЁН: $(ls inventory/pages | wc -l) файлов, ошибок: $(wc -l < inventory/fetch-errors.log 2>/dev/null || echo 0)"

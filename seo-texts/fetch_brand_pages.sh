#!/bin/bash
cd /tmp/claude-0/-home-user-avto/bcce55cd-293a-515c-9700-ae71a77daa5a/scratchpad
mkdir -p kb/brand-pages-raw
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0"
while read url; do
  slug=$(echo "$url" | sed 's|.*/brands/||; s|/$||')
  [ -z "$slug" ] && continue
  out="kb/brand-pages-raw/$slug.html"
  [ -s "$out" ] && continue
  curl -sS -m 40 -A "$UA" "$url" -o "$out" 2>/dev/null
  sleep 0.4
done < brand-info-urls.txt
echo "СКАЧАНО: $(ls kb/brand-pages-raw/*.html 2>/dev/null | wc -l) страниц"

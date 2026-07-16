#!/bin/bash
cd /tmp/claude-0/-home-user-avto/bcce55cd-293a-515c-9700-ae71a77daa5a/scratchpad
mkdir -p kb/manuf-raw
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0"
python3 -c "
import json
r=json.load(open('kb/brand-pages-facts.json'))
# известные точно (high) не трогаем; для родного/дружественных берём ВЕРНЫЕ домены из фактбазы
override={'enger':'enger-air.ru','berg':'berg-air.ru','dali':'dali-kompressor.ru','hansmann':'hansmann.ru'}
for x in r:
    if x.get('domain_confidence')=='high': continue
    d=override.get(x['_slug']) or x.get('official_domain_guess','')
    if d: print(x['_slug'], d.replace('https://','').replace('http://','').split('/')[0])
" > /tmp/claude-0/domains2.txt
while read slug domain; do
  out="kb/manuf-raw/$slug.html"
  [ -s "$out" ] && [ $(wc -c < "$out") -gt 8000 ] && continue
  curl -sS -m 12 -A "$UA" -L -o "$out" "https://$domain/" 2>/dev/null
  sz=$(wc -c < "$out" 2>/dev/null || echo 0)
  [ "$sz" -le 8000 ] && echo "НЕ РЕЗОЛВ: $slug ($domain) ${sz}b" && rm -f "$out"
done < /tmp/claude-0/domains2.txt
echo "ГОТОВО: живых сайтов $(ls kb/manuf-raw/*.html 2>/dev/null | wc -l)"

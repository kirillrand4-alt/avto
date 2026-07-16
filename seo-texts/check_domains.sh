#!/bin/bash
cd /tmp/claude-0/-home-user-avto/bcce55cd-293a-515c-9700-ae71a77daa5a/scratchpad
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0"
python3 -c "
import json
r=json.load(open('kb/brand-pages-facts.json'))
for x in r:
    d=x.get('official_domain_guess','')
    if d and x.get('domain_confidence')!='high': print(x['_slug'], d)
" > /tmp/claude-0/domains.txt
mkdir -p kb/manuf-raw
while read slug domain; do
  domain=$(echo "$domain" | sed 's|https\?://||; s|/.*||')
  code=$(curl -sS -m 20 -A "$UA" -L -o "kb/manuf-raw/$slug.html" -w '%{http_code}' "https://$domain/" 2>/dev/null)
  size=$(wc -c < "kb/manuf-raw/$slug.html" 2>/dev/null)
  echo "$slug | $domain | HTTP $code | ${size}b"
done < /tmp/claude-0/domains.txt

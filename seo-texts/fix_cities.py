# -*- coding: utf-8 -*-
import json, re, subprocess, html as H

recs = json.load(open('projects-index.json'))

CITY_RE = re.compile(r'(?:г\.\s*|город[ае]?\s+|в\s+городе\s+|пос\.\s*)([А-ЯЁ][а-яё]+(?:-[А-ЯЁа-яё][а-яё]+)*(?:\s[А-ЯЁ][а-яё]+)?)')
STOP1 = {'Заказчик','Компания','Недавно','Для','Приятно','Можно','Оборудование','Дата','Мы','Наш','Наша','Клиент','Так','Однако','Сегодня','После','Также','Кроме','Оно','Он','Она'}

def guess_city(text):
    cands = CITY_RE.findall(text or '')
    cands = [c for c in cands if c.split()[0] not in STOP1 and c.split('-')[0] not in STOP1]
    return cands[0] if cands else ''

def parse(u, src):
    if not src or len(src) < 5000:
        return {'url': u, 'error': 'empty'}
    rec = {'url': u, 'category': u.split('/')[4]}
    m = re.search(r'<title>(.*?)</title>', src);  rec['title'] = H.unescape(m.group(1)) if m else ''
    m = re.search(r'<h1[^>]*>(.*?)</h1>', src, re.S)
    rec['h1'] = H.unescape(re.sub(r'<[^>]+>','',m.group(1)).strip()) if m else ''
    i = src.find('class="properties"')
    if i > 0:
        frag = src[i:i+12000]
        frag = re.sub(r'<script.*?</script>','',frag,flags=re.S)
        txt = re.sub(r'<[^>]+>','|',frag)
        txt = H.unescape(re.sub(r'\|+','|',txt))
        for field, pat in [('date', r'Дата проекта\|?:?\|?\s*([^|]{2,40})'),
                           ('sphere', r'Сфера\|([^|]{2,60})'),
                           ('brand', r'Производитель\|([^|]{2,60})'),
                           ('equipment', r'Оборудование:?\|([^|]{3,300})'),
                           ('client', r'Заказчик\|?:?\|?\s*([^|]{2,120})'),
                           ('service', r'Услуга\|?:?\|?\s*([^|]{2,80})')]:
            mm = re.findall(pat, txt)
            rec[field] = mm[-1].strip().strip(':').strip() if mm else ''
        j = txt.find('Услуга'); k = txt.find('|Товары|')
        if j>0:
            nar = txt[j:k if k>j else j+3000]
            nar = re.sub(r'^[^|]*\|','',nar)
            rec['narrative'] = nar.replace('|',' ').strip()[:2000]
    rec['city_guess'] = guess_city((rec.get('narrative','') or '')+' '+(rec.get('client','') or ''))
    return rec

fixed = 0
for r in recs:
    if r.get('error'): continue
    new = guess_city((r.get('narrative','') or '') + ' ' + (r.get('client','') or ''))
    if new != r.get('city_guess',''):
        r['city_guess'] = new; fixed += 1

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36"
for r in recs:
    if r.get('error'):
        u = r['url']
        out = subprocess.run(['curl','-sS','--max-time','40','-A',UA,u], capture_output=True, text=True)
        nr = parse(u, out.stdout)
        r.clear(); r.update(nr)

json.dump(recs, open('projects-index.json','w'), ensure_ascii=False, indent=1)
ok = [r for r in recs if not r.get('error')]
have_city = sum(1 for r in ok if r.get('city_guess'))
print(f'город исправлен у {fixed}; итого city: {have_city}/{len(ok)}; ошибок: {sum(1 for r in recs if r.get("error"))}')
from collections import Counter
print(Counter(r['city_guess'] for r in ok if r.get('city_guess')).most_common(12))

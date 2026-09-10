# -*- coding: utf-8 -*-
"""Фаза 5.1б. Оценка полноты: перекрытия независимых источников прямых фактов (Линкольн-Петерсен, поправка Чепмена)
и покрытие по стратам ОКВЭД-раздел × город. Пишет AK-POLNOTA.md на дроп."""
import os, sys, re, json, sqlite3, collections, urllib.request, time
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
AK = r'C:\sender\_ops\ak'; DB = os.path.join(AK, 'AK-BAZA.sqlite')
c = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
SLAB = ('холодильный компрессор', 'ОПО (иное)')
src = collections.defaultdict(set)
for inn, ist, vid, tip, sila in c.execute("select inn, istochnik, vid_fakta, tip, sila from fakty where sila>=3 and inn like '22%'"):
    if tip in SLAB: continue
    k = {'monitor-pb.ru': 'ЭПБ/ОПО', 'zakupki.gov.ru': 'ЕИС', 'trudvsem.ru': 'вакансии', 'hh.ru': 'вакансии', 'etpgpb.ru': 'ГПБ'}.get(ist, ist)
    src[k].add(inn)
out = ['# Оценка полноты списка предприятий края с КО', '', f'Дата: {time.strftime("%Y-%m-%d %H:%M")}', '', '## 1. Независимые источники прямых фактов (ИНН с сильным фактом)', '']
for k, v in sorted(src.items(), key=lambda x: -len(x[1])): out.append(f'- {k}: {len(v)}')
vse = set().union(*src.values()) if src else set()
out += ['', f'Объединение: {len(vse)} ИНН', '', '## 2. Линкольн-Петерсен по парам (оценка числа предприятий с сильным прямым фактом, которое дали бы оба источника при полном обходе)', '',
        '| пара | n1 | n2 | пересечение | оценка N (Чепмен) | собрано в объединении | доля |', '|---|---:|---:|---:|---:|---:|---:|']
keys = [k for k in src if len(src[k]) >= 10]
for i in range(len(keys)):
    for j in range(i + 1, len(keys)):
        a, b = src[keys[i]], src[keys[j]]; m = len(a & b)
        N = (len(a) + 1) * (len(b) + 1) / (m + 1) - 1
        out.append(f'| {keys[i]} × {keys[j]} | {len(a)} | {len(b)} | {m} | {N:.0f} | {len(a | b)} | {len(a | b) / N:.0%} |')
out += ['', 'Оговорка: источники не независимы (крупное предприятие чаще и в ЭПБ, и в ЕИС), поэтому оценка N занижает истинное число; малое пересечение при больших n означает, что списки разные и полнота низкая.', '']
# страты
KLASS = {}
for inn, kl, ok, gor, adr in c.execute("select inn, klass, okved_osn, gorod, adres from predpriyatiya where inn like '22%' or adres like '%Алтайский край%'"):
    KLASS[inn] = (kl or 'не оценено', (ok or '')[:2], (gor or '').upper()[:20])
silnye = set(vse)
strat = collections.defaultdict(collections.Counter)
for inn, (kl, sek, gor) in KLASS.items():
    k = 'доказано' if inn in silnye else ('косвенно' if kl.startswith('косвенно') else 'кандидат' if kl.startswith('кандидат') else 'не наше' if kl == 'не наше' else 'не оценено')
    strat[sek][k] += 1
CAND = re.compile(r'^(0[1-9]|1\d|2\d|3[0-9]|4[1-3]|49|52)$')
out += ['## 3. Покрытие по разделам ОКВЭД (производственные разделы)', '', '| раздел | юрлиц | доказано | косвенно | кандидат | не наше | не оценено | доля доказано+косвенно среди оценённых |', '|---|---:|---:|---:|---:|---:|---:|---:|']
nizko = []
for sek in sorted(strat):
    if not CAND.match(sek): continue
    s = strat[sek]; tot = sum(s.values()); oc = tot - s['не оценено']
    dolya = (s['доказано'] + s['косвенно']) / oc if oc else 0
    out.append(f'| {sek} | {tot} | {s["доказано"]} | {s["косвенно"]} | {s["кандидат"]} | {s["не наше"]} | {s["не оценено"]} | {dolya:.0%} |')
    if oc >= 20 and dolya < 0.3 and s['не оценено'] > oc: nizko.append(sek)
out += ['', f'Разделы, где оценённых меньше половины и доля низкая (второй круг линз): {", ".join(nizko) or "нет"}', '']
# города
gor = collections.defaultdict(collections.Counter)
for inn, (kl, sek, g) in KLASS.items():
    k = 'доказано' if inn in silnye else ('косвенно' if kl.startswith('косвенно') else 'кандидат' if kl.startswith('кандидат') else 'прочее')
    gor[g or '?'][k] += 1
out += ['## 4. По городам (топ-15 по числу доказанных+косвенных)', '', '| город | доказано | косвенно | кандидат |', '|---|---:|---:|---:|']
for g, s in sorted(gor.items(), key=lambda x: -(x[1]['доказано'] + x[1]['косвенно']))[:15]:
    out.append(f'| {g} | {s["доказано"]} | {s["косвенно"]} | {s["кандидат"]} |')
txt = '\n'.join(out)
open(os.path.join(AK, 'AK-POLNOTA.md'), 'w', encoding='utf-8').write(txt); print(txt)
req = urllib.request.Request(os.environ['DROP_URL'].rstrip('/') + '/AK-POLNOTA.md', data=txt.encode('utf-8'), method='PUT', headers={'X-Drop-Token': os.environ['DROP_TOKEN'], 'Content-Type': 'application/octet-stream'})
print('на дроп:', urllib.request.urlopen(req, timeout=300).status)

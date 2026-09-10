# -*- coding: utf-8 -*-
"""Фаза 3б. Класс по ОКВЭД для тех, кого линзы не успели оценить (баланс провайдера кончился).
Правило НЕ выдумано: оно выведено из уже полученных вердиктов линз. Для каждого кода ОКВЭД (сначала 4-значный,
затем 3-значный, затем раздел) считается распределение классов среди ОЦЕНЁННЫХ линзами предприятий этого кода.
Класс переносится на неоценённое предприятие, только если у кода набралось >= MIN_N наблюдений и доля
доминирующего класса >= PORÓG. Иначе остаётся «не оценено». Уверенность = доля × 100, уменьшенная на 10 пунктов
(правило слабее прямого вердикта). В tehprocess пишется, по какому коду и на скольких наблюдениях принято решение.
Идемпотентно: трогает только строки без klass и без прямого факта. argv: [MIN_N] [PORÓG]"""
import os, sys, re, json, sqlite3, collections, time
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
AK = r'C:\sender\_ops\ak'; DB = os.path.join(AK, 'AK-BAZA.sqlite')
MIN_N = int(sys.argv[1]) if len(sys.argv) > 1 else 8
POROG = float(sys.argv[2]) if len(sys.argv) > 2 else 0.70
TS = time.strftime('%Y-%m-%d %H:%M')
c = sqlite3.connect(DB, timeout=120)
# --- обучающая выборка: те, у кого класс поставлен линзами (istochnik_klassa пуст = линзы)
cols = [d[1] for d in c.execute('pragma table_info(predpriyatiya)')]
if 'istochnik_klassa' not in cols:
    c.execute('alter table predpriyatiya add column istochnik_klassa text'); c.commit()
UPR = {'косвенно': 'косвенно', 'кандидат': 'кандидат', 'кандидат (слабый)': 'кандидат', 'кандидат (линзы разошлись)': 'кандидат', 'не наше': 'не наше'}
obuch = collections.defaultdict(collections.Counter)
n_ob = 0
for inn, ok, okv, kl in c.execute("select inn, okved_osn, okved_vse, klass from predpriyatiya where klass is not null and klass not like 'доказано%' and (istochnik_klassa is null or istochnik_klassa='линзы')"):
    k = UPR.get(kl)
    if not k or not ok: continue
    ok = ok.strip()
    for key in (ok[:5] if len(ok) >= 5 else ok, ok[:4], ok[:2]):
        if key: obuch[key][k] += 1
    n_ob += 1
pravila = {}
for key, cnt in obuch.items():
    tot = sum(cnt.values())
    if tot < MIN_N: continue
    kl, n = cnt.most_common(1)[0]
    if n / tot >= POROG: pravila[key] = (kl, n / tot, tot)
print(f'обучающих предприятий (вердикт линз) {n_ob}; кодов с правилом {len(pravila)} (мин. {MIN_N} наблюдений, порог {POROG:.0%})', flush=True)
top = sorted(pravila.items(), key=lambda x: -x[1][2])[:15]
for k, (kl, d, t) in top: print(f'   {k:6} -> {kl:10} {d:.0%} на {t}', flush=True)
# --- применение
CAND = re.compile(r'^(0[1-9]|1\d|2\d|3[0-9]|4[1-3]|45\.2|49|52|71\.12|71\.2|72|77\.3|86\.1)')
fk = {r[0] for r in c.execute('select distinct inn from fakty')}
n_pr = collections.Counter(); n_net = 0
for inn, ok in c.execute("select inn, okved_osn from predpriyatiya where klass is null and (inn like '22%' or adres like '%Алтайский край%')"):
    if inn in fk or not ok: continue
    ok = ok.strip()
    if not CAND.match(ok): continue
    hit = None
    for key in ((ok[:5] if len(ok) >= 5 else ok), ok[:4], ok[:2]):
        if key in pravila: hit = (key, *pravila[key]); break
    if not hit:
        n_net += 1; continue
    key, kl, dolya, tot = hit
    c.execute("update predpriyatiya set klass=?, uverennost=?, tehprocess=?, istochnik_klassa=? where inn=?",
              (kl, max(30, int(dolya * 100) - 10), f'класс по ОКВЭД {key}: у {dolya:.0%} из {tot} предприятий этого кода линзы дали «{kl}»', 'оквэд-правило', inn))
    n_pr[kl] += 1
c.execute("update predpriyatiya set istochnik_klassa='линзы' where klass is not null and istochnik_klassa is null and klass not like 'доказано%'")
c.execute("update predpriyatiya set istochnik_klassa='факт' where klass like 'доказано%'")
c.commit()
print('по правилу проставлено:', dict(n_pr), '| без правила осталось', n_net, flush=True)
print('классы итого:', c.execute('select klass, istochnik_klassa, count(*) from predpriyatiya group by 1,2 order by 3 desc').fetchall(), flush=True)
c.close()

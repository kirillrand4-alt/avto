# -*- coding: utf-8 -*-
"""Проверка ссылок-доказательств: живы ли, куда ведут, что отдают.
Требование владельца п.5. Случайная выборка, стратифицированная по источнику.
Пишет построчно с fsync — переживает рестарт."""
import sqlite3, json, os, random, re, urllib.request, gzip, io, time, sys
D = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(D, 'park_ssylki_proverka.jsonl')
N = int(sys.argv[1]) if len(sys.argv) > 1 else 60
random.seed(20260809)

c = sqlite3.connect('file:%s?mode=ro' % os.path.join(D, 'park.db'), uri=True).cursor()
# стратификация: не меньше 3 ссылок на каждый источник, остальное случайно
vyborka = []
for (ist,) in c.execute("select distinct istochnik from fakt_ssylka"):
    rows = c.execute("select url,istochnik,fakt_id from fakt_ssylka where istochnik=? "
                     "order by random() limit 4", (ist,)).fetchall()
    vyborka += rows
ost = c.execute("select url,istochnik,fakt_id from fakt_ssylka order by random() limit ?",
                (max(0, N - len(vyborka)),)).fetchall()
vyborka += ost
vidino = {r[0] for r in vyborka}
sdelano = set()
if os.path.exists(OUT):
    for ln in open(OUT, encoding='utf-8'):
        try: sdelano.add(json.loads(ln)['url'])
        except Exception: pass
vyborka = [r for r in vyborka if r[0] not in sdelano]
print('к проверке', len(vyborka), 'ссылок', flush=True)

HDR = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                     '(KHTML, like Gecko) Chrome/126.0 Safari/537.36',
       'Accept': 'text/html,application/xhtml+xml', 'Accept-Language': 'ru,en;q=0.8',
       'Accept-Encoding': 'gzip'}

for url, ist, fid in vyborka:
    res = {'url': url, 'istochnik': ist, 'fakt_id': fid}
    t0 = time.time()
    try:
        req = urllib.request.Request(url, headers=HDR)
        with urllib.request.urlopen(req, timeout=30) as r:
            res['kod'] = r.status
            res['konechnyy_url'] = r.geturl()
            raw = r.read(400000)
            if (r.headers.get('Content-Encoding') or '') == 'gzip':
                try: raw = gzip.decompress(raw)
                except Exception: pass
            txt = raw.decode('utf-8', 'replace')
            res['bayt'] = len(raw)
            m = re.search(r'<title[^>]*>(.*?)</title>', txt, re.S | re.I)
            res['title'] = re.sub(r'\s+', ' ', m.group(1)).strip()[:150] if m else ''
            plain = re.sub(r'<[^>]+>', ' ', txt)
            plain = re.sub(r'\s+', ' ', plain)
            res['tekst_nachalo'] = plain[:400]
            nizhe = plain.lower()
            res['est_mashina'] = bool(re.search(
                r'компрессор|воздуходувк|нагнетател|турбокомпрессор|воздухоразделит|'
                r'генератор азота|генератор кислорода|азотн\w* установк|кислородн\w* установк', nizhe))
            res['trebuet_vhoda'] = bool(re.search(
                r'зарегистрир|войти|авториз|log ?in|captcha|robot|доступ ограничен', nizhe))
    except Exception as e:
        res['oshibka'] = repr(e)[:160]
    res['sek'] = round(time.time() - t0, 1)
    with open(OUT, 'a', encoding='utf-8') as f:
        f.write(json.dumps(res, ensure_ascii=False) + '\n'); f.flush(); os.fsync(f.fileno())
    print('%-3s %-26s %s' % (res.get('kod') or 'ERR', ist[:26], url[:70]), flush=True)
print('ГОТОВО', flush=True)

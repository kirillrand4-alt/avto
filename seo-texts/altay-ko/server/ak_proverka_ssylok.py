# -*- coding: utf-8 -*-
"""Фаза 5.2. Проверка ссылок карточек доказательств ПО СОДЕРЖАНИЮ: страница открылась И на ней есть то, чем подписана
(ИНН предприятия, либо 8+ знаков из названия, либо слово-машина из цитаты). Колонка fakty.proverka: 'ок' | 'открылась, содержания нет' | 'HTTP N' | 'ошибка'.
argv: [бюджет] [SKOLKO=N выборка] [VSE]. Резюм: проверяются только строки с пустой proverka."""
import os, sys, re, time, sqlite3, html, random, requests
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
requests.packages.urllib3.disable_warnings()
AK = r'C:\sender\_ops\ak'; DB = os.path.join(AK, 'AK-BAZA.sqlite')
BUDGET = int(sys.argv[1]) if len(sys.argv) > 1 else 1400
SK = next((int(a.split('=')[1]) for a in sys.argv if a.startswith('SKOLKO=')), 0); VSE = 'VSE' in sys.argv
T0 = time.time(); UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36'}
c = sqlite3.connect(DB, timeout=120)
cols = [d[1] for d in c.execute('pragma table_info(fakty)')]
if 'proverka' not in cols: c.execute('alter table fakty add column proverka text'); c.commit()
MASH = re.compile(r'компрессор|воздуходув|нагнетател|ресивер|воздухосборник|осушител|воздухоразделительн|азотн|кислородн|компрессорн', re.I)
rows = c.execute("select f.id, f.inn, f.ssylka, f.citata, f.tip, p.nazvanie from fakty f left join predpriyatiya p on p.inn=f.inn where f.proverka is null and f.ssylka like 'http%'").fetchall()
if not VSE:
    random.Random(11).shuffle(rows); rows = rows[:SK or 100]
print('к проверке', len(rows), flush=True)
S = requests.Session(); S.headers.update(UA); itog = {}
def norm(s): return re.sub(r'[^а-яa-z0-9]', '', (s or '').lower())
for fid, inn, url, cit, tip, naz in rows:
    if time.time() - T0 > BUDGET: break
    try:
        r = S.get(url, timeout=60, verify=False, allow_redirects=True)
        if r.status_code != 200:
            v = f'HTTP {r.status_code}'
        else:
            t = re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', r.text)))
            tn = norm(t)
            imya = re.sub(r'^(ооо|оао|зао|ао|пао|муп|гуп|фкп|фгуп|ип|кгбу|мбу|мку|нао)\s*', '', (naz or '').lower().replace('"', '').replace('«', '').replace('»', '')).strip()
            imya_ok = len(norm(imya)) >= 8 and norm(imya)[:14] in tn
            inn_ok = inn in t
            mash_ok = bool(MASH.search(t)) and (bool(MASH.search(cit or '')) or bool(MASH.search(tip or '')))
            if inn_ok or imya_ok or (mash_ok and 'monitor-pb' in url):
                v = 'ок'
            elif mash_ok:
                v = 'ок (машина есть, предприятие не сверено)'
            else:
                v = 'открылась, содержания нет'
    except Exception as e:
        v = 'ошибка ' + type(e).__name__
    itog[v] = itog.get(v, 0) + 1
    c.execute('update fakty set proverka=? where id=?', (v, fid)); c.commit()
    time.sleep(0.7)
print('итог проверки:', itog, '| всего проверено в базе:', c.execute("select proverka, count(*) from fakty where proverka is not null group by 1").fetchall(), flush=True)
c.close()

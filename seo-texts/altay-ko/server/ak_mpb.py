# -*- coding: utf-8 -*-
"""Т2.1. Реестр ЭПБ monitor-pb.ru по Алтайскому краю.
Этап A: поиск по словам региона (города края + «Алтайский край»), type=ТУ, все страницы -> mpb-slova.jsonl (резюм по (слово, страница)).
Этап B: полный список заключений по каждому ИНН края из AK-BAZA, у которого есть хоть один факт или который встретился в этапе A
        (/conclusions?exploiter=<ИНН>&type=ТУ) -> mpb-po-inn.jsonl (резюм по ИНН). Параллелить нельзя: реестр душит.
Этап C: факты (только наши машины: компрессор/воздуходувка/нагнетатель/ресивер/осушитель/ВРУ/генераторы) -> AK-BAZA.fakty, ссылка = /conclusion/<код>.
argv: [бюджет_сек] [TEST]. Модуль mpb_po_inn.py должен лежать рядом (C:\\sender\\_ops\\ak)."""
import os, sys, re, json, time, sqlite3, urllib.parse
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
AK = r'C:\sender\_ops\ak'; DB = os.path.join(AK, 'AK-BAZA.sqlite'); sys.path.insert(0, AK)
import mpb_po_inn as M
# --- реестр ЭПБ банит голый IP сервера (WinError 10060), но отвечает через пул socks5: подменяем загрузчик
import requests, random, itertools
requests.packages.urllib3.disable_warnings()
_PR = [l.strip() for l in open(r'C:\sender\dolphin-proxies.txt', encoding='utf-8') if l.strip()]
_PX = itertools.cycle(random.sample(_PR, len(_PR))) if _PR else None
_UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36', 'Accept-Language': 'ru'}
_S = requests.Session(); _S.headers.update(_UA)
def _vzyat_px(url, popytok=3):
    for i in range(popytok):
        pr = next(_PX) if _PX else None
        px = {'http': 'socks5h://' + pr, 'https': 'socks5h://' + pr} if pr else None
        try:
            r = _S.get(url, proxies=px, timeout=60, verify=False)
            if r.status_code == 200 and len(r.text) > 400: return r.text
        except Exception as e:
            if i == popytok - 1: return f'__ОШИБКА__ {type(e).__name__}: {str(e)[:70]}'
        time.sleep(1.0 * (i + 1))
    return '__ОШИБКА__ пустой ответ реестра'
M._vzyat = _vzyat_px
F_A = os.path.join(AK, 'mpb-slova.jsonl'); F_B = os.path.join(AK, 'mpb-po-inn.jsonl')
BUDGET = int(sys.argv[1]) if len(sys.argv) > 1 else 1400; TEST = 'TEST' in sys.argv
T0 = time.time(); TS = time.strftime('%Y-%m-%d %H:%M')
MASHINY = ['компрессор', 'компрессорная установка', 'винтовой компрессор', 'поршневой компрессор', 'центробежный компрессор', 'турбокомпрессор', 'воздушный компрессор',
           'дожимной компрессор', 'мембранный компрессор', 'спиральный компрессор', 'компрессорная станция', 'передвижная компрессорная', 'мобильная компрессорная',
           'воздуходувка', 'турбовоздуходувка', 'газодувка', 'нагнетатель', 'ресивер', 'воздухосборник', 'осушитель воздуха', 'азотная станция', 'генератор азота',
           'азотная установка', 'мембранная азотная', 'адсорбционная азотная', 'кислородная станция', 'генератор кислорода', 'кислородная установка',
           'воздухоразделительная установка', 'криогенная установка']
SLOVA = ['Барнаул', 'Бийск', 'Рубцовск', 'Новоалтайск', 'Заринск', 'Славгород', 'Алейск', 'Яровое', 'Камень-на-Оби', 'Белокуриха', 'Змеиногорск', 'Горняк',
         'Алтайский край', 'Алтайского края', 'Алтайском крае', 'Алтайкрай', 'Павловск Алтайский', 'Кулунда', 'Благовещенка', 'Тальменка', 'Поспелиха', 'Ребриха', 'Шипуново', 'Троицкое Алтайский', 'Степное Озеро']
if 'MASHINY' in sys.argv:      # режим «обход реестра по номенклатуре машин, регион режем по ИНН строки»
    SLOVA = MASHINY
if TEST: SLOVA = ['Новоалтайск']
MASH = re.compile(r'компрессор|воздуходув|нагнетател|турбокомпрессор|ресивер|воздухосборник|осушител|воздухоразделительн|\bВРУ\b|генератор\w*\s+(азота|кислорода)|азотн\w+\s+(станц|установ)|кислородн\w+\s+(станц|установ)|компрессорн', re.I)
NASOS = M.NASOS
VIDY = [('генератор кислорода', r'кислородн\w*\s*(станц|генератор|установ)|генератор\w*\s*кислород'), ('генератор азота', r'азотн\w*\s*(станц|генератор|установ)|генератор\w*\s*азот'),
        ('ВРУ', r'воздухоразделительн|\bВРУ\b'), ('нагнетатель', r'нагнетател'), ('воздуходувка', r'воздуходув|турбовоздуходув'), ('осушитель', r'осушител'),
        ('ресивер', r'ресивер|воздухосборник'), ('компрессорная станция', r'компрессорн\w+\s+(станц|установк|цех)'), ('компрессор', r'компрессор')]
VIDY = [(v, re.compile(r, re.I)) for v, r in VIDY]
def vid(s):
    for v, rx in VIDY:
        if rx.search(s or ''): return v
    return ''
def stroki_stranicy(url):
    h = M._vzyat(url, popytok=2)
    if h.startswith('__ОШИБКА__'): return None, h
    if len(h) < 400: return None, 'заглушка'
    rows = M._stroki(h)
    # ИНН эксплуатанта из ссылки /customer/<ИНН> той же строки таблицы
    po_kodu = {}
    for tr in M.TR.findall(h):
        n = M.NOMER.search(tr); x = M.EKSPL.search(tr)
        if n and x: po_kodu[n.group(1)] = x.group(1)
    for r in rows: r['inn'] = po_kodu.get(r['kod'], '')
    return rows, ''
# ---- этап A
gotovo = set(); vidennye = {}
if os.path.exists(F_A):
    for l in open(F_A, encoding='utf-8'):
        try: d = json.loads(l)
        except Exception: continue
        if not d.get('err'): gotovo.add((d['slovo'], d['stranica']))
        for r in d.get('stroki', []): vidennye.setdefault(r['kod'], r)
fa = open(F_A, 'a', encoding='utf-8'); konch = {}; pusto = {}; n_a = 0
A_BUDGET = BUDGET if 'MASHINY' in sys.argv else min(BUDGET, 300)
for st in range(1, 2000):
    if time.time() - T0 > A_BUDGET: break
    if all(konch.get(s) for s in SLOVA): break
    for slovo in SLOVA:
        if konch.get(slovo) or (slovo, st) in gotovo: continue
        if time.time() - T0 > A_BUDGET: break
        qs = {'q': slovo, 'type': 'ТУ'}
        if st > 1: qs['page'] = st
        rows, err = stroki_stranicy(f'{M.BAZA}/conclusions?' + urllib.parse.urlencode(qs))
        if rows is None:
            fa.write(json.dumps({'slovo': slovo, 'stranica': st, 'err': err[:60], 'stroki': []}, ensure_ascii=False) + '\n'); fa.flush(); time.sleep(3); continue
        novye = [r for r in rows if r['kod'] not in vidennye]
        h_rows = [{k: r.get(k) for k in ('kod', 'nomer', 'data', 'zakazchik', 'obekt', 'tip', 'org', 'inn')} for r in rows]
        fa.write(json.dumps({'slovo': slovo, 'stranica': st, 'err': '', 'stroki': h_rows, 'novyh': len(novye)}, ensure_ascii=False) + '\n'); fa.flush()
        gotovo.add((slovo, st))
        for r in rows: vidennye.setdefault(r['kod'], r)
        n_a += len(novye)
        # конец выдачи по слову - только ПУСТАЯ страница (дважды подряд); страница без новых строк
        # (все уже видены через другое слово) концом не считается
        pusto[slovo] = pusto.get(slovo, 0) + 1 if not rows else 0
        if pusto[slovo] >= 2 or st >= 400: konch[slovo] = True
        if TEST and st >= 2: konch[slovo] = True
        time.sleep(M.PAUZA)
fa.close()
print(f'этап A: страниц готово {len(gotovo)}, заключений увидено {len(vidennye)} (новых {n_a}), слов кончилось {sum(1 for s in SLOVA if konch.get(s))}/{len(SLOVA)}', flush=True)
# ИНН эксплуатанта в строках списка нет (только имя) - берём его через _stroki? В EKSPL есть /customer/<inn>: перечитаем из html нельзя, поэтому этап A даёт имена,
# а ИНН достаём так: имя -> predpriyatiya.nazvanie (совпадение) или этап B по ИНН базы. Плюс отдельный проход ниже по /customer/ ссылкам.
# ---- этап B
c = sqlite3.connect(DB, timeout=120)
kandidaty = [r[0] for r in c.execute("select distinct inn from predpriyatiya where inn like '22%' and (inn in (select inn from fakty) or istochniki_zapisi like '%park%' or istochniki_zapisi like '%eis%')")]
# + ИНН, которые упоминаются в obekt строк этапа A? нет ИНН. Добавим ИНН по совпадению имени
imena = {}
for inn, naz in c.execute("select inn, nazvanie from predpriyatiya where inn like '22%' and nazvanie is not null"):
    k = re.sub(r'[^а-яa-z0-9]', '', (naz or '').lower())
    if len(k) >= 6: imena.setdefault(k, inn)
dop = set(); n_novyh_pred = 0
have0 = {r[0] for r in c.execute('select inn from predpriyatiya')}
for r in vidennye.values():
    inn = r.get('inn') or ''
    if inn.startswith('22'):
        dop.add(inn)
        if inn not in have0:
            c.execute('insert or ignore into predpriyatiya(inn, nazvanie, istochniki_zapisi, ts) values(?,?,?,?)', (inn, r.get('zakazchik'), 'mpb', TS)); have0.add(inn); n_novyh_pred += 1
    else:
        k = re.sub(r'[^а-яa-z0-9]', '', (r.get('zakazchik') or '').lower())
        if k in imena: dop.add(imena[k])
c.commit()
kandidaty = sorted(set(kandidaty) | dop)
print(f'этап A->B: ИНН края из списков {len(dop)}, новых предприятий {n_novyh_pred}', flush=True)
if 'MASHINY' in sys.argv:
    # факты прямо из строк списка: слово = машина, ИНН эксплуатанта на 22 -> доказательство
    n_pr = 0
    for r in vidennye.values():
        inn = (r.get('inn') or '')
        ob = r.get('obekt') or ''
        if not inn.startswith('22') or not MASH.search(ob) or NASOS.search(ob): continue
        tip = vid(ob)
        if not tip: continue
        ss = f'{M.BAZA}/conclusion/{r["kod"]}'
        cit = (ob[:400] + ' | ' + (r.get('nomer') or '') + ' | ' + (r.get('org') or ''))[:500]
        c.execute('''insert or ignore into fakty(inn,predpriyatie,vid_fakta,tip,marka_model,sreda,data,srok_do,status_sroka,sila,istochnik,ssylka,citata,kto_sobral,ts,klyuch) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                  (inn, r.get('zakazchik'), 'ЭПБ', tip, '', '', r.get('data'), '', '', 5, 'monitor-pb.ru', ss, cit, 'ak_mpb_slova', TS, f'{inn}|{ss}|{tip}||{cit[:80]}')); n_pr += 1
    c.commit()
    print('этап A-факты (по номенклатуре):', c.execute("select count(*), count(distinct inn) from fakty where kto_sobral='ak_mpb_slova'").fetchone(), '| строк-кандидатов', n_pr, flush=True)
    print('ИНН края с ЭПБ всего:', c.execute("select count(distinct inn) from fakty where vid_fakta='ЭПБ'").fetchone()[0], flush=True)
    if all(konch.get(s) for s in SLOVA): print('ГОТОВО')
    c.close(); sys.exit(0)
# этап B2: остальные юрлица края с производственным ОКВЭД, крупные первыми (полный список заключений по каждому ИНН)
CAND = re.compile(r'^(0[1-9]|1\d|2\d|3[0-9]|4[1-3]|45\.2|49|52|71\.12|71\.2|72|77\.3|86\.1)')
vyr = {r[0]: r[1] for r in c.execute("select inn, max(vyruchka_rub) from finansy where istochnik='girbo' group by 1")}
b2 = [r[0] for r in c.execute("select inn, okved_osn from predpriyatiya where inn like '22%' and (status_egrul is null or status_egrul not like '%LIQUID%')") if CAND.match(r[1] or '') and r[0] not in set(kandidaty)]
b2.sort(key=lambda i: -(vyr.get(i) or 0))
kandidaty = kandidaty + b2
print(f'этап B2: добавлено ИНН по ОКВЭД {len(b2)}', flush=True)
if TEST: kandidaty = kandidaty[:3]
gotovo_b = {}
if os.path.exists(F_B):
    for l in open(F_B, encoding='utf-8'):
        try: d = json.loads(l); gotovo_b[d['inn']] = d
        except Exception: pass
fb = open(F_B, 'a', encoding='utf-8'); n_b = 0
for inn in kandidaty:
    if inn in gotovo_b: continue
    if time.time() - T0 > BUDGET: break
    rows, err = M.po_inn(inn, max_stranic=60 if not TEST else 3, tolko_tu=True)
    d = {'inn': inn, 'err': err[:80] if err else '', 'n': len(rows), 'stroki': [{k: r.get(k) for k in ('nomer', 'data', 'obekt', 'tip', 'ekspertnaya_org', 'ssylka', 'nashe_oborudovanie', 'centrobezhnoe', 'nasos', 'predpriyatie')} for r in rows]}
    if not err: gotovo_b[inn] = d
    fb.write(json.dumps(d, ensure_ascii=False) + '\n'); fb.flush(); n_b += 1
    time.sleep(M.PAUZA)
fb.close()
print(f'этап B: ИНН-кандидатов {len(kandidaty)}, готово {len(gotovo_b)}, за заход {n_b}', flush=True)
# ---- этап C: факты
have = {r[0] for r in c.execute('select inn from predpriyatiya')}
n_f = 0
for inn, d in gotovo_b.items():
    for r in d['stroki']:
        ob = r.get('obekt') or ''
        if not MASH.search(ob) or NASOS.search(ob): continue
        tip = vid(ob)
        if not tip: continue
        m = re.search(r'([А-ЯA-Z][\w\-/.]{1,25}\s?[\-\d][\w\-/.,]{0,20})', ob)
        kl = f'{inn}|{r.get("ssylka")}|{tip}||{ob[:80]}'
        c.execute('''insert or ignore into fakty(inn,predpriyatie,vid_fakta,tip,marka_model,sreda,data,srok_do,status_sroka,sila,istochnik,ssylka,citata,kto_sobral,ts,klyuch)
                     values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                  (inn, r.get('predpriyatie'), 'ЭПБ', tip, '', M.sreda(ob) if hasattr(M, 'sreda') else '', r.get('data'), '', '', 5, 'monitor-pb.ru', r.get('ssylka'), (ob[:400] + ' | ' + (r.get('nomer') or '') + ' | ' + (r.get('ekspertnaya_org') or ''))[:500], 'ak_mpb', TS, kl))
        n_f += 1
c.commit()
print('этап C: строк-кандидатов', n_f, '| фактов ЭПБ ak_mpb:', c.execute("select count(*) from fakty where kto_sobral='ak_mpb'").fetchone()[0], '| ИНН с ЭПБ:', c.execute("select count(distinct inn) from fakty where vid_fakta='ЭПБ'").fetchone()[0], flush=True)
c.close()
if all(konch.get(s) for s in SLOVA) and all(i in gotovo_b for i in kandidaty):
    print('ГОТОВО')

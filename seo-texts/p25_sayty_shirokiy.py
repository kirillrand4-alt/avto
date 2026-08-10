# -*- coding: utf-8 -*-
"""Широкий обход САЙТОВ предприятий парка: телефон приёмной и текст страницы контактов.

Первый заход этого канала обошёл 90 сайтов и дал 24 строки. Мало не потому, что канал
плохой, а потому что я взяла сайты ТОЛЬКО из своих баз, где их немного. Между тем сайты
лежат ещё в двух местах, собранных соседями и выложенных на дроп:

    P25-SAYTY-OT-1S-VSE.csv     363 сайта, собраны 1-й и 2-й сессиями
    OBOJTI-sayty-est-3s.csv     463 сайта

Источники СКЛАДЫВАЮ, а не заменяю: если сайт известен и из базы, и из файла соседа — это
два источника у одного факта, и оба идут в запись. Правило владельца про накопление
провенанса тут работает буквально.

ЧЕГО ЭТОТ СКРИПТ НЕ ДЕЛАЕТ. Он не решает, кто на странице ЛПР. Регулярка по телефонам
одинаково берёт приёмную, факс, номер поставщика в подвале и телефон разработчика сайта.
Поэтому кроме номеров он сохраняет ПЛОСКИЙ ТЕКСТ страницы контактов — по нему отдельным
проходом пойдёт модель и вытащит «ФИО + должность + номер» связкой, чего регуляркой не
получить.

ЗАСЛОН, тот же что в первом заходе и по той же причине: хост ОТВЕТА должен совпадать с
сайтом предприятия. Редирект на агрегатор даёт настоящие номера, приписанные не тому, —
ошибка, неотличимая от правды по цитате.

СРОК. У задания на сервере 1700 секунд, и молча упереться в них — значит потерять всё
собранное. Держу свой срок в 1450 секунд: по нему обход прекращается, собранное пишется, а
число необойдённых печатается честно, а не прячется.

Числа в КОНЦЕ.
"""
import collections
import io
import json
import os
import re
import ssl
import sqlite3
import threading
import time
import urllib.parse
import urllib.request

NACHALO = time.time()
SROK = 1450
PARK = [r'C:\sender\_ops\park_ingest_3.jsonl', r'C:\sender\_ops\park_ingest_3b.jsonl',
        r'C:\sender\_ops\park_ingest_3c.jsonl']
GOTOVO = [r'C:\sender\_ops\PARK-SPISOK-DLYA-ZVONKA-3S.csv',
          r'C:\sender\_ops\PARK-SPISOK-CHEREZ-KOMMUTATOR-3S.csv']
BAZY = [r'C:\sender\enrich.db', r'C:\seostat\data\centrifugal.db',
        r'C:\seostat\drop\drop-storage\atlas_copco.db']
S_DROPA = ['P25-SAYTY-OT-1S-VSE.csv', 'OBOJTI-sayty-est-3s.csv']
BYLO = r'C:\sender\_ops\PARK-SAYTY-TELEFONY-3S.jsonl'
VYHOD = r'C:\sender\_ops\PARK-SAYTY-TELEFONY-3S.jsonl'
TEKSTY = r'C:\sender\_ops\PARK-SAYTY-TEKST-3S.jsonl'
POTOKOV = 14
PUTI = ['/contacts', '/kontakty', '', '/contact', '/about/contacts', '/o-kompanii/kontakty']
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/120.0.0.0 Safari/537.36')
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
net = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx),
                                 urllib.request.ProxyHandler({}))
TEG = re.compile(r'<(script|style)[^>]*>.*?</\1>|<[^>]+>', re.S | re.I)
TELEFON = re.compile(r'(?:\+7|8)[\s\-()]*\d{3,5}[\s\-()]*\d{2,3}[\s\-]*\d{2}[\s\-]*\d{2}')
POCHTA = re.compile(r'[A-Za-z0-9._%-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')
LYUDI_SLOVA = re.compile(r'директор|руководител|главн\w+ (?:инженер|энергетик|механик)|'
                         r'начальник|снабжен|закупк|отдел', re.I)
drop = os.environ.get('DROP_URL', '').rstrip('/')
tok = {'X-Drop-Token': os.environ.get('DROP_TOKEN', '')}


def s_dropa(imya):
    try:
        return net.open(urllib.request.Request('%s/%s' % (drop, imya), headers=tok),
                        timeout=120).read().decode('utf-8-sig', 'replace')
    except Exception:  # noqa: BLE001
        return ''


park = {}
for p in PARK:
    if not os.path.exists(p):
        continue
    for s in io.open(p, encoding='utf-8'):
        try:
            o = json.loads(s)
        except Exception:  # noqa: BLE001
            continue
        if o.get('inn'):
            park.setdefault(o['inn'], o.get('vid') or 'машина')

gotovo = set()
for g in GOTOVO:
    if not os.path.exists(g):
        continue
    for s in io.open(g, encoding='utf-8-sig').read().splitlines()[1:]:
        p_ = s.split(';')
        if p_ and p_[0].strip().isdigit():
            gotovo.add(p_[0].strip())

# сайт может прийти из нескольких мест — храню ВСЕ, а не последний
sayty = collections.defaultdict(set)
imena = {}


def chistyy_sayt(v):
    v = str(v or '').strip().strip('"').lower()
    v = re.sub(r'^https?://', '', v).rstrip('/')
    v = v.split('/')[0]
    if not v or '.' not in v or ' ' in v or '@' in v:
        return ''
    if re.search(r'(vk\.com|facebook|instagram|youtube|yandex\.|google\.|mail\.ru$)', v):
        return ''
    return v


for b in BAZY:
    if not os.path.exists(b):
        continue
    try:
        cx = sqlite3.connect('file:%s?mode=ro' % b.replace('\\', '/'), uri=True)
        tabl = [r[0] for r in cx.execute("select name from sqlite_master where type='table'")]
    except Exception:  # noqa: BLE001
        continue
    for t in tabl:
        try:
            kol = [r[1] for r in cx.execute('pragma table_info("%s")' % t)]
        except Exception:  # noqa: BLE001
            continue
        if 'inn' not in kol:
            continue
        ps = [k for k in ('site', 'sayt', 'domain', 'url', 'website') if k in kol]
        pn = next((k for k in ('name', 'naimenovanie', 'company') if k in kol), None)
        if not ps and not pn:
            continue
        polya = ps + ([pn] if pn else [])
        try:
            kur = cx.execute('select inn,%s from "%s"' % (','.join('"%s"' % k for k in polya), t))
        except Exception:  # noqa: BLE001
            continue
        try:
            for r in kur:
                i = str(r[0] or '').strip()
                if not i or i not in park:
                    continue
                for j, k in enumerate(polya):
                    v = r[1 + j]
                    if k == pn:
                        if v and i not in imena:
                            imena[i] = re.sub(r'\s+', ' ', str(v)).strip()
                    else:
                        c = chistyy_sayt(v)
                        if c:
                            sayty[i].add((c, '%s/%s' % (os.path.basename(b), t)))
        except Exception:  # noqa: BLE001
            pass
    cx.close()

for f in S_DROPA:
    syr = s_dropa(f)
    for s in syr.splitlines()[1:]:
        p_ = s.split(';')
        if len(p_) < 3 or not p_[0].strip().isdigit():
            continue
        i = p_[0].strip()
        c = chistyy_sayt(p_[2])
        if c and i in park:
            sayty[i].add((c, f))
        if len(p_) > 1 and p_[1].strip() and i not in imena:
            imena[i] = p_[1].strip().strip('"')

# сперва те, у кого контакта ещё нет вовсе
celi = sorted(sayty, key=lambda i: (i in gotovo, i))
ochered = list(celi)
zamok = threading.Lock()
potok, prichiny, teksty = [], collections.Counter(), []
schet = {'sdelano': 0}


def odin(inn):
    hosty = sorted({c for c, _ in sayty[inn]})
    otkuda_sayt = ' | '.join(sorted({o for _, o in sayty[inn]}))
    nashli_t, nashli_p, otkuda, tekst_str = set(), set(), '', ''
    for h in hosty[:2]:
        for shema in ('https://', 'http://'):
            for put in PUTI:
                if time.time() - NACHALO > SROK:
                    return
                u = shema + h + put
                try:
                    rq = urllib.request.Request(u, headers={'User-Agent': UA,
                                                            'Accept-Language': 'ru'})
                    with net.open(rq, timeout=12) as rs:
                        telo = rs.read(400000).decode('utf-8', 'replace')
                        real = urllib.parse.urlparse(rs.geturl()).netloc.lower()
                except Exception:  # noqa: BLE001
                    continue
                if re.sub(r'^www\.', '', real) != re.sub(r'^www\.', '', h):
                    with zamok:
                        prichiny['ответил чужой хост — не засчитываю'] += 1
                    continue
                t = re.sub(r'\s+', ' ', TEG.sub(' ', telo))
                for m in TELEFON.finditer(t):
                    nashli_t.add(m.group(0).strip())
                for m in POCHTA.finditer(t):
                    if not re.search(r'\.(png|jpg|jpeg|svg|css|js|webp)$', m.group(0), re.I):
                        nashli_p.add(m.group(0).strip().lower())
                if nashli_t and (LYUDI_SLOVA.search(t) or put):
                    otkuda, tekst_str = u, t[:18000]
                    break
            if otkuda:
                break
        if otkuda:
            break
    with zamok:
        schet['sdelano'] += 1
        if not nashli_t and not nashli_p:
            prichiny['сайт не дал ни телефона, ни почты'] += 1
            return
        if not nashli_t:
            prichiny['только почта'] += 1
        potok.append({'inn': inn, 'predpriyatie': imena.get(inn, ''),
                      'sayt': ' | '.join(hosty[:2]),
                      'sayt_otkuda': otkuda_sayt,
                      'telefony': ' | '.join(sorted(nashli_t)[:6]),
                      'vid_nomera': 'ОБЩИЙ ТЕЛЕФОН ПРЕДПРИЯТИЯ (сайт), не личный',
                      'pochty': ' | '.join(sorted(nashli_p)[:4]),
                      'mashina': park.get(inn, ''),
                      'istochniki': otkuda or ('https://' + hosty[0]),
                      'istochnikov': 1, 'bylo_v_spiske': inn in gotovo,
                      'kto': '3-я сессия, сайт предприятия'})
        prichiny['взято'] += 1
        if tekst_str and LYUDI_SLOVA.search(tekst_str):
            teksty.append({'inn': inn, 'ssylka': otkuda, 'tekst': tekst_str})
            prichiny['текст сохранён для разбора моделью'] += 1


def rabotnik():
    while True:
        with zamok:
            if not ochered or time.time() - NACHALO > SROK:
                return
            i = ochered.pop(0)
        try:
            odin(i)
        except Exception:  # noqa: BLE001
            with zamok:
                prichiny['исключение при обходе'] += 1


nitki = [threading.Thread(target=rabotnik) for _ in range(POTOKOV)]
for n in nitki:
    n.start()
for n in nitki:
    n.join()

# СКЛАДЫВАЮ со старым файлом, а не затираю его: 24 строки первого захода добыты честно.
staroe = {}
if os.path.exists(BYLO):
    for s in io.open(BYLO, encoding='utf-8'):
        try:
            o = json.loads(s)
        except Exception:  # noqa: BLE001
            continue
        if o.get('inn'):
            staroe[o['inn']] = o
novyh = 0
for o in potok:
    if o['inn'] in staroe:
        st = staroe[o['inn']]
        for u in (o.get('istochniki') or '').split(' | '):
            if u and u not in (st.get('istochniki') or ''):
                st['istochniki'] = (st.get('istochniki') or '') + ' | ' + u
                st['istochnikov'] = st.get('istochnikov', 1) + 1
        if o['telefony'] and not st.get('telefony'):
            st['telefony'] = o['telefony']
    else:
        staroe[o['inn']] = o
        novyh += 1

with io.open(VYHOD, 'w', encoding='utf-8') as f:
    for o in staroe.values():
        f.write(json.dumps(o, ensure_ascii=False) + '\n')
with io.open(TEKSTY, 'w', encoding='utf-8') as f:
    for o in teksty:
        f.write(json.dumps(o, ensure_ascii=False) + '\n')

vyl = []
for p in (VYHOD, TEKSTY):
    try:
        rq = urllib.request.Request('%s/%s' % (drop, os.path.basename(p)),
                                    data=io.open(p, 'rb').read(), method='PUT', headers=tok)
        vyl.append('%s: %s' % (os.path.basename(p),
                               net.open(rq, timeout=300).read().decode('utf-8', 'replace')[:60]))
    except Exception as e:  # noqa: BLE001
        vyl.append('%s НЕ ВЫЛОЖЕН: %s' % (os.path.basename(p), str(e)[:60]))

s_tel = [o for o in staroe.values() if o.get('telefony')]
print('\n\n########## ПЕРВЫЕ ДЕСЯТЬ НОВЫХ')
for o in potok[:10]:
    print('  %-12s %-28s %-32s %s' % (o['inn'], (o['predpriyatie'] or '—')[:28],
                                      o['telefony'][:32], o['mashina'][:14]))
print('\n########## ЧИСЛА')
print('  предприятий в парке          %5d' % len(park))
print('  из них уже в готовых списках %5d' % len(gotovo & set(park)))
print('  сайт известен хоть откуда-то %5d' % len(sayty))
print('  обойдено за этот заход       %5d  (осталось в очереди %d)'
      % (schet['sdelano'], len(ochered)))
print('  строк добыто                 %5d  (новых предприятий %d)' % (len(potok), novyh))
print('  всего в файле сайтов         %5d  (с телефоном %d)' % (len(staroe), len(s_tel)))
print('  текстов для разбора моделью  %5d' % len(teksty))
for k, v in prichiny.most_common():
    print('     %-46s %5d' % (k[:46], v))
for v in vyl:
    print('  %s' % v)
print('  секунд потрачено %d из %d' % (time.time() - NACHALO, SROK))
print('ИТОГ ' + json.dumps({'обойдено': schet['sdelano'], 'осталось': len(ochered),
                            'новых предприятий': novyh, 'всего с телефоном': len(s_tel),
                            'текстов': len(teksty)}, ensure_ascii=False))

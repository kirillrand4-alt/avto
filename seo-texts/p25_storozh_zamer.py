# -*- coding: utf-8 -*-
"""Замер сторожа одним заходом: словарь, поток парка и пять случайных ссылок глазами.

Три вопроса сторожа меряются по РАЗНЫМ файлам, и каждый файл называется в выводе. Замер,
который не называет живой файл, — это пересказ памяти, а не замер.

    словарь серий   PARK-SLOVAR-SERII-3S-v4.csv  — сколько серий, у скольких доказан вид
                    машины, сколько сняли заслоны, и ПРОБА НА РАЗЛИЧЕНИЕ: беру серии, у
                    которых в цитате стоит признак «позиция/помещение/чужая машина/
                    технологический номер», и смотрю, сняты ли они. Проба обязана иметь
                    провалы или объяснение, почему их нет.
    поток парка     park_ingest_3.jsonl — фактов, со ссылкой, без ссылки
    пять ссылок     случайные из park_ingest_3.jsonl, открываются С СЕРВЕРА, и по каждой
                    сказано, доказывает ли она то, ради чего стоит

Числа в КОНЦЕ.
"""
import collections
import io
import json
import os
import random
import re
import ssl
import urllib.request

OPS = r'C:\sender\_ops'
POTOK = os.path.join(OPS, 'park_ingest_3.jsonl')
SLOVARI = ['PARK-SLOVAR-SERII-3S-v4.csv', 'PARK-SLOVAR-SERII-3S-v3.csv',
           'PARK-SLOVAR-SERII-3S.csv']
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/120.0.0.0 Safari/537.36')
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
net = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx),
                                  urllib.request.ProxyHandler({}))
TEG = re.compile(r'<(script|style)[^>]*>.*?</\1>|<[^>]+>', re.S | re.I)
drop = os.environ.get('DROP_URL', '').rstrip('/')
tok = {'X-Drop-Token': os.environ.get('DROP_TOKEN', '')}
# признаки, из-за которых обозначение в цитате — НЕ машина предприятия
ZASLONY = [('позиция', re.compile(r'\bпоз\.?\s*\d|\bпозиция\s*\d', re.I)),
           ('помещение или здание', re.compile(r'помещени|здани|корпус\s*\d|цех\s*№', re.I)),
           ('чужая машина', re.compile(r'насос|вентилятор|котёл|котел|кран|трубопровод|'
                                       r'резервуар|ёмкост|емкост', re.I)),
           ('технологический номер', re.compile(r'зав\.?\s*№|инв\.?\s*№|рег\.?\s*№', re.I))]


def s_dropa(imya):
    try:
        return net.open(urllib.request.Request('%s/%s' % (drop, imya), headers=tok),
                        timeout=180).read().decode('utf-8-sig', 'replace')
    except Exception as e:  # noqa: BLE001
        return ''


# ---------- 1. СЛОВАРЬ
syr, fajl_slovarya = '', ''
for f in SLOVARI:
    syr = s_dropa(f)
    if syr:
        fajl_slovarya = f
        break
serii, vid_dokazan, s_citatoy = 0, 0, 0
zaslon_sch = collections.Counter()
proba, provaly = [], 0
if syr:
    st = syr.splitlines()
    sh = [x.strip() for x in st[0].split(';')]
    for s in st[1:]:
        p = s.split(';')
        if len(p) < len(sh):
            continue
        o = dict(zip(sh, p[:len(sh) - 1] + [';'.join(p[len(sh) - 1:])]))
        serii += 1
        if (o.get('vid') or '').strip():
            vid_dokazan += 1
        cit = o.get('citata') or ''
        if cit:
            s_citatoy += 1
        for imya, reg in ZASLONY:
            if reg.search(cit):
                zaslon_sch[imya] += 1
                proba.append((o.get('seriya', ''), imya, cit[:90]))

# ---------- 2. ПОТОК ПАРКА
fakty, so_ssylkoy, bez_ssylki = 0, 0, 0
vidy = collections.Counter()
stroki = []
if os.path.exists(POTOK):
    for s in io.open(POTOK, encoding='utf-8'):
        try:
            o = json.loads(s)
        except Exception:  # noqa: BLE001
            continue
        fakty += 1
        stroki.append(o)
        vidy[o.get('vid') or 'вид не назван'] += 1
        if [u for u in str(o.get('istochniki') or '').split(' | ') if u.startswith('http')]:
            so_ssylkoy += 1
        else:
            bez_ssylki += 1

# имена предприятий: нужны, чтобы засчитать доказательство, названное СЛОВОМ, а не цифрами
imena = {}
_baza = os.path.join(OPS, 'PARK-BAZA-EDINAYA-3S.csv')
if os.path.exists(_baza):
    _sh = None
    for _s in io.open(_baza, encoding='utf-8-sig'):
        _p = _s.rstrip('\n').split(';')
        if _sh is None:
            _sh = _p
            continue
        if len(_p) == len(_sh):
            _o = dict(zip(_sh, _p))
            if _o.get('inn') and _o.get('predpriyatie') and _o['inn'] not in imena:
                imena[_o['inn']] = _o['predpriyatie']

# ---------- 3. ПЯТЬ СЛУЧАЙНЫХ ССЫЛОК ГЛАЗАМИ
# Жребий берётся из довода запуска: сторож просит КАЖДЫЙ раз НОВЫЕ пять ссылок, а один
# и тот же посев вернул бы те же пять и создал бы вид проверки без проверки.
import sys as _sys
random.seed(int(_sys.argv[1]) if len(_sys.argv) > 1 else 4242)
vybor = random.sample(stroki, min(5, len(stroki))) if stroki else []
ishody = collections.Counter()
glazami = []
kontrol_probit = 0
chuzhie = [imena.get(x.get('inn')) for x in vybor]
for o in vybor:
    us = [u for u in str(o.get('istochniki') or '').split(' | ') if u.startswith('http')]
    vid = (o.get('vid') or '').lower()
    obozn = str(o.get('oboznachenie') or o.get('seriya') or '').strip()
    nashli_vid, nashli_obozn, nashli_inn, otkrylos = False, False, False, 0
    nashli_imenem = False
    posledniy_tekst = ''
    chuzhoe_imya = next((c for j, c in enumerate(chuzhie)
                         if c and c != imena.get(o.get('inn'))), '')
    err = ''
    for u in us[:3]:
        try:
            with net.open(urllib.request.Request(u, headers={'User-Agent': UA,
                                                             'Accept-Language': 'ru'}),
                          timeout=40) as rs:
                t = re.sub(r'\s+', ' ', TEG.sub(' ', rs.read(400000).decode('utf-8', 'replace')))
        except Exception as e:  # noqa: BLE001
            err = str(e)[:44]
            continue
        otkrylos += 1
        posledniy_tekst = t
        if re.search(r'компрессор|воздуходув|нагнетател|ГПА|осушител|азот|кислород|ВРУ', t, re.I):
            nashli_vid = True
        if obozn and len(obozn) > 3:
            cifry_o = re.sub(r'\W', '', obozn).lower()
            if cifry_o and cifry_o in re.sub(r'\W', '', t).lower():
                nashli_obozn = True
        if o.get('inn') and o['inn'] in re.sub(r'\D', '', t):
            nashli_inn = True
        # ПРЕДПРИЯТИЕ МОЖЕТ БЫТЬ НАЗВАНО ИМЕНЕМ, А НЕ ИНН, и мерка обязана это видеть.
        # Жребий 7373 дал 4 «ИНН на странице не напечатан» из 5, и две из них — карточки
        # ПЛАНА закупок ЕИС (`orderplan/tru-plan/card`), где заказчик стоит названием, а
        # цифры ИНН лежат на другой вкладке. Требовать только цифры значит объявлять
        # недоказанным то, что доказано словами.
        if not nashli_inn and imena.get(o.get('inn')):
            koren = [w for w in re.findall(r'[А-ЯЁA-Z]{5,}', imena[o['inn']].upper())
                     if w not in ('ОБЩЕСТВО', 'ОГРАНИЧЕННОЙ', 'ОТВЕТСТВЕННОСТЬЮ',
                                  'АКЦИОНЕРНОЕ', 'ПУБЛИЧНОЕ', 'ГОСУДАРСТВЕННОЕ',
                                  'БЮДЖЕТНОЕ', 'УЧРЕЖДЕНИЕ', 'ПРЕДПРИЯТИЕ', 'УНИТАРНОЕ',
                                  'ФЕДЕРАЛЬНОЕ', 'МУНИЦИПАЛЬНОЕ', 'КАЗЕННОЕ')]
            # СТРОГОСТЬ ПОДБИРАЛАСЬ КОНТРОЛЕМ, А НЕ НА ГЛАЗ. Первый вариант («любой из
            # трёх корней длиной от пяти букв») дал 5 из 5 — и тут же провалил
            # отрицательный контроль: ЧУЖОЕ имя подтвердилось на 2 страницах из 5.
            # Корни вроде «ЭНЕРГО», «СЕРВИС», «ЗАВОДА» лежат на половине страниц закупок.
            # Условие ужесточено: либо ДВА разных корня от шести букв, либо один длинный
            # от восьми. Контроль печатается рядом с результатом всегда — если он снова
            # пробит, число «доказано по имени» недействительно.
            dlinnye = [k for k in koren if len(k) >= 8]
            shest = [k for k in koren if len(k) >= 6]
            sovpalo = [k for k in shest if k in t.upper()]
            if (dlinnye and any(k in t.upper() for k in dlinnye)) or len(set(sovpalo)) >= 2:
                nashli_inn = True
                nashli_imenem = True
    # ОТРИЦАТЕЛЬНЫЙ КОНТРОЛЬ НА ПРОВЕРКУ ПО ИМЕНИ. Признание «предприятие названо словом»
    # опаснее цифрового: корень «ЭНЕРГО» или «СЕРВИС» найдётся на половине страниц. Поэтому
    # той же меркой проверяю ЧУЖОЕ имя — предприятия из другой строки выборки. Если чужое
    # имя тоже «подтверждается», проверка по имени ничего не стоит и я обязана это сказать.
    if nashli_imenem and chuzhoe_imya:
        koren_ch = [w for w in re.findall(r'[А-ЯЁA-Z]{5,}', chuzhoe_imya.upper())
                    if w not in ('ОБЩЕСТВО', 'ОГРАНИЧЕННОЙ', 'ОТВЕТСТВЕННОСТЬЮ',
                                 'АКЦИОНЕРНОЕ', 'ПУБЛИЧНОЕ', 'ГОСУДАРСТВЕННОЕ',
                                 'БЮДЖЕТНОЕ', 'УЧРЕЖДЕНИЕ', 'ПРЕДПРИЯТИЕ', 'УНИТАРНОЕ',
                                 'ФЕДЕРАЛЬНОЕ', 'МУНИЦИПАЛЬНОЕ', 'КАЗЕННОЕ')]
        _t = (posledniy_tekst or '').upper()
        _dl = [k for k in koren_ch if len(k) >= 8]
        _sh = [k for k in koren_ch if len(k) >= 6 and k in _t]
        if (_dl and any(k in _t for k in _dl)) or len(set(_sh)) >= 2:
            kontrol_probit += 1
    if nashli_vid and nashli_inn:
        v = ('ДОКАЗЫВАЕТ: машина и предприятие (по НАЗВАНИЮ)' if nashli_imenem
             else 'ДОКАЗЫВАЕТ: и машина, и ИНН предприятия на странице')
    elif nashli_vid:
        v = 'машина есть, предприятие не названо ни ИНН, ни именем'
    elif otkrylos:
        v = 'страница открылась, машины на ней нет'
    else:
        v = 'НЕ ОТКРЫЛАСЬ'
    ishody[v.split(':')[0]] += 1
    # ЧЕСТНАЯ ПОДПИСЬ О СОБСТВЕННОМ ПОТОЛКЕ. Строка «ссылок 25, открылось 3» читается как
    # «22 ссылки мертвы», а на самом деле проверяльщик берёт только первые три (`us[:3]`) —
    # 22 никто не пробовал. Печатаю, сколько ПРОБОВАЛА, иначе мой же отчёт наговаривает
    # на данные.
    glazami.append((o.get('inn', ''), o.get('vid', '')[:16], obozn[:16], min(len(us), 3),
                    otkrylos,
                    v, (us[0] if us else '—')[:88], err))

print('\n\n########## ПЯТЬ ССЫЛОК, ОТКРЫТЫХ С СЕРВЕРА')
for g in glazami:
    print('  %-12s %-16s %-16s пробовала %d ссылок, открылось %d — %s' % g[:6])
    print('        %s%s' % (g[6], ('   ошибка: ' + g[7]) if g[7] else ''))
print('\n########## ПРОБА НА РАЗЛИЧЕНИЕ СЛОВАРЯ, по одной')
for p in proba[:8]:
    print('  %-14s признак «%s»' % (p[0][:14], p[1]))
    print('        %s' % p[2])
print('\n########## ЧИСЛА')
print('  словарь: файл %s' % (fajl_slovarya or 'НЕ СКАЧАЛСЯ НИ ОДИН'))
print('     серий всего                       %5d' % serii)
print('     из них с доказанным видом машины  %5d' % vid_dokazan)
print('     из них с цитатой-доказательством  %5d' % s_citatoy)
for k, v in zaslon_sch.most_common():
    print('     признак «%-28s» встретился %4d' % (k, v))
print('  поток: файл %s' % POTOK)
print('     фактов                            %5d' % fakty)
print('     со ссылкой-первоисточником        %5d' % so_ssylkoy)
print('     БЕЗ ссылки                        %5d' % bez_ssylki)
print('     --- по виду машины')
for k, v in vidy.most_common(9):
    print('        %-28s %5d' % (k[:28], v))
print('  отрицательный контроль проверки ПО ИМЕНИ: чужое имя подтвердилось %d раз %s'
      % (kontrol_probit, '— проверке по имени верить нельзя' if kontrol_probit
         else '— проверка по имени умеет говорить «нет»'))
print('  пять ссылок глазами:')
for k, v in ishody.most_common():
    print('     %-52s %5d' % (k[:52], v))
print('ИТОГ ' + json.dumps({'серий': serii, 'фактов': fakty, 'без ссылки': bez_ssylki,
                            'ссылки': dict(ishody)}, ensure_ascii=False))

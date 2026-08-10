# -*- coding: utf-8 -*-
"""836 новых предприятий пришли БЕЗ контактов. У ЕИС на карточке организации они есть.

Прирост парка сам по себе цели не двигает: у 836 новых предприятий доказана машина и нет
ни одного телефона, из-за чего очередь «машина есть, контакта нет» выросла с 591 до 1 390.
Звонить туда пока нечем.

Но эти предприятия пришли ИЗ ЕИС, а у ЕИС на карточке организации-заказчика по закону
напечатаны ответственное должностное лицо, телефон и почта. Это не личный мобильный
главного энергетика, но это названный человек с должностью и с адресом страницы, на
которой он назван, — то есть строка, годная для звонка и проверяемая ссылкой.

ЗАСЛОНЫ, каждый из уже оплаченных ошибками:

  1. ИНН обязан стоять НА КАРТОЧКЕ. Иначе я припишу предприятию телефон соседней
     организации из подсказок поиска — ошибка того же рода, что «номер одного человека
     у имени другого».
  2. Телефон засчитывается, только если он телефонного вида и стоит рядом с подписью
     «Телефон» / «Контактное лицо», а не где угодно в тексте (в подвале ЕИС есть свой
     номер поддержки, и он один на все карточки).
  3. Вид номера называется явно: это РАБОЧИЙ телефон организации, а не личный. Правило
     владельца — разделять, а не отсеивать.

СРОК: 1 450 секунд, дальше пишу собранное и печатаю, сколько осталось. Молча упереться
в потолок задания — значит потерять всё.

Числа в КОНЦЕ.
"""
import collections
import io
import json
import os
import re
import ssl
import threading
import time
import urllib.parse
import urllib.request

NACHALO = time.time()
SROK = 1450
OPS = r'C:\sender\_ops'
PARK = ['park_ingest_3d.jsonl', 'park_ingest_3.jsonl', 'park_ingest_3b.jsonl',
        'park_ingest_3c.jsonl']
BAZA = os.path.join(OPS, 'PARK-BAZA-EDINAYA-3S.csv')
VYHOD = os.path.join(OPS, 'PARK-EIS-ORG-KONTAKTY-3S.jsonl')
POTOKOV = 8
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/120.0.0.0 Safari/537.36')
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
net = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx),
                                  urllib.request.ProxyHandler({}))
TEG = re.compile(r'<[^>]+>')
KARTA = re.compile(r'href="(/epz/organization/view[^"]*?)"')
TELEFON = re.compile(r'(?:\+7|8)[\s\-()]*\d{3,5}[\s\-()]*\d{2,3}[\s\-]*\d{2}[\s\-]*\d{2}')
POCHTA = re.compile(r'[A-Za-z0-9._%-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')
FIO = re.compile(r'\b([А-ЯЁ][а-яё\-]{2,}\s+[А-ЯЁ][а-яё]{2,}\s+[А-ЯЁ][а-яё]{2,}вич|'
                 r'[А-ЯЁ][а-яё\-]{2,}\s+[А-ЯЁ][а-яё]{2,}\s+[А-ЯЁ][а-яё]{2,}вна)\b')
# номер поддержки самого ЕИС стоит на КАЖДОЙ карточке — его брать нельзя
SVOI_NOMERA = {'88003332434', '8003332434', '84957873232'}
drop = os.environ.get('DROP_URL', '').rstrip('/')
tok = {'X-Drop-Token': os.environ.get('DROP_TOKEN', '')}

celi, imena = [], {}
est_kontakt = set()
if os.path.exists(BAZA):
    sh = None
    for s in io.open(BAZA, encoding='utf-8-sig'):
        p = s.rstrip('\n').split(';')
        if sh is None:
            sh = p
            continue
        if len(p) == len(sh):
            o = dict(zip(sh, p))
            if o.get('inn') and (o.get('nomer') or o.get('pochta')):
                est_kontakt.add(o['inn'])
vidno = set()
for f in PARK:
    put = os.path.join(OPS, f)
    if not os.path.exists(put):
        continue
    for s in io.open(put, encoding='utf-8'):
        try:
            o = json.loads(s)
        except Exception:  # noqa: BLE001
            continue
        i = o.get('inn')
        if not i or i in vidno:
            continue
        vidno.add(i)
        if o.get('predpriyatie'):
            imena[i] = o['predpriyatie']
        if i not in est_kontakt:
            celi.append(i)

zamok = threading.Lock()
ochered = list(celi)
potok, prichiny = [], collections.Counter()


def tyanut(u):
    with net.open(urllib.request.Request(u, headers={'User-Agent': UA,
                                                     'Accept-Language': 'ru'}),
                  timeout=40) as rs:
        return rs.read(500000).decode('utf-8', 'replace')


def odin(inn):
    poisk = ('https://zakupki.gov.ru/epz/organization/search/results.html?searchString=%s'
             '&morphology=on&sortBy=UPDATE_DATE' % inn)
    try:
        h = tyanut(poisk)
    except Exception as e:  # noqa: BLE001
        with zamok:
            prichiny['страница поиска не открылась: %s' % str(e)[:26]] += 1
        return
    m = KARTA.search(h)
    if not m:
        with zamok:
            prichiny['в выдаче нет ссылки на карточку организации'] += 1
        return
    u = 'https://zakupki.gov.ru' + m.group(1).replace('&amp;', '&')
    try:
        hk = tyanut(u)
    except Exception as e:  # noqa: BLE001
        with zamok:
            prichiny['карточка не открылась: %s' % str(e)[:26]] += 1
        return
    t = re.sub(r'\s+', ' ', TEG.sub(' ', hk))
    # ЗАСЛОН 1: ИНН обязан стоять на карточке
    if inn not in re.sub(r'\D', '', t):
        with zamok:
            prichiny['ИНН на карточке не найден — это чужая организация'] += 1
        return
    # ЗАСЛОН 2: беру только окрестность подписей, а не весь текст
    okno = ''
    for podpis in ('Контактное лицо', 'Ответственное должностное лицо', 'Телефон',
                   'Контактная информация', 'Адрес электронной почты'):
        i = t.find(podpis)
        if i >= 0:
            okno += ' ' + t[i:i + 400]
    if not okno:
        with zamok:
            prichiny['на карточке нет ни одной подписи о контактах'] += 1
        return
    tel = [x for x in TELEFON.findall(okno)
           if re.sub(r'\D', '', x) not in SVOI_NOMERA]
    poch = [x.lower() for x in POCHTA.findall(okno)]
    chel = FIO.search(okno)
    if not tel and not poch and not chel:
        with zamok:
            prichiny['подписи есть, а значений рядом нет'] += 1
        return
    with zamok:
        potok.append({'inn': inn, 'predpriyatie': imena.get(inn, '')[:180],
                      'chelovek': chel.group(1) if chel else '',
                      'dolzhnost': 'ответственное должностное лицо заказчика (карточка ЕИС)',
                      'telefon': tel[0][:32] if tel else '',
                      'vid_nomera': ('РАБОЧИЙ ТЕЛЕФОН ОРГАНИЗАЦИИ (карточка ЕИС), не личный'
                                     if tel else 'номера нет, есть имя или почта'),
                      'pochta': poch[0] if poch else '',
                      'istochniki': u, 'istochnikov': 1,
                      'kto': '3-я сессия, карточка организации ЕИС'})
        prichiny['взято'] += 1


def rabotnik():
    while True:
        with zamok:
            if not ochered or time.time() - NACHALO > SROK:
                return
            i = ochered.pop(0)
        try:
            odin(i)
        except Exception as e:  # noqa: BLE001
            with zamok:
                prichiny['исключение: %s' % str(e)[:30]] += 1


nitki = [threading.Thread(target=rabotnik) for _ in range(POTOKOV)]
for n in nitki:
    n.start()
for n in nitki:
    n.join()

with io.open(VYHOD, 'w', encoding='utf-8') as f:
    for o in potok:
        f.write(json.dumps(o, ensure_ascii=False) + '\n')
try:
    rq = urllib.request.Request('%s/%s' % (drop, os.path.basename(VYHOD)),
                                data=io.open(VYHOD, 'rb').read(), method='PUT', headers=tok)
    vyl = net.open(rq, timeout=300).read().decode('utf-8', 'replace')[:90]
except Exception as e:  # noqa: BLE001
    vyl = 'НЕ ВЫЛОЖЕНО: %s' % str(e)[:60]

s_tel = [o for o in potok if o['telefon']]
s_chel = [o for o in potok if o['chelovek']]
print('\n\n########## ПЕРВЫЕ ДЕСЯТЬ')
for o in potok[:10]:
    print('  %-12s %-26s %-22s %s' % (o['inn'], (o['predpriyatie'] or '—')[:26],
                                      (o['chelovek'] or '—')[:22], o['telefon']))
print('\n########## ЧИСЛА')
print('  предприятий в парке всего     %5d' % len(vidno))
print('  из них БЕЗ контакта в базе    %5d' % len(celi))
print('  обойдено за заход             %5d  (осталось в очереди %d)'
      % (len(celi) - len(ochered), len(ochered)))
print('  строк добыто                  %5d' % len(potok))
print('     с телефоном                %5d  (предприятий %d)'
      % (len(s_tel), len({o['inn'] for o in s_tel})))
print('     с названным человеком      %5d' % len(s_chel))
for k, v in prichiny.most_common():
    print('     %-52s %5d' % (k[:52], v))
print('  секунд потрачено %d из %d' % (time.time() - NACHALO, SROK))
print('  выложено: %s' % vyl)
print('ИТОГ ' + json.dumps({'цели': len(celi), 'взято': len(potok),
                            'с телефоном': len(s_tel), 'осталось': len(ochered)},
                           ensure_ascii=False))

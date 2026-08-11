# -*- coding: utf-8 -*-
"""КАРТОЧКА ОРГАНИЗАЦИИ ЕИС ПО СОБСТВЕННОЙ ОЧЕРЕДИ. Замер показал, где на самом деле дыра.

Очередь «машина есть, контакта нет» — 3 643 предприятия, и я держала её как список работы,
не спросив, ЧЕМ КАЖДОЕ ИЗ НИХ УЖЕ ПРОБОВАЛИ. Спросила — счёт по потокам всех пяти каналов
контактов:

    предприятий в очереди                        3643
    прошли 0 каналов                             3579
    прошли 1 канал                                 47
    прошли 2 канала                                17

То есть 3 579 предприятий с ДОКАЗАННОЙ машиной не видели ни одного канала добычи контакта.
Это не «нужен новый канал» — это старый канал, ни разу по ним не пущенный. Разница важная:
новый канал надо изобретать и проверять, а этот уже проверен дважды (по моему парку 429
строк и 162 телефона, по парку 1-й сессии 845 строк и 369 телефонов).

ЧТО ИЗМЕНЕНО ПРОТИВ ИСХОДНОГО СБОРЩИКА. Только вход: цели берутся из моей очереди
`PARK-BEZ-KONTAKTA-3S.csv`, а не из файла соседа. Заслоны, разбор карточки, вид номера,
накопление файла и срок задания — те же, менять их не за чем.

ЖУРНАЛ СПРОШЕННЫХ НАКАПЛИВАЕТСЯ, а не заменяется: перед заходом читаются ОБА прежних
потока карточек организации (`PARK-EIS-ORG-KONTAKTY-3S.jsonl` и `...-1S-3S.jsonl`), и ИНН,
по которым канал уже ходил, второй раз не берутся. Тот же класс, что стоил мне 1 827
повторных платных запросов в обходе, когда журнал читал один поток из двух.

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
VYHOD = os.path.join(OPS, 'PARK-EIS-ORG-OCHERED-3S.jsonl')
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

# Флаг берётся И из окружения, И из доводов: раннер прокидывает `argv` наверняка, а про
# `env` я не проверяла — а непроверенный путь запуска это ещё один способ получить ноль.
import sys as _sys
ZANOVO = (os.environ.get('P25_ZANOVO') == '1') or ('--zanovo' in _sys.argv)

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
# ЦЕЛИ — ИЗ СОБСТВЕННОЙ ОЧЕРЕДИ «машина есть, контакта нет».
vidno = set()
OCHERED_FAJL = os.path.join(OPS, 'PARK-BEZ-KONTAKTA-3S.csv')
# ЖУРНАЛ: по каким ИНН канал УЖЕ ходил. Читаются оба прежних потока, а не один.
POTOKI_KANALA = ['PARK-EIS-ORG-KONTAKTY-3S.jsonl', 'PARK-EIS-ORG-KONTAKTY-1S-3S.jsonl',
                 os.path.basename(VYHOD)]
uzhe_hodili = set()
for _f in POTOKI_KANALA:
    _p = os.path.join(OPS, _f)
    if not os.path.exists(_p):
        print('журнал канала: НЕТ ПОТОКА %s' % _f)
        continue
    _bylo = len(uzhe_hodili)
    for _s in io.open(_p, encoding='utf-8', errors='replace'):
        try:
            _z = json.loads(_s)
        except Exception:  # noqa: BLE001
            continue
        if _z.get('inn'):
            uzhe_hodili.add(str(_z['inn']).strip())
    print('журнал канала: %s дал %d новых ИНН' % (_f, len(uzhe_hodili) - _bylo))
print('журнал канала: всего уже хожено %d ИНН' % len(uzhe_hodili))

propushcheno = collections.Counter()
if os.path.exists(OCHERED_FAJL):
    _sh = None
    for _s in io.open(OCHERED_FAJL, encoding='utf-8-sig'):
        _p = _s.rstrip('\n').split(';')
        if _sh is None:
            _sh = _p
            continue
        if len(_p) != len(_sh):
            continue
        _o = dict(zip(_sh, _p))
        _i = (_o.get('inn') or '').strip()
        if not _i.isdigit() or _i in vidno:
            continue
        vidno.add(_i)
        if _o.get('predpriyatie'):
            imena[_i] = _o['predpriyatie'][:180]
        if _i in est_kontakt:
            propushcheno['контакт уже есть в базе'] += 1
            continue
        # ЗАНОВО: когда меняется ЗАСЛОН, прежние вердикты недействительны — журнал спрошенных
        # тогда не бережёт работу, а прячет непроверенное. Флаг ставится руками и только под
        # смену заслона, чтобы обычный заход по-прежнему не платил дважды.
        if _i in uzhe_hodili and not ZANOVO:
            propushcheno['канал по этому ИНН уже ходил'] += 1
            continue
        celi.append(_i)
else:
    print('ОЧЕРЕДИ НЕТ НА МЕСТЕ: %s' % OCHERED_FAJL)
for _k, _v in propushcheno.most_common():
    print('вход: пропуск, %s — %d' % (_k, _v))

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
    # ЗАСЛОН 1: ИНН обязан стоять на карточке ПОСЛЕ СЛОВА «ИНН», а не где угодно.
    #
    # Прежняя запись заслона была `if inn not in re.sub(r'\D', '', t)`: все цифры страницы
    # склеивались в одну длинную строку, и десятизначный кусок находился в ней почти всегда —
    # по номерам закупок, суммам, датам. Заслон пропускал что угодно, и его счётчик «чужая
    # организация» за прогон по 3 579 предприятиям показал РОВНО НОЛЬ. Ноль был диагнозом
    # прибора: заслон не срабатывал, потому что не мог.
    #
    # Что заставило посмотреть: контроль выдачи. Выдуманный ИНН 9999999999 вернул
    # 193 744 знака и ТРИ ссылки на карточки организаций — то есть выдача при непопадании
    # показывает ЧУЖИЕ организации, а сборщик берёт первую ссылку. Единственное, что стоит
    # между чужой карточкой и базой, — этот заслон.
    #
    # Строгая форма — та же, которую 1-я сессия купила на эхо-дефекте карточки 223-ФЗ:
    # ИНН должен стоять рядом со своей подписью.
    if not re.search(r'ИНН[^0-9]{0,12}' + re.escape(inn), t):
        with zamok:
            prichiny['ИНН после слова «ИНН» на карточке не стоит — чужая организация'] += 1
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

# НАКОПЛЕНИЕ, А НЕ ПЕРЕЗАПИСЬ. Второй заход этого скрипта СТЁР результат первого: файл
# открывался режимом 'w', и 429 строк (162 телефона) заменились полусотней новых. В единой
# базе это тут же дало 8 921 -> 8 541 строку и 1 338 -> 958 предприятий, то есть работа
# ночи ушла молча. Счётчик при этом честно печатал «взято 50» — и выглядел как успех.
# Читаю свой прежний выход и складываю с новым по ключу (ИНН + телефон + почта).
staroe = {}
if os.path.exists(VYHOD):
    for s in io.open(VYHOD, encoding='utf-8'):
        try:
            o = json.loads(s)
        except Exception:  # noqa: BLE001
            continue
        staroe[(o.get('inn'), o.get('telefon'), o.get('pochta'))] = o
bylo_ranshe = len(staroe)
for o in potok:
    staroe[(o.get('inn'), o.get('telefon'), o.get('pochta'))] = o
potok = list(staroe.values())
print('  было в файле до этого захода: %d, стало после склейки: %d' % (bylo_ranshe, len(potok)))
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
print('  предприятий в очереди всего   %5d' % len(vidno))
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

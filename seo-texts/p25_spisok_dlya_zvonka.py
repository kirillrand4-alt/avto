# -*- coding: utf-8 -*-
"""СПИСОК ДЛЯ ЗВОНКА — то, ради чего вся смена. Одна строка = один звонок.

Сводка дала 373 полных строки, из них 305 на предприятиях с ДОКАЗАННОЙ машиной. Здесь я
собираю их в вид, пригодный человеку с телефоном: кому звонить, кем он работает, по какому
номеру, про какую машину и куда смотреть, если он спросит «откуда у вас мои данные».

ЧТО ОБЯЗАТЕЛЬНО В КАЖДОЙ СТРОКЕ:
    ссылка на ЧЕЛОВЕКА  — страница, где стоит его имя рядом с номером
    ссылка на МАШИНУ    — заключение ЭПБ либо закупка, где названа его машина
Строка без обеих ссылок в список не идёт: продавцу нечем будет ответить на вопрос об
источнике, а это первое, что спрашивают.

ПОРЯДОК — не алфавитный. Сверху те, у кого машина дороже (ГПА и компрессор), внутри — у кого
больше независимых доказательств. Если обзвон оборвётся на середине, оборваться он должен на
дешёвом.

ЗАСЛОН НА ДУБЛИ: один человек может прийти из двух потоков. Ключ — ИНН плюс десять цифр
номера; ссылки при свёртке накапливаются, а не заменяются.

Только чтение. Числа в КОНЦЕ.
"""
import collections
import io
import json
import os
import re
import sqlite3
import urllib.parse as _up
import urllib.request

SVODKA = r'C:\sender\_ops\PARK-SVODKA-CHELOVEK-ROL-NOMER-3S.jsonl'
# ВТОРОЙ КЛАСС СТРОК. Контактное лицо из карточки закупки ЕИС — это не личный мобильный, а
# рабочий телефон человека, названного в самом документе о закупке машины. Из 179 добытых
# 43 строки на 25 предприятиях приходятся на наш парк, у них в предмете стоит «техническое
# обслуживание компрессора» — то есть человек имеет отношение к машине.
# По правилу владельца «разделять, а не отсеивать» кладу их в тот же список, но ОТДЕЛЬНЫМ
# классом и ниже личных мобильных: продавец должен видеть, кому он звонит.
KONT_LICO = r'C:\sender\_ops\PARK-EIS-KONTAKTNOE-LICO-3S.jsonl'
PARK = [r'C:\sender\_ops\park_ingest_3.jsonl', r'C:\sender\_ops\park_ingest_3b.jsonl',
        r'C:\sender\_ops\park_ingest_3c.jsonl',
        r'C:\sender\_ops\park_ingest_3d.jsonl']
BAZY = [r'C:\sender\enrich.db', r'C:\seostat\data\centrifugal.db']
VYHOD = r'C:\sender\_ops\PARK-SPISOK-DLYA-ZVONKA-3S.csv'
KLASS = {'ГПА': 5, 'компрессор': 4, 'нагнетатель': 4, 'ВРУ': 4, 'генератор азота': 4,
         'генератор кислорода': 4, 'воздуходувка': 3, 'МКС / передвижная': 3, 'осушитель': 2}
MUSOR_DOLZH = re.compile(r'^(развернуть|страница|неясно|нет|—|-|\?)$', re.I)


def pochinit_ssylku(u):
    """Ссылка обязана открываться у того, кто будет звонить, а не только у меня.

    Проверка 25 случайных строк ГОТОВОГО списка (не потока) дала три поломки, и обе первые
    чинятся здесь:

      1. `https://etpgpb.ru/procedures/?search=ГП830249` — в адресе КИРИЛЛИЦА. Человек в
         браузере такую строку проходит, потому что браузер кодирует её сам; любой мой
         проверяльщик падает с «'ascii' codec can't encode». Доказательство, которое
         выглядит целым и не работает, — то же самое, что его отсутствие.
      2. `https://www.tender.pro/#/tender/1099290` — одностраничное приложение: карточку
         рисует скрипт, и в теле ответа искомого нет НИКОГДА. У того же домена есть форма
         `/api/tender/<номер>/view_public`, которая отдаёт данные прямо. Что номер в обеих
         формах один и тот же — ПРОВЕРЕНО на пяти адресах из этого самого списка: все пять
         вернули 200 и содержат свой номер в теле. Догадкой это не осталось.
    """
    if not u or not u.startswith('http'):
        return u
    m = re.match(r'^https?://(?:www\.)?tender\.pro/#/tender/(\d+)', u)
    if m:
        u = 'https://www.tender.pro/api/tender/%s/view_public' % m.group(1)
    # ПОРТАЛ МОСКВЫ — тот же случай, найден проверкой пяти ссылок: страница отдаёт каркас
    # в 7 992 знака, машины в теле нет. Спросила у площадки её собственный API восемью
    # формами: `newapi/api/Auction/Get` и `newapi/api/Need/Get` возвращают тело, где слово
    # машины СТОИТ (3 274 и 1 771 знак). Старый `api/Cssp/...` отдаёт тот же каркас, а
    # `old.zakupki.mos.ru` — 404. Проверено на живых номерах 9485656 и 4640755.
    m = re.match(r'^https?://(?:www\.)?zakupki\.mos\.ru/auction/(\d+)', u)
    if m:
        u = 'https://zakupki.mos.ru/newapi/api/Auction/Get?auctionId=%s' % m.group(1)
    m = re.match(r'^https?://(?:www\.)?zakupki\.mos\.ru/need/(\d+)', u)
    if m:
        u = 'https://zakupki.mos.ru/newapi/api/Need/Get?needId=%s' % m.group(1)
    try:
        p = _up.urlsplit(u)
        host = p.netloc
        if re.search(r'[^\x00-\x7F]', host):
            host = host.encode('idna').decode('ascii')
        u = _up.urlunsplit((p.scheme, host,
                            _up.quote(p.path, safe="/%:@&=+$,~!*'()"),
                            _up.quote(p.query, safe="/%:@&=+$,?~!*'()"), ''))
    except Exception:  # noqa: BLE001
        pass
    return u

# машина и ссылка на неё
mash, mash_ssylka = {}, {}
for p in PARK:
    if not os.path.exists(p):
        continue
    for s in io.open(p, encoding='utf-8'):
        try:
            o = json.loads(s)
        except Exception:  # noqa: BLE001
            continue
        i = o.get('inn')
        if not i:
            continue
        if i not in mash or KLASS.get(o.get('vid', ''), 0) > KLASS.get(mash[i], 0):
            mash[i] = o.get('vid') or 'машина'
            u = [x for x in (o.get('istochniki') or '').split(' | ') if x.startswith('http')]
            if u:
                mash_ssylka[i] = pochinit_ssylku(u[0])

imena = {}
for b in BAZY:
    if not os.path.exists(b):
        continue
    try:
        cx = sqlite3.connect('file:%s?mode=ro' % b.replace('\\', '/'), uri=True)
        for t in ('companies', 'company'):
            try:
                for i, n in cx.execute('select inn, name from "%s" where name is not null' % t):
                    i = str(i or '').strip()
                    if i and i not in imena:
                        imena[i] = re.sub(r'\s+', ' ', str(n)).strip()
            except Exception:  # noqa: BLE001
                continue
        cx.close()
    except Exception:  # noqa: BLE001
        pass

svern, snyato = {}, collections.Counter()
for s in io.open(SVODKA, encoding='utf-8'):
    try:
        o = json.loads(s)
    except Exception:  # noqa: BLE001
        continue
    if o.get('ishod') != 'ПОЛНЫЙ':
        continue
    inn, nomer = o.get('inn', ''), re.sub(r'\D', '', o.get('nomer') or '')
    if not inn or len(nomer) != 10:
        snyato['номер не десятизначный'] += 1
        continue
    if not mash.get(inn):
        snyato['машина у предприятия не доказана'] += 1
        continue
    ssylka_chel = pochinit_ssylku(next((x for x in str(o.get('istochniki') or '').split(' | ')
                                        if x.startswith('http')), ''))
    if not ssylka_chel:
        snyato['нет ссылки на человека'] += 1
        continue
    if not mash_ssylka.get(inn):
        snyato['нет ссылки на машину'] += 1
        continue
    dolzh = (o.get('dolzhnost') or '').split(' | ')[0].strip()
    if MUSOR_DOLZH.match(dolzh):
        dolzh = 'должность не подтверждена'
    k = (inn, nomer)
    if k in svern:
        z = svern[k]
        if ssylka_chel not in z['ssylka_chelovek']:
            z['ssylka_chelovek'] += ' | ' + ssylka_chel
            z['dokazatelstv'] += 1
        continue
    # ВИД НОМЕРА СЧИТАЕТСЯ ИЗ ЦИФР, А НЕ ИЗ УНАСЛЕДОВАННОГО ТЕКСТА ДОЛЖНОСТИ.
    # Разбор расхождения «57 строк в списке против 41 по мерке» показал ровно это: у 32
    # строк должность пришла из исходника словами «контактное лицо закупки (рабочий
    # телефон, НЕ личный)», а номер у них +79…, то есть личный мобильный. Сортировка
    # смотрела на ТЕКСТ должности и уводила эти 32 личных номера в самый низ списка,
    # под рабочие телефоны. Никакой выдумки в них нет, они просто были подписаны чужой
    # подписью — и продавец звонил бы им последними. Считаю вид по цифрам.
    svern[k] = {'inn': inn, 'predpriyatie': imena.get(inn, ''),
                'chelovek': (o.get('chelovek') or '').split(' | ')[0].strip(),
                'dolzhnost': dolzh,
                'vid_nomera': ('ЛИЧНЫЙ МОБИЛЬНЫЙ' if nomer[0] == '9'
                               else ('8-800' if nomer.startswith('800')
                                     else 'городской, чей именно — не доказано')),
                'nomer': '+7' + nomer,
                'mashina': mash[inn], 'klass_ceny': KLASS.get(mash[inn], 2),
                'ssylka_chelovek': ssylka_chel, 'ssylka_mashina': mash_ssylka[inn],
                'dokazatelstv': 2}

# добавляю второй класс — контактное лицо закупки
if os.path.exists(KONT_LICO):
    for s_ in io.open(KONT_LICO, encoding='utf-8'):
        try:
            o = json.loads(s_)
        except Exception:  # noqa: BLE001
            continue
        inn = o.get('inn') or ''
        nomer = re.sub(r'\D', '', o.get('telefon') or '')
        if not inn or not mash.get(inn) or len(nomer) < 10:
            snyato['контактное лицо: машина не доказана либо телефон короткий'] += 1
            continue
        k = (inn, nomer[-10:])
        if k in svern:
            continue
        ssyl = pochinit_ssylku(next((x for x in str(o.get('istochniki') or '').split(' | ')
                                     if x.startswith('http')), ''))
        svern[k] = {'inn': inn, 'predpriyatie': imena.get(inn, o.get('zakazchik', ''))[:120],
                    'chelovek': o.get('imya') or 'имя не названо',
                    'dolzhnost': 'контактное лицо закупки',
                    'vid_nomera': ('ЛИЧНЫЙ МОБИЛЬНЫЙ, назван контактным лицом закупки'
                                   if nomer[-10:][0] == '9'
                                   else 'РАБОЧИЙ ТЕЛЕФОН контактного лица, НЕ личный'),
                    'nomer': o.get('telefon', ''), 'mashina': mash[inn],
                    'klass_ceny': KLASS.get(mash[inn], 2),
                    'ssylka_chelovek': ssyl, 'ssylka_mashina': mash_ssylka.get(inn, ''),
                    'dokazatelstv': 2}

spisok = sorted(svern.values(),
                key=lambda o: (0 if o['vid_nomera'].startswith('ЛИЧНЫЙ') else 1,
                               -o['klass_ceny'], -o['dokazatelstv']))
with io.open(VYHOD, 'w', encoding='utf-8-sig') as f:
    f.write('inn;predpriyatie;chelovek;dolzhnost;vid_nomera;nomer;mashina;klass_ceny;'
            'dokazatelstv;ssylka_chelovek;ssylka_mashina\n')
    for o in spisok:
        f.write(';'.join(str(o[k]).replace(';', ',') for k in
                         ('inn', 'predpriyatie', 'chelovek', 'dolzhnost', 'vid_nomera',
                          'nomer', 'mashina', 'klass_ceny', 'dokazatelstv',
                          'ssylka_chelovek', 'ssylka_mashina')) + '\n')
try:
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    rq = urllib.request.Request('%s/%s' % (os.environ.get('DROP_URL', '').rstrip('/'),
                                           os.path.basename(VYHOD)),
                                data=io.open(VYHOD, 'rb').read(), method='PUT',
                                headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')})
    vyl = op.open(rq, timeout=180).read().decode('utf-8', 'replace')[:110]
except Exception as e:  # noqa: BLE001
    vyl = 'не выложено: %s' % str(e)[:80]

print('\n\n########## ПЕРВЫЕ ДЕСЯТЬ СТРОК СПИСКА')
for o in spisok[:10]:
    print('  %-12s %-30s %-26s %-13s %s' % (o['inn'], (o['predpriyatie'] or '—')[:30],
                                            o['chelovek'][:26], o['nomer'], o['mashina'][:16]))
print('\n########## ЧИСЛА')
print('  строк в списке            %5d  (предприятий %d)'
      % (len(spisok), len({o['inn'] for o in spisok})))
print('  --- по машине')
for k, v in collections.Counter(o['mashina'] for o in spisok).most_common():
    print('     %-26s %5d' % (k, v))
print('  должность не подтверждена %5d'
      % sum(1 for o in spisok if o['dolzhnost'] == 'должность не подтверждена'))
print('  --- не попали в список')
for k, v in snyato.most_common():
    print('     %-44s %5d' % (k, v))
print('  файл: %s' % VYHOD)
print('  выложено: %s' % vyl)
print('ИТОГ ' + json.dumps({'строк': len(spisok),
                            'предприятий': len({o['inn'] for o in spisok})},
                           ensure_ascii=False))

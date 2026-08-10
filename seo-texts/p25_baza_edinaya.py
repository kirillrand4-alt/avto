# -*- coding: utf-8 -*-
"""ЕДИНАЯ ОТДЕЛЬНАЯ БАЗА парка: одна строка на «предприятие + номер», источники НАКОПЛЕНЫ.

Владелец просил базу отдельную от прежней и чтобы каждый контакт и факт доказывался ссылкой,
а если ссылок несколько — чтобы в базе стояли ВСЕ. До сих пор мои данные жили десятком
потоков, и один и тот же номер, добытый двумя разными каналами, лежал двумя строками с одной
ссылкой у каждой. Это ровно та потеря, про которую владелец писал 30.07: подтверждённое
дважды становилось неотличимо от подтверждённого однажды.

Здесь склейка по ключу «ИНН + десять цифр номера», и при склейке:

    istochniki      все уникальные ссылки через « | », сколько бы их ни было
    istochnikov     их число
    kanalov         сколько РАЗНЫХ каналов добычи дали этот же номер (обратный ход, сайт,
                    карточка ЕИС, разбор моделью…). Два канала — это независимое
                    подтверждение, и оно ценнее двух ссылок одного канала.
    vid_nomera      вид называется явно и НЕ смешивается: личный мобильный, рабочий прямой,
                    приёмная, 8-800, добавочный. Правило владельца — разделять, а не
                    отсеивать: приёмная это путь к человеку через коммутатор.

Вторым файлом идут предприятия с ДОКАЗАННОЙ машиной и БЕЗ единого контакта — это очередь
работы, а не отход: пока она не названа числом, её не видно.

Только чтение входов. Числа в КОНЦЕ.
"""
import collections
import io
import json
import os
import re
import sqlite3
import urllib.parse as _up
import urllib.request

OPS = r'C:\sender\_ops'
PARK = ['park_ingest_3.jsonl', 'park_ingest_3b.jsonl', 'park_ingest_3c.jsonl', 'park_ingest_3d.jsonl']
# канал -> файл. Канал называю, потому что независимость подтверждения меряется каналами.
KANALY = [
    ('контактная база', 'PARK-KONTAKTY-3S-CHESTNO.jsonl'),
    ('обратный ход', 'PARK-OBRATNYY-PROVERENO-3S.jsonl'),
    ('обратный ход по именам 1-й сессии', 'PARK-OBRATNYY-1S-PROVERENO-3S.jsonl'),
    ('обратный ход по именам 2-й сессии', 'PARK-OBRATNYY-2S-PROVERENO-3S.jsonl'),
    ('обратный ход, старый поток', 'PARK-OBRATNYY-STARYY-PROVERENO-3S.jsonl'),
    ('обратный ход, старый поток 2', 'PARK-OBRATNYY-STARYY2-PROVERENO-3S.jsonl'),
    ('обратный ход по новым именам 2-й сессии', 'PARK-OBRATNYY-2S-NOVYE-PROVERENO-3S.jsonl'),
    # Обратный ход, пущенный по ЖИВОЙ базе: 2 025 названных людей без личного номера,
    # спрошено 1 886. Сырьё — 108 человек «с личным мобильным», после оплаченных заслонов
    # (номер у нескольких ИНН, номер не в цитате, однофамилец, ближе стоит другое ФИО,
    # сборник утёкших данных) осталось 60 со ссылкой. Разница в 48 — цена заслонов, и она
    # называется вслух, а не прячется.
    ('обратный ход по живой базе', 'PARK-OBRATNYY-BAZA-PROVERENO-3S.jsonl'),
    ('сайт предприятия', 'PARK-SAYTY-TELEFONY-3S.jsonl'),
    ('сайт предприятия, разбор моделью', 'PARK-SAYTY-LICA-3S.jsonl'),
    ('контактное лицо карточки ЕИС', 'PARK-OTKAZY-RAZOBRANY-3S.jsonl'),
    # Канал открыт под 836 новых предприятий, пришедших из ЕИС без единого контакта:
    # на карточке организации-заказчика по закону напечатаны ответственное лицо,
    # телефон и почта. 429 строк, из них 162 с телефоном и 70 с названным человеком.
    ('карточка организации ЕИС', 'PARK-EIS-ORG-KONTAKTY-3S.jsonl'),
    # Тот же канал, пущенный по парку ПЕРВОЙ сессии (5 146 предприятий, из них 4 037 без
    # контакта): 845 строк, 369 телефонов, 192 названных человека за 518 с. Их машина
    # доказана не моими потоками, а их выдачей, поэтому канал назван отдельно и машина
    # берётся с ИХ ссылкой — источник обязан быть виден, а не растворён в моём парке.
    ('карточка организации ЕИС, парк 1-й сессии', 'PARK-EIS-ORG-KONTAKTY-1S-3S.jsonl'),
]
# Парк соседей как источник ДОКАЗАТЕЛЬСТВА МАШИНЫ для тех ИНН, которых нет в моих потоках.
# Беру только строки, где у них стоит «есть открываемое доказательство машины» и лежит
# ссылка: без ссылки факт в базу не идёт — правило владельца.
PARK_SOSEDEY = 'PARK-VYDACHA-PREDPRIYATIYA.csv'
BAZY = [r'C:\sender\enrich.db', r'C:\seostat\data\centrifugal.db',
        r'C:\seostat\drop\drop-storage\atlas_copco.db']
VYHOD = os.path.join(OPS, 'PARK-BAZA-EDINAYA-3S.csv')
OCHERED = os.path.join(OPS, 'PARK-BEZ-KONTAKTA-3S.csv')
KLASS = {'ГПА': 5, 'компрессор': 4, 'нагнетатель': 4, 'ВРУ': 4, 'генератор азота': 4,
         'генератор кислорода': 4, 'воздуходувка': 3, 'МКС / передвижная': 3, 'осушитель': 2}
drop = os.environ.get('DROP_URL', '').rstrip('/')
tok = {'X-Drop-Token': os.environ.get('DROP_TOKEN', '')}
op = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def desyat(t):
    c = re.sub(r'\D', '', str(t or ''))
    if len(c) == 11 and c[0] in '78':
        c = c[1:]
    return c if len(c) == 10 else ''


def prigodno_k_perehodu(u):
    """Ссылка обязана ОТКРЫВАТЬСЯ, а не только выглядеть ссылкой.

    Замер по базе: 300 ссылок содержат кириллицу в адресе или в имени хоста
    (`ural.gosnadzor.ru/…?поиск=…` — 209, `мосводосток.рф` — 13, `мосавтодор.рус` — 8).
    Любой переход по такому адресу падает на «'ascii' codec can't encode», то есть
    доказательство есть в базе, а открыть его нельзя ни мне, ни продавцу. Здесь адрес
    приводится к виду, по которому переход выполняется: хост в punycode, путь и запрос
    в процентном кодировании. Ничего не выбрасывается — меняется только запись адреса.
    """
    # ХВОСТ ПОСЛЕ РЕШЁТКИ НЕ ТЕРЯЕТСЯ. Ту же ошибку я уже чинила в скрипте снимков и НЕ
    # довезла сюда — а база кормит список звонка. Итог виден числами: у 36 строк ссылка
    # на человека превратилась в `https://www.tender.pro/`, автопилот стал вечно
    # переснимать их с главной страницы, и проверенных стало 158 -> 136 -> 104.
    # Починка, не доехавшая до второго места, — это половина починки.
    m = re.match(r'^https?://(?:www\.)?tender\.pro/(?:#/)?tender/(\d+)', u or '')
    if m:
        u = 'https://www.tender.pro/api/tender/%s/view_public' % m.group(1)
    try:
        p = _up.urlsplit(u)
        host = p.netloc
        if re.search(r'[^\x00-\x7F]', host):
            host = host.encode('idna').decode('ascii')
        return _up.urlunsplit((p.scheme, host,
                               _up.quote(p.path, safe="/%:@&=+$,~!*'()"),
                               _up.quote(p.query, safe="/%:@&=+$,?~!*'()"),
                               _up.quote(p.fragment, safe="/%:@&=+$,?~!*'()")))
    except Exception:  # noqa: BLE001
        return u


def klyuch_ssylki(u):
    """Один и тот же адрес — один источник, как бы его ни записали.

    Нашлось глазами на проверке пяти ссылок: у АО «БСК» в списке источников лежат
    `...conclusion/2-%D0%A2%D0%A3-897549-2026` и `...conclusion/2-%d0%a2%d0%a3-897549-2026`
    — одна и та же страница, отличается РЕГИСТР процентного кодирования. Сравнение шло
    строкой, поэтому дубль считался вторым источником. По живой базе таких строк 112, и
    они приписали 114 несуществующих подтверждений. Это бьёт по числу, которым владелец
    меряет провенанс: «источников» становится больше, чем доказательств.
    Здесь адрес приводится к сравнимому виду: проценты в верхний регистр, хвостовой слэш
    и `www.` отброшены. Сам адрес в базе остаётся как был — сравнивается только ключ.
    """
    u = (u or '').strip()
    u = re.sub(r'%[0-9a-fA-F]{2}', lambda m: m.group(0).upper(), u)
    u = re.sub(r'^https?://(?:www\.)?', '', u).rstrip('/')
    return u.lower()


def ssylki_iz(o):
    out = []
    for k in ('istochniki', 'istochnik', 'ssylka', 'url'):
        v = o.get(k)
        if not v:
            continue
        for u in str(v).split(' | '):
            u = prigodno_k_perehodu(u.strip())
            if u.startswith('http') and u not in out:
                out.append(u)
    return out


mash, mash_ssylka, mash_ist = {}, {}, collections.defaultdict(list)
imena_sosedey = {}
for p in PARK:
    put = os.path.join(OPS, p)
    if not os.path.exists(put):
        continue
    for s in io.open(put, encoding='utf-8'):
        try:
            o = json.loads(s)
        except Exception:  # noqa: BLE001
            continue
        i = o.get('inn')
        if not i:
            continue
        v = o.get('vid') or 'машина'
        if i not in mash or KLASS.get(v, 0) > KLASS.get(mash[i], 0):
            mash[i] = v
        for u in ssylki_iz(o):
            if u not in mash_ist[i]:
                mash_ist[i].append(u)
        if i not in mash_ssylka and mash_ist[i]:
            mash_ssylka[i] = mash_ist[i][0]

# ПАРК СОСЕДЕЙ. Их 5 149 ИНН доказаны их же ссылками; мои потоки этих предприятий не знают,
# и без этого шага 369 добытых телефонов повисли бы без машины, то есть не доехали бы до
# списка звонка. Вид машины беру из их колонки типов, ссылку — из их `ssylka_luchshaya`.
sosedey_vzyato = 0
try:
    _syr = op.open(urllib.request.Request('%s/%s' % (drop, PARK_SOSEDEY), headers=tok),
                   timeout=300).read().decode('utf-8-sig', 'replace')
    _sh = None
    for _s in _syr.splitlines():
        _p = _s.split(';')
        if _sh is None:
            _sh = _p
            continue
        if len(_p) != len(_sh):
            continue
        _d = dict(zip(_sh, _p))
        _i = (_d.get('inn') or '').strip()
        _u = prigodno_k_perehodu((_d.get('ssylka_luchshaya') or '').strip())
        if not _i.isdigit() or not _u.startswith('http'):
            continue
        if 'доказательств' not in (_d.get('dokazano') or ''):
            continue
        _v = next((x.strip() for x in (_d.get('tipy') or '').split('|') if x.strip()), 'машина')
        if _i not in mash:
            mash[_i] = _v
            sosedey_vzyato += 1
        if _u not in mash_ist[_i]:
            mash_ist[_i].append(_u)
        mash_ssylka.setdefault(_i, _u)
        if _d.get('nazvanie'):
            imena_sosedey[_i] = _d['nazvanie'].strip('"').replace('""', '"')
except Exception as _e:  # noqa: BLE001
    print('парк соседей не прочитан: %s' % str(_e)[:60])

imena = dict(imena_sosedey)
for b in BAZY:
    if not os.path.exists(b):
        continue
    try:
        cx = sqlite3.connect('file:%s?mode=ro' % b.replace('\\', '/'), uri=True)
        for t in ('companies', 'company', 'predpriyatiya'):
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

def stroki_kanala(fajl):
    """Часть потоков живёт на сервере, часть — в песочнице и попадает сюда только через дроп.

    Разбор страниц моделью идёт в песочнице (ключ провайдера лежит там), и его результат на
    сервере не появляется сам. Молча пропустить такой канал — значит недосчитать людей и
    не узнать об этом: счётчик покажет ровно то, что прочитал. Поэтому: нет файла рядом —
    беру его с дропа, и в любом случае печатаю, откуда он взят.
    """
    put = os.path.join(OPS, fajl)
    if os.path.exists(put):
        return io.open(put, encoding='utf-8').read().splitlines(), 'с сервера'
    try:
        syr = op.open(urllib.request.Request('%s/%s' % (drop, fajl), headers=tok),
                      timeout=240).read().decode('utf-8', 'replace')
        return syr.splitlines(), 'с дропа'
    except Exception as e:  # noqa: BLE001
        return [], 'НЕТ НИГДЕ: %s' % str(e)[:40]


svern, prochli = {}, collections.Counter()
for kanal, fajl in KANALY:
    stroki_f, otkuda_f = stroki_kanala(fajl)
    prochli['%s: файл %s' % (kanal, otkuda_f)] += len(stroki_f)
    if not stroki_f:
        continue
    for s in stroki_f:
        try:
            o = json.loads(s)
        except Exception:  # noqa: BLE001
            continue
        inn = str(o.get('inn') or '').strip()
        if not inn:
            continue
        # у сайта телефоны лежат списком в одном поле — разворачиваю в отдельные строки
        nomera = []
        if o.get('telefony'):
            nomera = [x for x in str(o['telefony']).split(' | ') if x.strip()]
        elif o.get('nomer') or o.get('telefon'):
            nomera = [str(o.get('nomer') or o.get('telefon'))]
        pochty = [x for x in str(o.get('pochty') or o.get('pochta') or '').split(' | ')
                  if '@' in x]
        us = ssylki_iz(o)
        chel = str(o.get('chelovek') or o.get('imya') or o.get('fio') or '').split(' | ')[0]
        dolzh = str(o.get('dolzhnost') or '').split(' | ')[0]
        if not nomera and pochty:
            nomera = ['']
        for nm in nomera:
            d = desyat(nm)
            if not d and not pochty:
                prochli['%s: номер не десятизначный' % kanal] += 1
                continue
            vid = str(o.get('vid_nomera') or '').strip()
            if not vid:
                vid = ('ЛИЧНЫЙ МОБИЛЬНЫЙ' if (d and d[0] == '9' and chel)
                       else ('мобильный без имени' if d and d[0] == '9'
                             else ('8-800' if d.startswith('800') else
                                   'общий телефон предприятия')))
            k = (inn, d, chel.upper()[:24])
            z = svern.get(k)
            if not z:
                z = svern[k] = {'inn': inn, 'predpriyatie': imena.get(inn, ''),
                                'chelovek': chel, 'dolzhnost': dolzh,
                                'nomer': ('+7' + d) if d else '',
                                'vid_nomera': vid,
                                'dobavochnyy': str(o.get('dobavochnyy') or ''),
                                'pochta': pochty[0] if pochty else '',
                                'mashina': mash.get(inn, ''),
                                'mashina_ssylka': mash_ssylka.get(inn, ''),
                                'istochniki': [], 'kanaly': []}
            if not z['chelovek'] and chel:
                z['chelovek'], z['dolzhnost'] = chel, dolzh
            if not z['pochta'] and pochty:
                z['pochta'] = pochty[0]
            # ЛИЧНЫЙ ВИД ПОБЕЖДАЕТ ТОЛЬКО ВМЕСТЕ С ИМЕНЕМ. Иначе тот же номер, найденный
            # каналом без имени, понижал бы уже доказанный личный — и наоборот, безымянная
            # находка не должна повышать себя до личного.
            if vid.startswith('ЛИЧНЫЙ') and chel:
                z['vid_nomera'] = vid
            for u in us:
                if klyuch_ssylki(u) not in {klyuch_ssylki(x) for x in z['istochniki']}:
                    z['istochniki'].append(u)
            if kanal not in z['kanaly']:
                z['kanaly'].append(kanal)
            prochli['%s: строк принято' % kanal] += 1

stroki = sorted(svern.values(),
                key=lambda z: (0 if z['vid_nomera'].startswith('ЛИЧНЫЙ') else 1,
                               -len(z['kanaly']), -len(z['istochniki']),
                               -KLASS.get(z['mashina'], 0)))
# ВИД ПОЧТЫ — та же мысль, что и вид номера: разделять, а не отсеивать.
# Нашлось глазами на проверке ссылок: строка «Жучкова Елена Эдуардовна | info@myhistorypark
# .spb.ru», ссылка ведёт на страницу ВАКАНСИЙ музея, где стоит общая почта организации.
# Счётчик написал «ДОКАЗЫВАЕТ», потому что почта на странице есть, — но доказано
# существование почты У ОРГАНИЗАЦИИ, а не принадлежность её этому человеку. По живой базе
# таких строк 78 из 1 829 «человек + почта». Не выбрасываю: помечаю видом, как номера.
OBSHCHAYA_POCHTA = re.compile(
    r'^(info|mail|office|priemnaya|priem|secretar|kanc|general|post|zakupki|tender|adm|'
    r'admin|reception|hr|kadry|job|vacancy|sales|market|support|help|contact)@', re.I)


def vid_pochty(adres, chelovek):
    a = str(adres or '').strip()
    if not a:
        return ''
    if OBSHCHAYA_POCHTA.match(a):
        return ('ОБЩАЯ ПОЧТА ОРГАНИЗАЦИИ, не личная' if chelovek
                else 'общая почта организации')
    return 'почта, принадлежность человеку не проверена' if chelovek else 'почта организации'


KOL = ('inn', 'predpriyatie', 'chelovek', 'dolzhnost', 'nomer', 'dobavochnyy', 'vid_nomera',
       'pochta', 'vid_pochty', 'mashina', 'kanalov', 'istochnikov', 'kanaly', 'istochniki',
       'mashina_ssylka')
with io.open(VYHOD, 'w', encoding='utf-8-sig') as f:
    f.write(';'.join(KOL) + '\n')
    for z in stroki:
        z['kanalov'] = len(z['kanaly'])
        z['istochnikov'] = len(z['istochniki'])
        z['vid_pochty'] = vid_pochty(z.get('pochta'), z.get('chelovek'))
        r = dict(z)
        r['kanaly'] = ' | '.join(z['kanaly'])
        r['istochniki'] = ' | '.join(z['istochniki'])
        f.write(';'.join(str(r.get(k, '')).replace(';', ',').replace('\n', ' ')
                         for k in KOL) + '\n')

s_kontaktom = {z['inn'] for z in stroki}
bez = [i for i in mash if i not in s_kontaktom]
with io.open(OCHERED, 'w', encoding='utf-8-sig') as f:
    f.write('inn;predpriyatie;mashina;istochnikov_mashiny;istochniki_mashiny\n')
    for i in sorted(bez, key=lambda x: -KLASS.get(mash.get(x, ''), 0)):
        f.write('%s;%s;%s;%d;%s\n' % (i, imena.get(i, '').replace(';', ','), mash.get(i, ''),
                                      len(mash_ist[i]), ' | '.join(mash_ist[i][:6])))

vyl = []
for p in (VYHOD, OCHERED):
    try:
        rq = urllib.request.Request('%s/%s' % (drop, os.path.basename(p)),
                                    data=io.open(p, 'rb').read(), method='PUT', headers=tok)
        vyl.append('%s: %s' % (os.path.basename(p),
                               op.open(rq, timeout=300).read().decode('utf-8', 'replace')[:60]))
    except Exception as e:  # noqa: BLE001
        vyl.append('%s НЕ ВЫЛОЖЕН: %s' % (os.path.basename(p), str(e)[:60]))

lich = [z for z in stroki if z['vid_nomera'].startswith('ЛИЧНЫЙ')]
dva_kanala = [z for z in stroki if len(z['kanaly']) > 1]
vidy = collections.Counter(z['vid_nomera'][:44] for z in stroki)
print('\n\n########## ЛИЧНЫЕ МОБИЛЬНЫЕ, ПОДТВЕРЖДЁННЫЕ БОЛЕЕ ЧЕМ ОДНИМ КАНАЛОМ')
for z in [x for x in lich if len(x['kanaly']) > 1][:10]:
    print('  %-12s %-24s %-14s каналов %d ссылок %d' % (z['inn'], z['chelovek'][:24],
                                                        z['nomer'], len(z['kanaly']),
                                                        len(z['istochniki'])))
print('\n########## ЧИСЛА')
print('  предприятий с доказанной машиной   %5d' % len(mash))
print('     из них взято из парка 1-й сессии %4d  (машина доказана ИХ ссылкой)'
      % sosedey_vzyato)
print('  строк в единой базе                %5d  (предприятий %d)'
      % (len(stroki), len(s_kontaktom)))
print('  --- по виду номера')
for k, v in vidy.most_common():
    print('     %-50s %5d' % (k, v))
print('  ЛИЧНЫХ МОБИЛЬНЫХ                   %5d  на %d предприятиях'
      % (len(lich), len({z['inn'] for z in lich})))
print('  строк, подтверждённых ДВУМЯ каналами %3d' % len(dva_kanala))
print('  строк с двумя и более ссылками     %5d'
      % sum(1 for z in stroki if len(z['istochniki']) > 1))
print('  предприятий БЕЗ единого контакта   %5d  (очередь работы, не отход)' % len(bez))
print('  --- что прочитано')
for k, v in prochli.most_common(20):
    print('     %-58s %5d' % (k[:58], v))
for v in vyl:
    print('  %s' % v)
print('ИТОГ ' + json.dumps({'строк': len(stroki), 'предприятий': len(s_kontaktom),
                            'личных': len(lich), 'двумя каналами': len(dva_kanala),
                            'без контакта': len(bez)}, ensure_ascii=False))

# -*- coding: utf-8 -*-
"""Пройти по СЛУЧАЙНЫМ карточкам и провалиться из каждого номера в его первоисточник.

ЧТО ЭТО И ПОЧЕМУ ТАК. Карточку панели рисует запрос к `centrifugal.db` — те же люди,
контакты и ссылки. Живой HTTP-вход в панель на 8012 закрыт Basic-логином (проверено:
карточка это /obzvon/centroN/card, отдаёт 401 без верных кред; admin/prodazhnik из .env
к нему не подходят, рабочие креды владельца я в репозиторий и на дроп не пишу). Поэтому
иду по тем же данным напрямую — это ровно то же содержимое карточки и та же цепочка
«карточка → первоисточник», только без обхода чужого пароля.

ЧТО СЧИТАЕТСЯ ПРОВЕРЕННОЙ ЦЕПОЧКОЙ. Не «ссылка есть» и не «страница открылась», а: у
контакта есть ссылка на источник; источник открыт; и ЭТОТ ЖЕ номер найден в его тексте.
Номер сверяется ЦИФРАМИ: «+7 (343) 229-00-75» и «8 343 229 00 75» — один номер.

  * ПОДТВЕРЖДЕНО ИСТОЧНИКОМ — номер найден в тексте страницы-источника;
  * В ИСТОЧНИКЕ НЕТ — страница открылась, номера в ней нет: цепочка рвётся здесь;
  * ИСТОЧНИК НЕ ОТКРЫЛСЯ / ССЫЛКИ НЕТ — проверить нечем, это не то же, что «нет».

СЛУЧАЙНОСТЬ НАСТОЯЩАЯ: предприятия берутся по случайным rowid из всей таблицы, а не
первые — первые всегда самые заполненные, и по ним всё выглядит лучше, чем есть.

Запуск: python3 p25_hodok_po_kartochkam.py [--kart N] [--zerno N]
"""
import collections
import io
import json
import os
import random
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.request

BAZA = r'C:\seostat\data\centrifugal.db'
VYHOD = r'C:\sender\_ops\P25-HODOK-PO-KARTOCHKAM-3S.json'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/120.0 Safari/537.36')
TEG = re.compile(r'<[^>]+>')
SYROY_TEL = re.compile(r'(?:\+7|\b8)?[\s\-(]{0,3}\d[\d\s\-()]{7,18}\d')


def dovod(s):
    return sys.argv[sys.argv.index(s) + 1] if s in sys.argv else ''


KART = int(dovod('--kart') or 15)
ZERNO = int(dovod('--zerno') or 20260805)


def cifry(s):
    c = re.sub(r'\D', '', str(s or ''))
    if len(c) == 11 and c[0] in '78':
        return '7' + c[1:]
    if len(c) == 10 and c[0] == '9':
        return '7' + c
    return ''


def tekst(h):
    t = re.sub(r'(?is)<(?:script|style)[^>]*>.*?</(?:script|style)>', ' ', h or '')
    t = TEG.sub(' ', t)
    for a, b in (('&nbsp;', ' '), ('&amp;', '&'), ('&laquo;', '«'), ('&raquo;', '»'),
                 ('&mdash;', '—'), ('&ndash;', '–'), ('&quot;', '"'), ('&#39;', "'")):
        t = t.replace(a, b)
    return t


def vzyat(url, popytok=2):
    for p in range(popytok):
        try:
            rq = urllib.request.Request(url, headers={'User-Agent': UA,
                                                      'Accept-Language': 'ru,en;q=0.8'})
            with urllib.request.urlopen(rq, timeout=45) as r:
                syroy = r.read()
            for kod in ('utf-8', 'cp1251'):
                try:
                    return r.status, syroy.decode(kod)
                except Exception:  # noqa: BLE001
                    continue
            return r.status, syroy.decode('utf-8', 'replace')
        except urllib.error.HTTPError as e:
            return e.code, ''
        except Exception as e:  # noqa: BLE001
            if p == popytok - 1:
                return 0, '__ОШИБКА__ %s' % type(e).__name__
            time.sleep(1.2)


def normalizovat(u):
    u = str(u or '').strip()
    if u and not u.startswith('http'):
        u = 'http://' + u.lstrip('/')
    return u


# Род источника. Первый проход показал: 65 из 88 «источников» это checko/rts-tender,
# отдающие 404/503 боту. Но checko — агрегатор реквизитов, а не первоисточник: номер
# оттуда принадлежит юрлицу, а не человеку, и «не открылся» вводит в заблуждение —
# проверять эту ссылку как первоисточник бессмысленно и с открытой страницей.
AGREGATORY = re.compile(
    r'checko\.ru|rusprofile|list-org|zachestnyi|sbis\.ru|audit-it|'
    r'sudact|kad\.arbitr|2gis|yell\.ru|za-chestnyibiznes|of-combanks|bo\.nalog', re.I)
ZAKUPKI = re.compile(
    r'zakupki\.gov|zakupki\.mos|tender\.pro|etpgpb|roseltorg|rts-tender|tektorg|'
    r'sberbank-ast|b2b-center|fabrikant|torgi\.gov', re.I)


def rod_istochnika(u, sayt_predpr):
    d = str(u or '').lower()
    if AGREGATORY.search(d):
        return 'агрегатор реквизитов (не первоисточник)'
    if ZAKUPKI.search(d):
        return 'карточка закупки'
    host = re.sub(r'^https?://(www\.)?', '', d).split('/')[0]
    if sayt_predpr and host and (host in sayt_predpr or sayt_predpr in host):
        return 'сайт самого предприятия'
    return 'прочий сайт'


def main():
    random.seed(ZERNO)
    b = sqlite3.connect('file:%s?mode=ro' % BAZA.replace('\\', '/'), uri=True)
    tabl = {r[0] for r in b.execute("select name from sqlite_master where type='table'")}
    imena = {i: n for i, n in b.execute(
        'select inn, coalesce(predpriyatie,"") from company')}
    sayty = {i: re.sub(r'^https?://(www\.)?', '', (s or '').lower().strip()).split('/')[0]
             for i, s in b.execute('select inn, coalesce(sayt,"") from company')}
    p_pole = [r[1] for r in b.execute('pragma table_info(person)')]
    c_pole = [r[1] for r in b.execute('pragma table_info(contact)')] if 'contact' in tabl \
        else []

    # Случайные предприятия из всей таблицы company.
    vse_inn = [r[0] for r in b.execute(
        'select inn from company where coalesce(predpriyatie,"") <> ""')]
    random.shuffle(vse_inn)

    sch = collections.Counter()
    kartochki, cepochki = [], []
    istochniki = {}
    vzyato = 0
    for inn in vse_inn:
        if vzyato >= KART:
            break
        nazv = imena.get(inn, inn)
        lyudi = []
        for r in b.execute(
                'select %s from person where inn = ?'
                % ','.join(p_pole), (inn,)):
            z = dict(zip(p_pole, r))
            lyudi.append(z)
        # Контакты с номером и ссылкой.
        kont = []
        if c_pole:
            polya = ','.join(c_pole)
            try:
                for r in b.execute('select %s from contact where inn = ?' % polya, (inn,)):
                    kont.append(dict(zip(c_pole, r)))
            except Exception:  # noqa: BLE001
                pass
        if not lyudi and not kont:
            continue
        vzyato += 1
        sch['карточек пройдено'] += 1
        sch['людей'] += len(lyudi)
        sch['людей со значком должности'] += sum(
            1 for z in lyudi if str(z.get('position') or '').strip())
        sch['людей с пометкой привязки'] += sum(
            1 for z in lyudi if str(z.get('privyazka_somnitelna') or '').strip())

        # Что видно на карточке (глазами).
        vid_lyudi = [{'chelovek': str(z.get('person') or ''),
                      'dolzhnost': str(z.get('position') or ''),
                      'telefon': str(z.get('phone') or ''),
                      'privyazka': str(z.get('privyazka_somnitelna') or ''),
                      'ssylka': str(z.get('source_url') or '')} for z in lyudi]
        kartochki.append({'inn': inn, 'predpriyatie': nazv,
                          'lyudey': len(lyudi), 'kontaktov': len(kont),
                          'lyudi': vid_lyudi[:10]})

        # Проваливание: каждый номер (из людей и контактов) со ссылкой.
        pary = []
        for z in lyudi:
            if cifry(z.get('phone')):
                pary.append((cifry(z.get('phone')), normalizovat(z.get('source_url')),
                             str(z.get('person') or ''), 'человек'))
        for z in kont:
            nomer = cifry(z.get('value') or z.get('phone') or z.get('nomer'))
            if nomer:
                pary.append((nomer, normalizovat(z.get('source_url') or z.get('url')),
                             str(z.get('person') or z.get('vid') or ''), 'контакт'))
        # Схлопываем по номеру, предпочитая запись со ссылкой.
        vidno = {}
        for nomer, ssylka, kto, rod in pary:
            if nomer not in vidno or (ssylka and not vidno[nomer][1]):
                vidno[nomer] = (nomer, ssylka, kto, rod)

        for nomer, ssylka, kto, rod in vidno.values():
            vid = rod_istochnika(ssylka, sayty.get(inn, ''))
            zapis = {'inn': inn, 'predpriyatie': nazv, 'nomer': nomer, 'kto': kto,
                     'rod': rod, 'ssylka': ssylka, 'vid_istochnika': vid}
            if not ssylka:
                zapis['itog'] = 'ССЫЛКИ НЕТ — провалиться некуда'
                sch['ССЫЛКИ НЕТ'] += 1
            elif vid.startswith('агрегатор'):
                # Агрегатор не первоисточник: проверять цепочку по нему нечестно.
                zapis['itog'] = 'ИСТОЧНИК-АГРЕГАТОР — не первоисточник, номер юрлица'
                sch['источник — агрегатор (не первоисточник)'] += 1
            else:
                if ssylka not in istochniki:
                    istochniki[ssylka] = vzyat(ssylka)
                kodi, telo = istochniki[ssylka]
                if kodi != 200 or telo.startswith('__ОШИБКА__') or not telo:
                    zapis['itog'] = 'ИСТОЧНИК НЕ ОТКРЫЛСЯ (%s)' % kodi
                    sch['ИСТОЧНИК НЕ ОТКРЫЛСЯ (%s)' % ('403/антибот' if kodi == 403
                                                       else kodi)] += 1
                else:
                    t_ist = tekst(telo)
                    vse = {cifry(x) for x in SYROY_TEL.findall(t_ist)}
                    if nomer in vse:
                        zapis['itog'] = 'ПОДТВЕРЖДЕНО ИСТОЧНИКОМ (%s)' % vid
                        sch['ПОДТВЕРЖДЕНО ИСТОЧНИКОМ'] += 1
                        sch['  из них: %s' % vid] += 1
                    else:
                        zapis['itog'] = 'В ИСТОЧНИКЕ НЕТ'
                        zapis['chto_v_istochnike'] = sorted(x for x in vse if x)[:6]
                        sch['В ИСТОЧНИКЕ НЕТ'] += 1
            cepochki.append(zapis)

    b.close()

    # Глазами.
    print('=== карточки (случайные предприятия)')
    for k in kartochki[:10]:
        print('\n--- %s  ИНН %s  людей %d, контактов %d'
              % (k['predpriyatie'][:48], k['inn'], k['lyudey'], k['kontaktov']))
        for l in k['lyudi'][:4]:
            hvost = ''
            if l['privyazka']:
                hvost = '  ПРИВЯЗКА СПОРНА: ' + l['privyazka'][:46]
            print('    %-28s %-24s тел %-13s%s'
                  % (l['chelovek'][:28], (l['dolzhnost'] or 'без должности')[:24],
                     l['telefon'] or '—', hvost))
    print('\n=== цепочки: заявленный номер -> первоисточник')
    for c in cepochki[:26]:
        print('  %-24s %-11s %-40s %s'
              % (c['predpriyatie'][:24], c['nomer'], c['itog'][:40],
                 (c['ssylka'] or '—')[:46]))

    # Разрывы цепочки разглядываем отдельно: источник открылся, а номера в нём НЕТ.
    razryvy = [c for c in cepochki if c['itog'] == 'В ИСТОЧНИКЕ НЕТ']
    if razryvy:
        print('\n=== РАЗРЫВЫ: источник открылся, номера в нём нет (глазами)')
        for c in razryvy[:12]:
            print('  %s  номер %s' % (c['predpriyatie'][:40], c['nomer']))
            print('     ссылка: %s' % c['ssylka'][:100])
            print('     в источнике номера: %s'
                  % ', '.join(c.get('chto_v_istochnike') or ['(ни одного)']))

    io.open(VYHOD, 'w', encoding='utf-8').write(json.dumps(
        {'kartochki': kartochki, 'cepochki': cepochki, 'schet': dict(sch),
         'zerno': ZERNO}, ensure_ascii=False, indent=1))
    url, tokd = os.environ.get('DROP_URL', ''), os.environ.get('DROP_TOKEN', '')
    if url and tokd:
        rq = urllib.request.Request(url.rstrip('/') + '/' + os.path.basename(VYHOD),
                                    data=io.open(VYHOD, 'rb').read(), method='PUT')
        rq.add_header('X-Drop-Token', tokd)
        try:
            sch['выложено, ответ дропа %s'
                % urllib.request.urlopen(rq, timeout=180).status] += 1
        except Exception as e:  # noqa: BLE001
            sch['выкладка не прошла: %s' % str(e)[:40]] += 1

    for k, v in sch.most_common():
        print('REC %s\t%d' % (k, v))
    proverennyh = sum(sch[x] for x in ('ПОДТВЕРЖДЕНО ИСТОЧНИКОМ', 'В ИСТОЧНИКЕ НЕТ',
                                       'ИСТОЧНИК НЕ ОТКРЫЛСЯ'))
    print('ИТОГ ' + json.dumps({
        'карточек пройдено': sch['карточек пройдено'],
        'номеров с проваливанием': proverennyh,
        'подтверждено первоисточником': sch['ПОДТВЕРЖДЕНО ИСТОЧНИКОМ'],
        'разрыв цепочки (в источнике нет)': sch['В ИСТОЧНИКЕ НЕТ'],
        'зерно': ZERNO}, ensure_ascii=False))


if __name__ == '__main__':
    main()

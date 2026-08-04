# -*- coding: utf-8 -*-
"""Добить тех, кому до закрытия не хватает ОДНОГО — первоисточника. Точечный прогон.

ЗАЧЕМ ИМЕННО ЭТО, А НЕ НОВЫЕ ИМЕНА. Условие ТЗ требует трёх вещей сразу: технический круг,
личный мобильный, первоисточник. Разбор всех 49 найденных личных мобильных:

    у человека технического круга      3
    из них с подтверждённым источником 0

То есть до первого закрытого предприятия за всю смену не хватает не людей и не номеров, а
ОДНОГО подтверждения на уже добытых. Искать новых значит начинать с нуля там, где две трети
пути пройдено.

ПОЧЕМУ ДОБЫТЫЕ ДОМЕНЫ САМИ ПО СЕБЕ НЕ ПОМОГЛИ. Их стало 150 из 491, но пересбор выкладки не
добавил ни одного подтверждённого. Причина проста и её стоит записать: домен подтверждает
страницу, ЛЕЖАЩУЮ НА НЁМ. Люди же найдены на площадках и агрегаторах, и знание домена задним
числом их не переносит. Домены работают ВПЕРЁД — под запрос `site:<домен> "ФИО"`, — а не
назад. Моя вчерашняя формулировка «469 человек ждут домена» была неточной: они ждут СТРАНИЦЫ
на этом домене, а её надо спросить.

ЧТО ДЕЛАЕТ ЭТОТ ПРОГОН. Для каждого человека, у которого есть личный мобильный или
техническая должность, а первоисточника нет, спрашивает `"ФИО" site:<домен предприятия>`.
Страница на собственном сайте предприятия — сильнейшее подтверждение по ТЗ, и один такой
ответ закрывает человека целиком.

Запуск на сервере: --lim N --potokov N
"""
import collections
import csv
import importlib.util
import json
import os
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, r'C:\sender\_ops')
import _3s_chuzhaya_stranica as CH  # noqa: E402

POTOK_OBR = r'C:\sender\_ops\p25-obratnyy.jsonl'
POTOK_IMENA = r'C:\sender\_ops\p25-imena.jsonl'
POTOK = r'C:\sender\_ops\p25-dobit.jsonl'
SAYTY_FAJLY = (r'C:\sender\_ops\3s_p25_sayty_2s.csv',
               r'C:\sender\_ops\3s_p25_sayty_2s_002.csv',
               r'C:\sender\_ops\3s_p25_sayty_iz_poiska.csv',
               r'C:\sender\_ops\3s_p25_sayty_iz_potokov.csv',
               r'C:\sender\_ops\3s_p25_sayty.csv')
KANDIDATY = (r'C:\sender\_ops\3s_lpr_obratnyy.py', r'C:\sender\_ops\_3s_lpr_obratnyy.py')

KRUG1 = re.compile(r'главн\w*\s+(?:инженер|механик|энергетик)|техническ\w+\s+директор', re.I)
KRUG2 = re.compile(r'начальник\w*\s+(?:производств|цеха)|главн\w+\s+технолог|АСУ|КИПиА', re.I)
TEL = re.compile(r'(?:\+7|\b8)[\s\-(]*\d{3}[\s\-)]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}\b')


def lichnyy(n):
    c = re.sub(r'\D', '', str(n or ''))
    if len(c) == 11 and c[0] in '78':
        c = '7' + c[1:]
    return len(c) == 11 and c.startswith('79')


def _serp():
    for put in KANDIDATY:
        if os.path.exists(put):
            spec = importlib.util.spec_from_file_location('lpr_obr', put)
            m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m)
            return m.serp
    raise SystemExit('модуля поиска нет')


def sayty():
    d = {}
    for p in SAYTY_FAJLY:
        if not os.path.exists(p):
            continue
        for r in csv.DictReader(open(p, encoding='utf-8-sig'), delimiter=';'):
            v = (r.get('ves') or '').strip()
            if v.isdigit() and int(v) < 2:
                continue
            if r.get('inn') and r.get('sayt'):
                d.setdefault(r['inn'], r['sayt'])
    return d


def celi(st):
    """Кого добивать: есть личный мобильный ИЛИ техническая должность, источника нет."""
    out, sch = {}, collections.Counter()
    for put, obratnyy in ((POTOK_OBR, True), (POTOK_IMENA, False)):
        if not os.path.exists(put):
            continue
        for ln in open(put, encoding='utf-8'):
            try:
                z = json.loads(ln)
            except Exception:  # noqa: BLE001
                continue
            if z.get('err'):
                continue
            inn = z.get('inn')
            if inn not in st:
                sch['домена предприятия нет — спрашивать не с чем'] += 1
                continue
            if obratnyy:
                dolzh = z.get('dolzhnost') or ''
                fio = z.get('fio') or ''
                lich = any(k.get('tip') == 'телефон' and lichnyy(k.get('znachenie'))
                           and (k.get('uverennost') != 'спорная')
                           for k in z.get('kontakty') or [])
                istochniki = [k.get('ssylka', '') for k in z.get('kontakty') or []]
            else:
                lyudi = z.get('lyudi') or []
                for l in lyudi:
                    if l.get('krug') == 'ИСТОЧНИК ЗАПРЕЩЁН':
                        continue
                    d2, f2 = l.get('dolzhnost') or '', l.get('fio') or ''
                    if not (KRUG1.search(d2) or KRUG2.search(d2)):
                        continue
                    if any(CH.stranica_podtverzhdaet(l.get('ssylka', ''), st.get(inn, ''),
                                                     z.get('predpriyatie', ''), '',
                                                     strogo=True)[0] for _ in (1,)):
                        sch['уже подтверждён — не трогаем'] += 1
                        continue
                    k = (inn, f2)
                    if k not in out and len(f2.split()) >= 2:
                        out[k] = {'inn': inn, 'fio': f2, 'dolzhnost': d2,
                                  'predpriyatie': z.get('predpriyatie', ''),
                                  'sayt': st[inn], 'pochemu_cel': 'технический круг, '
                                                                  'первоисточника нет'}
                        sch['ЦЕЛЬ: технический круг без источника'] += 1
                continue
            teh = bool(KRUG1.search(dolzh) or KRUG2.search(dolzh))
            podtv = any(CH.stranica_podtverzhdaet(u, st.get(inn, ''), z.get('predpriyatie', ''),
                                                  '', strogo=True)[0] for u in istochniki)
            # СЕМЬ ЧЕЛОВЕК, У КОТОРЫХ НЕ ХВАТАЕТ ДОЛЖНОСТИ, А НЕ НОМЕРА. Это выяснилось,
            # когда прогон за номерами вернул честный ноль: предприятия не публикуют личные
            # мобильные главных инженеров на своих сайтах, и не будут. Зато обратный ход уже
            # добыл 13 личных мобильных С ПОДТВЕРЖДЁННЫМ первоисточником — карточки закупок,
            # где контактное лицо заказчика названо с номером. У шести из них должность
            # известна и не техническая, а у СЕМИ её просто нет в списке 2-й сессии: площадки
            # должностей не отдают вовсе.
            #
            # То есть до закрытия им не хватает ОДНОЙ вещи — должности, и она стоит один
            # запрос. Прежний отбор их пропускал: «уже подтверждён — не трогаем» смотрел
            # только на источник и не спрашивал, знаем ли мы, КТО это.
            if podtv and lich and not dolzh:
                k = (inn, fio)
                if k not in out and len(fio.split()) >= 2 and inn in st:
                    out[k] = {'inn': inn, 'fio': fio, 'dolzhnost': '',
                              'predpriyatie': z.get('predpriyatie', ''), 'sayt': st[inn],
                              'pochemu_cel': 'личный мобильный и источник есть, НЕТ ДОЛЖНОСТИ'}
                    sch['ЦЕЛЬ: номер и источник есть, не хватает должности'] += 1
                continue
            if not (lich or teh):
                continue
            if podtv:
                sch['уже подтверждён — не трогаем'] += 1
                continue
            k = (inn, fio)
            if k in out or len(fio.split()) < 2:
                continue
            out[k] = {'inn': inn, 'fio': fio, 'dolzhnost': dolzh,
                      'predpriyatie': z.get('predpriyatie', ''), 'sayt': st[inn],
                      'pochemu_cel': ('личный мобильный без источника' if lich
                                      else 'технический круг, первоисточника нет')}
            sch['ЦЕЛЬ: ' + out[k]['pochemu_cel']] += 1
    return out, sch


def main():
    serp = _serp()
    lim = int(sys.argv[sys.argv.index('--lim') + 1]) if '--lim' in sys.argv else 10 ** 9
    pot = int(sys.argv[sys.argv.index('--potokov') + 1]) if '--potokov' in sys.argv else 5
    st = sayty()
    cel, sch = celi(st)
    gotovo = set()
    if os.path.exists(POTOK):
        for ln in open(POTOK, encoding='utf-8'):
            try:
                z = json.loads(ln)
            except Exception:  # noqa: BLE001
                continue
            if not z.get('err'):
                gotovo.add((z['inn'], z['fio']))
    zad = [v for k, v in cel.items() if k not in gotovo][:lim]
    print('сайтов известно %d, целей %d, уже спрошено %d, к обходу %d'
          % (len(st), len(cel), len(gotovo), len(zad)), file=sys.stderr, flush=True)

    f = open(POTOK, 'a', encoding='utf-8')
    lock = threading.Lock()
    itog = collections.Counter()

    def odin(c):
        q = '"%s" site:%s' % (c['fio'], c['sayt'])
        docs, err = serp(q)
        nashli = []
        for d in docs:
            url = (d.get('url') or '').strip()
            tekst = ' '.join(v for k, v in d.items() if k != 'url' and isinstance(v, str))
            est, poch = CH.stranica_podtverzhdaet(url, c['sayt'], c['predpriyatie'], '',
                                                  strogo=True)
            if not est:
                continue
            fam = c['fio'].split()[0]
            if fam.lower() not in tekst.lower():
                continue
            m = TEL.search(tekst)
            nashli.append({'ssylka': url, 'pochemu': poch,
                           'telefon': m.group(0) if m else '',
                           'citata': tekst[:600]})
        return {**c, 'zapros': q, 'err': err, 'stranic': len(docs), 'naydeno': nashli}

    with ThreadPoolExecutor(max_workers=pot) as ex:
        for r in ex.map(odin, zad):
            with lock:
                f.write(json.dumps(r, ensure_ascii=False) + '\n')
                if r['err']:
                    itog['сбой'] += 1
                elif r['naydeno']:
                    itog['ПОДТВЕРЖДЁН САЙТОМ ПРЕДПРИЯТИЯ'] += 1
                    if any(x['telefon'] for x in r['naydeno']):
                        itog['  и номер на той же странице'] += 1
                else:
                    itog['на сайте предприятия не найден'] += 1
    f.close()
    for k, v in sch.most_common():
        print('REC отбор: %s\t%d' % (k, v))
    for k, v in itog.most_common():
        print('REC прогон: %s\t%d' % (k, v))
    print('ИТОГ ' + json.dumps({'спрошено': len(zad)}, ensure_ascii=False))


if __name__ == '__main__':
    main()

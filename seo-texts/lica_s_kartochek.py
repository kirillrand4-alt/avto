# -*- coding: utf-8 -*-
"""Люди с карточек Росэлторга, Портала Москвы, ТЭК-Торга и РТС — одним модулем.

Продолжение `gpb_lica_s_kartochek.py`, который делает то же для ЭТП ГПБ. Разборщики карточек
не пишутся заново: берутся из `zamer_kontaktov.py`, где они уже сняты агентами с живых
карточек и проверены независимой попыткой опровержения. Здесь только отбор карточек, обход
и запись — то есть ровно то, чего у замера нет: замер отвечает «что там лежит», этот модуль
«достань всё».

ПОЧЕМУ ПОРЯДОК ПЛОЩАДОК ИМЕННО ТАКОЙ. По замеру на карточках (выборка равномерно по разным
предприятиям, не подряд):
    ЭТП ГПБ    ФИО 90 из 99, телефон 91, ЛИЧНЫЙ МОБИЛЬНЫЙ 15 (15 %), общих номеров 0
    Росэлторг  ФИО есть, но телефон ОДИН на несколько человек: +7 495 730 04 50 стоял
               у Рославцева, Яковлева и Назаровой одновременно
    Портал     contactPerson есть, contactPhone приходит ПУСТЫМ
    ТЭК-Торг   contactPerson и contactPhone привязаны к человеку
Поэтому ЭТП ГПБ идёт отдельным модулем и первым, здесь — остальные, и **ожидание от них
честно ниже**: имена и почты, телефоны реже и чаще общие. Имя тоже стоит работы: это вход
для обратного поиска и для действия «спросить по фамилии».

ДОЛЖНОСТИ НЕТ НИ НА ОДНОЙ ПЛОЩАДКЕ. Перебраны все атрибуты карточек: у ЭТП ГПБ 92 поля,
полей вида position/post/dolzhnost нет вовсе. Роль придётся ставить разбором должности из
других источников, а не ждать её от площадки.

ОТБОР тот же, что у ЭТП ГПБ: предприятия по пользе (сначала те, у кого нет технического
человека), карточки внутри предприятия — машинные предметы вперёд, остановка после N карточек
подряд без новой фамилии.

Использование:
    python3 lica_s_kartochek.py --ploshchadka roseltorg --parallel 4
    python3 lica_s_kartochek.py --vse --na-predpriyatie 25
"""
import csv
import os
import re
import sys
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import zamer_kontaktov as z

csv.field_size_limit(10 ** 7)
BAZA = os.path.dirname(os.path.abspath(__file__))
L = os.path.join(BAZA, 'engineers-lens')
C = os.path.join(L, 'centro')
OCHERED = os.path.join(L, 'OCHERED-centrobezhnye.csv')
COLS = ['inn', 'predpriyatie', 'chelovek', 'telefon', 'mobilnyy', 'pochta', 'chey_kontakt',
        'nomer', 'predmet', 'ploshchadka', 'ssylka']
STOP = 10

MASHINNYE = ('компрессор', 'воздуходув', 'турбо', 'нагнетател', 'центробеж', 'ремонт',
             'экспертиз', 'диагностик', 'подшипник', 'ротор', 'запчаст', 'кипиа',
             'электродвигател', 'насос', 'обслуживани')

# имя площадки -> (человекочитаемое, файл карточек, разборщик из zamer_kontaktov, выход)
PLOSHCHADKI = {
    'roseltorg': ('Росэлторг', 'roseltorg-po-kompaniyam.csv', z.roseltorg,
                  'roseltorg-lica-s-kartochek.csv'),
    'portal': ('Портал Москвы', 'portal-po-kompaniyam-inn.csv', z.portal,
               'portal-lica-s-kartochek.csv'),
    'tektorg': ('ТЭК-Торг', 'tektorg-po-kompaniyam.csv', z.tektorg,
                'tektorg-lica-s-kartochek.csv'),
    'rts': ('РТС-тендер', 'rts-po-kompaniyam.csv', z.rts, 'rts-lica-s-kartochek.csv'),
}


def chitat(put):
    return list(csv.DictReader(open(put, encoding='utf-8-sig'), delimiter=';')) \
        if os.path.exists(put) else []


def familiya(imya):
    ch = re.sub(r'[^А-ЯЁа-яё ]', ' ', imya or '').split()
    return ch[0].lower() if ch else ''


def ves(r):
    t = (r.get('predmet') or '').lower()
    return 0 if any(s in t for s in MASHINNYE) else 1


def main():
    na_predpriyatie = z.dovod('--na-predpriyatie', 25)
    parallel = z.dovod('--parallel', 4)
    # Предел раннера: сверх 30 воркеров задачи не работают, а ждут.
    import predel_rannera
    predel_rannera.preduprezhdenie(parallel)
    predpriyatiy = z.dovod('--predpriyatiy', 10 ** 9)
    imena = (list(PLOSHCHADKI) if '--vse' in sys.argv
             else [z.dovod('--ploshchadka', 'roseltorg')])

    och = {r['inn']: r for r in chitat(OCHERED)}

    for imya in imena:
        nazvanie, fajl, razbor, vyhodnoy = PLOSHCHADKI[imya]
        kartochki = chitat(os.path.join(C, fajl))
        if len(kartochki) < 50:
            print(f'[{nazvanie}] в файле {len(kartochki)} строк — пропускаю', file=sys.stderr)
            continue
        po_inn = defaultdict(list)
        for r in kartochki:
            if r.get('ssylka') and r.get('inn'):
                po_inn[r['inn']].append(r)

        VYHOD = os.path.join(C, vyhodnoy)
        KARTA = os.path.join(C, vyhodnoy.replace('.csv', '-zhurnal.csv'))
        # ЗАПИСЬ СО СБОЕМ — НЕ «ПРОЙДЕНО». Дефект найден 3-й сессией у себя 04.08 и проверен
        # здесь: её резюм считал записи с ошибкой пройденными, и 150 человек, по которым прибор
        # ответил «нет свободных каналов», навсегда остались бы в отчёте как «прошли, контактов
        # нет». Ложный ноль, закреплённый резюмом. У меня та же дыра: журнал писался и тогда,
        # когда все карточки предприятия не снялись. Теперь предприятие считается пройденным,
        # только если хоть одна карточка ДЕЙСТВИТЕЛЬНО разобрана.
        proydeno = {r['inn'] for r in chitat(KARTA)
                    if str(r.get('pochemu') or '').startswith('обойдено')
                    or int(str(r.get('lyudej') or 0) or 0) > 0}
        so_sboem = {r['inn'] for r in chitat(KARTA)} - proydeno
        if so_sboem:
            print(f'  в журнале {len(so_sboem)} предприятий со сбоем — будут переспрошены',
                  file=sys.stderr)

        def polza(inn):
            o = och.get(inn) or {}
            return (0 if (o.get('lyudej_tehnicheskih') or '0') in ('', '0') else 1,
                    0 if (o.get('lyudej_s_telefonom') or '0') in ('', '0') else 1,
                    -len(po_inn[inn]))

        celi = [i for i in sorted(po_inn, key=polza) if i not in proydeno][:predpriyatiy]
        print(f'[{nazvanie}] карточек {len(kartochki)}, предприятий {len(po_inn)}, '
              f'к обходу {len(celi)} (пройдено {len(proydeno)})', file=sys.stderr)
        if not celi:
            continue

        novyy_v = not os.path.exists(VYHOD) or os.path.getsize(VYHOD) == 0
        novyy_k = not os.path.exists(KARTA) or os.path.getsize(KARTA) == 0
        fv = open(VYHOD, 'a', encoding='utf-8-sig', newline='')
        wv = csv.DictWriter(fv, fieldnames=COLS, delimiter=';', extrasaction='ignore')
        if novyy_v:
            wv.writeheader()
        fk = open(KARTA, 'a', encoding='utf-8-sig', newline='')
        wk = csv.DictWriter(fk, fieldnames=['inn', 'predpriyatie', 'kartochek', 'lyudej',
                                            's_mobilnym', 'sboev', 'pochemu'],
                            delimiter=';', extrasaction='ignore')
        if novyy_k:
            wk.writeheader()

        sch = {'предприятий': 0, 'карточек': 0, 'людей': 0, 'с телефоном': 0,
               'с мобильным': 0, 'сбоев': 0}
        lock = threading.Lock()

        def odno(inn):
            spisok = sorted(po_inn[inn], key=ves)[:na_predpriyatie]
            vidennye, lyudi, bez_novyh, vzyato, sboev = set(), [], 0, 0, 0
            for r in spisok:
                if bez_novyh >= STOP:
                    break
                vzyato += 1
                try:
                    najdeno, err = razbor(r['ssylka'])
                except Exception as e:
                    najdeno, err = [], f'исключение: {str(e)[:80]}'
                if err:
                    sboev += 1
                    continue
                novoe = False
                for x in najdeno:
                    fio = (x.get('fio') or '').strip()
                    if not fio:
                        continue
                    f = familiya(fio)
                    if not f or f in vidennye:
                        continue
                    vidennye.add(f)
                    novoe = True
                    lyudi.append({'chelovek': fio, 'telefon': (x.get('tel') or '').strip(),
                                  'pochta': (x.get('poc') or '').strip(),
                                  'chey_kontakt': x.get('chey') or '',
                                  'nomer': r.get('nomer') or '',
                                  'predmet': (r.get('predmet') or '')[:200],
                                  'ssylka': r['ssylka']})
                bez_novyh = 0 if novoe else bez_novyh + 1
            return inn, lyudi, vzyato, sboev

        with ThreadPoolExecutor(max_workers=parallel) as pool:
            for nomer, (inn, lyudi, vzyato, sboev) in enumerate(pool.map(odno, celi), 1):
                with lock:
                    sch['предприятий'] += 1
                    sch['карточек'] += vzyato
                    sch['сбоев'] += sboev
                    imya_p = (och.get(inn) or {}).get('predpriyatie') or ''
                    s_mob = 0
                    for x in lyudi:
                        mob = z.mobilnyy(x['telefon'])
                        if mob:
                            s_mob += 1
                        if x['telefon']:
                            sch['с телефоном'] += 1
                        sch['людей'] += 1
                        wv.writerow(dict(x, inn=inn, predpriyatie=imya_p,
                                         ploshchadka=nazvanie,
                                         mobilnyy='да' if mob else ''))
                    sch['с мобильным'] += s_mob
                    wk.writerow({'inn': inn, 'predpriyatie': imya_p, 'kartochek': vzyato,
                                 'lyudej': len(lyudi), 's_mobilnym': s_mob, 'sboev': sboev,
                                 'pochemu': (f'{sboev} карточек не снялось — перезапросить'
                                             if sboev else 'обойдено')})
                    fv.flush()
                    fk.flush()
                    if nomer % 5 == 0 or lyudi:
                        print(f'  [{imya}] {nomer}/{len(celi)}: {sch}',
                              file=sys.stderr, flush=True)
        fv.close()
        fk.close()
        print(f'[{nazvanie}] готово: {sch}\n→ {VYHOD}', file=sys.stderr)


if __name__ == '__main__':
    main()

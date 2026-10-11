# -*- coding: utf-8 -*-
r"""Доизвлечение номеров из кэша страниц обхода новым разборщиком (telefony_izvlech.извлечь_номера).

11.10, ревизия (№42): на кэше 1507 компаний новый разбор нашёл 582 номера, которых не видят шаблоны обхода (CO.ТЕЛ):
«(код) номер» без 8/+7, продолжения через запятую с кодом предыдущего, юникод-тире, белорусские 4-значные коды,
«/код/», группировка 3-3, добавочные «доб. 34-20». Ошибок разбора 0 из 200. Здесь — по всем компаниям набора, БЕЗ
скачивания: страницы текущего сайта из кэша (<ИНН>.json.gz), только номера, которых в записи обхода ещё нет.

Результат — новая строка в <набор>-kontakty.jsonl: копия последней записи компании + новые номера (без роли: роль даст
kc_dorazmetka, «чей номер» — kc_audit в шагах после агентов) и отметка «доизвлечено». Резюм: компании с отметкой
пропускаются. Запускать, когда файл обхода никто не пишет (обход, добор закупок, дозаразметка).

    KC_NABOR=<набор> python kc_doizvlech.py            (KC_DOIZV_PROBA=1 — только счёт и примеры, без записи)
"""
import io
import json
import os
import re
import shutil
import sys
import time

DIR = r'C:\sender\server'
sys.path.insert(0, DIR)
sys.path.insert(0, r'C:\sender')
os.chdir(DIR)
import kc_kontakty as KK  # noqa: E402
import meyer_nalichie as MN  # noqa: E402
import telefony_izvlech as TI  # noqa: E402
import kc_zakupki_dobor as KZ  # noqa: E402  (пора_стоп)

НАБОР = os.environ.get('KC_NABOR', 'pilot')
ВЫХОД = os.path.join(DIR, НАБОР + '-kontakty.jsonl')
ПРОБА = os.environ.get('KC_DOIZV_PROBA') == '1'
ПРЕДЕЛ = int(os.environ.get('KC_DOIZV_PREDEL', '30'))  # больше новых на компанию — подозрение на мусор (ID статей, хеши)


def цифры(н):
    ц = re.sub(r'\D', '', н or '')
    return ц[-9:] if ц.startswith('375') else ц[-10:]


def новые_номера(з):
    сайт_дом = MN.домен(з.get('сайт') or '')
    свои_стр = {u for u, ст in з.get('страницы') or [] if ст in ('ok', 'кэш')}
    кэш = KK.прочитать_кэш(з['inn']).get('pages') or []
    есть = {(цифры(н.get('номер')), н.get('доб') or '') for н in з.get('номера') or [] if н.get('номер')}
    есть_ц = {ц for ц, _ in есть}
    нов = {}
    for стр in кэш:
        u, h = стр.get('url') or '', стр.get('html') or ''
        if not h or (u not in свои_стр and MN.домен(u) != сайт_дом):
            continue
        т = KK.MP.в_текст(KK.без_длинного(h)) + KK.json_текст(h)
        for номер, доб, поз in TI.извлечь_номера(т):
            ц = цифры(номер)
            if (ц, доб) in есть or (not доб and ц in есть_ц):
                continue
            ключ = номер + ((' доб. ' + доб) if доб else '')
            if ключ in нов:
                if u not in нов[ключ]['страницы']:
                    нов[ключ]['страницы'].append(u)
                continue
            нов[ключ] = {'номер': номер, 'доб': доб, 'страницы': [u],
                         'контекст': re.sub(r'\s+', ' ', т[max(0, поз - 200):поз + len(номер) + 60]),
                         'фио': '', 'должность': '', 'доизвлечён': 'telefony_izvlech'}
    return list(нов.values())


def main():
    последняя = {}
    for s in io.open(ВЫХОД, encoding='utf-8', errors='replace'):
        try:
            з = json.loads(s)
        except ValueError:
            continue
        if з.get('inn'):
            последняя[з['inn']] = з
    задачи = [з for з in последняя.values() if з.get('итог') == 'ok' and з.get('сайт') and not з.get('доизвлечено')]
    if ПРОБА:
        задачи = задачи[:int(os.environ.get('KC_DOIZV_VYBORKA', '1500'))]
    print('компаний с открывшимся сайтом', len(задачи), 'проба' if ПРОБА else '', flush=True)
    t0 = time.time()
    сч = {'компаний_с_новыми': 0, 'новых_номеров': 0, 'сверх_предела': 0, 'компаний_без_номеров_было': 0}
    примеры = []
    t0_iso, проверено = time.strftime('%Y-%m-%dT%H:%M:%S'), time.time()
    for n, з in enumerate(задачи, 1):
        if not ПРОБА and time.time() - проверено > 60:
            проверено = time.time()
            if KZ.пора_стоп(t0_iso):
                print('оркестратор начал шаги после агентов — стоп (резюм по отметке «доизвлечено»)', flush=True)
                break
        try:
            нов = новые_номера(з)
        except Exception as e:  # noqa: BLE001
            print('сбой', з['inn'], repr(e)[:100], flush=True)
            continue
        if len(нов) > ПРЕДЕЛ:
            сч['сверх_предела'] += 1
            нов = []
        if нов:
            сч['компаний_с_новыми'] += 1
            сч['новых_номеров'] += len(нов)
            if not any(н.get('номер') for н in з.get('номера') or []):
                сч['компаний_без_номеров_было'] += 1
            if len(примеры) < 25:
                примеры.append((з['inn'], нов[0]['номер'], нов[0]['доб'], нов[0]['контекст'][150:260]))
        if not ПРОБА:
            with io.open(ВЫХОД, 'a', encoding='utf-8') as f:
                f.write(json.dumps(dict(з, номера=(з.get('номера') or []) + нов,
                                        доизвлечено=time.strftime('%Y-%m-%d %H:%M')), ensure_ascii=False) + '\n')
                f.flush()
                os.fsync(f.fileno())
        if n % 500 == 0:
            print('готово %d/%d за %d мин' % (n, len(задачи), (time.time() - t0) / 60), json.dumps(сч, ensure_ascii=False),
                  flush=True)
    for п in примеры:
        print(' ', п)
    if not ПРОБА:
        shutil.copyfile(ВЫХОД, os.path.join(r'C:\seostat\drop\drop-storage', os.path.basename(ВЫХОД)))
    сч['минут'] = round((time.time() - t0) / 60, 1)
    print('===ИТОГ===')
    print('готово', json.dumps(сч, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()

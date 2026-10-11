# -*- coding: utf-8 -*-
r"""Доизвлечение ПОЧТ из кэша страниц обхода: pochty_izvlech.найти — защита Joomla, Cloudflare, data-атрибуты, ROT13,
склейка в JS, текстовая обфускация, кириллические домены (ревизия №07/№09; шаблон обхода их не видит).

Как kc_doizvlech (номера): без скачивания, страницы текущего сайта из кэша, только адреса, которых в записи ещё нет.
Новая строка в <набор>-kontakty.jsonl — ТОЛЬКО у компаний с находкой (копия последней записи + новые адреса без роли:
роль — kc_dorazmetka, «чей» — kc_audit после агентов); остальные — отметкой в <набор>-doizvlech-pochty-sdelano.txt.
Запускать, когда файл обхода никто не пишет; останавливается при старте шагов после агентов.

    KC_NABOR=<набор> python kc_doizvlech_pochty.py      (KC_DOIZV_PROBA=1 — счёт и примеры без записи)
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
import kc_zakupki_dobor as KZ  # noqa: E402  (пора_стоп)
import meyer_nalichie as MN  # noqa: E402
import pochty_izvlech as PI  # noqa: E402

НАБОР = os.environ.get('KC_NABOR', 'pilot')
ВЫХОД = os.path.join(DIR, НАБОР + '-kontakty.jsonl')
СДЕЛАНО = os.path.join(DIR, НАБОР + '-doizvlech-pochty-sdelano.txt')
ПРОБА = os.environ.get('KC_DOIZV_PROBA') == '1'


def новые_почты(з):
    сайт_дом = MN.домен(з.get('сайт') or '')
    свои_стр = {u for u, ст in з.get('страницы') or [] if ст in ('ok', 'кэш')}
    есть = {(н.get('почта') or '').lower() for н in з.get('номера') or [] if н.get('почта')}
    есть |= {(x.get('почта') or '').lower() for x in з.get('почты_исключены') or []}
    нов = {}
    for стр in KK.прочитать_кэш(з['inn']).get('pages') or []:
        u, h = стр.get('url') or '', стр.get('html') or ''
        if not h or (u not in свои_стр and MN.домен(u) != сайт_дом):
            continue
        вид = None
        for e, как, поз in PI.найти(h):
            if e in есть:
                continue
            if e in нов:
                if u not in нов[e]['страницы']:
                    нов[e]['страницы'].append(u)
                continue
            if поз >= 0:  # подпись перед адресом — видимый текст до начала скрипта/тега защиты (не код скрипта)
                нач = max(h.rfind('<script', 0, поз), h.rfind('<joomla-hidden-mail', 0, поз + 1), -1)
                нач = нач if нач >= 0 and поз - нач < 6000 else поз
                контекст = PI.видимый(h[max(0, нач - 4000):нач])[-220:]
            else:
                вид = вид if вид is not None else PI.видимый(h)
                п = вид.lower().find(e.split('@')[0])
                контекст = вид[max(0, п - 200):п + 80] if п >= 0 else ''
            нов[e] = {'почта': e, 'доб': '', 'страницы': [u], 'контекст': re.sub(r'\s+', ' ', контекст),
                      'фио': '', 'должность': '', 'доизвлечена': как}
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
    сделано = set(io.open(СДЕЛАНО, encoding='utf-8').read().split()) if os.path.exists(СДЕЛАНО) else set()
    задачи = [з for з in последняя.values() if з.get('итог') == 'ok' and з.get('сайт') and not з.get('доизвлечено_почты')
              and з['inn'] not in сделано]
    if ПРОБА:
        задачи = задачи[:int(os.environ.get('KC_DOIZV_VYBORKA', '1500'))]
    print('компаний', len(задачи), 'проба' if ПРОБА else '', flush=True)
    t0, t0_iso, проверено = time.time(), time.strftime('%Y-%m-%dT%H:%M:%S'), time.time()
    сч = {'компаний_с_новыми': 0, 'новых_почт': 0, 'без_почт_было': 0}
    по_виду, примеры = {}, []
    for n, з in enumerate(задачи, 1):
        if not ПРОБА and time.time() - проверено > 60:
            проверено = time.time()
            if KZ.пора_стоп(t0_iso):
                print('оркестратор начал шаги после агентов — стоп', flush=True)
                break
        try:
            нов = новые_почты(з)
        except Exception as e:  # noqa: BLE001
            print('сбой', з['inn'], repr(e)[:100], flush=True)
            continue
        if нов:
            сч['компаний_с_новыми'] += 1
            сч['новых_почт'] += len(нов)
            if not any(н.get('почта') for н in з.get('номера') or []):
                сч['без_почт_было'] += 1
            for н in нов:
                по_виду[н['доизвлечена']] = по_виду.get(н['доизвлечена'], 0) + 1
            if len(примеры) < 30:
                примеры.append((з['inn'], нов[0]['почта'], нов[0]['доизвлечена'], нов[0]['контекст'][-90:]))
        if ПРОБА:
            continue
        if нов:
            with io.open(ВЫХОД, 'a', encoding='utf-8') as f:
                f.write(json.dumps(dict(з, номера=(з.get('номера') or []) + нов,
                                        доизвлечено_почты=time.strftime('%Y-%m-%d %H:%M')), ensure_ascii=False) + '\n')
                f.flush()
                os.fsync(f.fileno())
        else:
            with io.open(СДЕЛАНО, 'a', encoding='utf-8') as f:
                f.write(з['inn'] + '\n')
                f.flush()
                os.fsync(f.fileno())
    for п in примеры:
        print(' ', п)
    if not ПРОБА:
        shutil.copyfile(ВЫХОД, os.path.join(r'C:\seostat\drop\drop-storage', os.path.basename(ВЫХОД)))
    сч['по_виду'] = по_виду
    сч['минут'] = round((time.time() - t0) / 60, 1)
    print('===ИТОГ===')
    print('готово', json.dumps(сч, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()

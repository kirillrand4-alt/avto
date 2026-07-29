# -*- coding: utf-8 -*-
"""Скан центробежных компрессоров по всем рабочим тендерным площадкам.

Идея. Реестр ЭПБ показал, что запрос «центробежный компрессор» ловит малую часть парка:
та же машина называется нагнетателем, турбокомпрессором, воздуходувкой, ГПА, ЦНД.
Словарь обозначений собран линзой `smezh` и проверен на реестре. Здесь тот же словарь
раскатывается на площадки — и на текущие процедуры, и на планы закупок.

Что скрипт делает: по каждой паре (площадка × термин) открывает поиск через раннер на
сервере владельца, вытаскивает счётчик найденного и первые организации. Это **разведка
объёмов**, а не выгрузка: смысл в том, чтобы понять, где чего сколько, и уже потом
выгружать прицельно.

Запуск (из песочницы, раннер должен отвечать):
    python3 tender_centro_scan.py                 # все площадки, все термины
    python3 tender_centro_scan.py --only gpb,tektorg --terms "нагнетатель,ЦНД"

Выход: engineers-lens/centro/scan-ploshchadki.csv
"""
import argparse
import csv
import json
import os
import re
import subprocess
import sys
import urllib.parse

DIR = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(DIR, 'engineers-lens', 'centro')
RUNNER_CLIENT = os.environ.get(
    'RUNNER_CLIENT',
    '/tmp/claude-0/-home-user-avto/520847fd-7699-5483-869b-cf6d49851f67/scratchpad/run_on_server.py')

# Словарь обозначений центробежных машин. Собран линзой smezh, проверен на реестре ЭПБ:
# «нагнетатель» дал 3 195 записей, «воздуходувка» 1 617, «ЦНД» 297 — при том что прямой
# запрос «центробежный компрессор» давал 2 616. То есть половина парка называется иначе.
TERMS = [
    'центробежный компрессор',
    'нагнетатель',
    'турбокомпрессор',
    'воздуходувка',
    'турбовоздуходувка',
    'ЦНД',
    'компрессорная установка',
]

# Площадки, у которых проверена рабочая точка входа. Для каждой: как строится адрес
# поиска и чем ловится счётчик. Росэлторг требует антидетект-профиля (режет
# датацентровые адреса), поэтому ходит с dolphin.
PLATFORMS = {
    'gpb': dict(
        name='ЭТП ГПБ',
        url=lambda q: f'https://etpgpb.ru/procedures/?search={urllib.parse.quote(q)}',
        count=[r'([\d\s ]{1,9})[\s|]*предложени'],
        dolphin=False),
    'tektorg': dict(
        name='ТЭК-Торг 223-ФЗ',
        url=lambda q: f'https://www.tektorg.ru/223-fz/procedures?name={urllib.parse.quote(q)}',
        # «30 | закупок найдено» — между числом и словом стоит разделитель разметки,
        # поэтому \s* недостаточно: нужен и вертикальный штрих (ловушка В8, седьмой случай)
        count=[r'([\d\s ]{1,9})[\s|]*закупк\w+ найден'],
        dolphin=False),
    'tektorg_rn': dict(
        name='ТЭК-Торг, секция Роснефти',
        url=lambda q: f'https://www.tektorg.ru/rosneft/procedures?name={urllib.parse.quote(q)}',
        # «30 | закупок найдено» — между числом и словом стоит разделитель разметки,
        # поэтому \s* недостаточно: нужен и вертикальный штрих (ловушка В8, седьмой случай)
        count=[r'([\d\s ]{1,9})[\s|]*закупк\w+ найден'],
        dolphin=False),
    'fabrikant': dict(
        name='Фабрикант',
        url=lambda q: f'https://www.fabrikant.ru/procedure/search?query={urllib.parse.quote(q)}',
        count=[r'Всего[:\s|]{0,6}([\d\s ]{1,9})'],
        dolphin=False),
    'roseltorg': dict(
        name='Росэлторг',
        url=lambda q: ('https://www.roseltorg.ru/procedures/search?currency=all&query_field='
                       + urllib.parse.quote(q)),
        count=[r'([\d\s ]{1,9})\s*(?:процедур|закупок|результат)'],
        dolphin=True),
    'eis_plan': dict(
        name='ЕИС, план закупки 223-ФЗ (плановые)',
        url=lambda q: ('https://zakupki.gov.ru/epz/orderplan/search/results.html?searchString='
                       + urllib.parse.quote(q)
                       + '&morphology=on&fz223=on&sortBy=UPDATE_DATE&recordsPerPage=_50'),
        count=[r'Найдено[^\d]{0,20}([\d\s ]{1,9})'],
        dolphin=False),
}

ORG_PATTERNS = [
    r'Наименование организации \| ([^|]{5,70})',
    r'Заказчики \| ([^|]{5,70})',
    r'Организатор \| ([^|]{5,70})',
    r'ОРГАНИЗАТОР \| ([^|]{5,70})',
]


def probe(url, dolphin, cap=900000):
    args = {'url': url, 'screenshot': False, 'wait_ms': 11000, 'proxy': False,
            'ignore_https_errors': True, 'return_html': True, 'html_cap': cap}
    if dolphin:
        args['dolphin_profile'] = os.environ.get('DOLPHIN_PROFILE', '829115286')
        args['dolphin_keep'] = True
    p = subprocess.run([sys.executable, RUNNER_CLIENT, 'browser_probe',
                        json.dumps(args, ensure_ascii=False)],
                       capture_output=True, timeout=420)
    s = p.stdout.decode('utf-8', 'replace')
    i = s.find('{')
    if i < 0:
        return '', None
    try:
        d = (json.loads(s[i:]).get('data') or {})
    except Exception:  # noqa: BLE001
        return '', None
    return d.get('html') or '', d.get('http_status')


def flat(html):
    t = re.sub(r'<script.*?</script>', '', html, flags=re.S)
    t = re.sub(r'<style.*?</style>', '', t, flags=re.S)
    t = re.sub(r'<[^>]+>', ' | ', t).replace('&nbsp;', ' ')
    t = re.sub(r'[ \t]+', ' ', t)
    return re.sub(r'(\s*\|\s*)+', ' | ', t)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', default='')
    ap.add_argument('--terms', default='')
    a = ap.parse_args()
    keys = [k.strip() for k in a.only.split(',') if k.strip()] or list(PLATFORMS)
    terms = [t.strip() for t in a.terms.split(',') if t.strip()] or TERMS

    os.makedirs(OUT, exist_ok=True)
    rows = []
    for pk in keys:
        p = PLATFORMS[pk]
        for q in terms:
            url = p['url'](q)
            try:
                html, status = probe(url, p['dolphin'])
            except Exception as e:  # noqa: BLE001
                rows.append(dict(ploshchadka=p['name'], zapros=q, naydeno='',
                                 status='', primer='', url=url, oshibka=str(e)[:70]))
                print(f'{p["name"][:22]:22} {q[:24]:24} ОШИБКА {str(e)[:40]}', file=sys.stderr)
                continue
            t = flat(html)
            n = ''
            for pat in p['count']:
                m = re.search(pat, t)
                if m:
                    n = re.sub(r'\D', '', m.group(1))
                    break
            orgs = []
            for pat in ORG_PATTERNS:
                orgs += [x.strip() for x in re.findall(pat, t)]
            orgs = [o for o in dict.fromkeys(orgs) if len(o) > 6][:3]
            # ловушка В7: если html ровно в потолок, счётчик мог не попасть в разметку
            trunc = 'усечено' if len(html) >= 900000 else ''
            rows.append(dict(ploshchadka=p['name'], zapros=q, naydeno=n, status=status,
                             primer=' / '.join(orgs)[:120], url=url, oshibka=trunc))
            print(f'{p["name"][:22]:22} {q[:24]:24} найдено {n or "-":>8}  {trunc}  '
                  f'{orgs[0][:34] if orgs else ""}', file=sys.stderr)

    path = os.path.join(OUT, 'scan-ploshchadki.csv')
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, delimiter=';',
                           fieldnames=['ploshchadka', 'zapros', 'naydeno', 'status',
                                       'primer', 'url', 'oshibka'])
        w.writeheader()
        w.writerows(rows)
    print(f'\nзаписано {len(rows)} строк -> {path}', file=sys.stderr)


if __name__ == '__main__':
    main()

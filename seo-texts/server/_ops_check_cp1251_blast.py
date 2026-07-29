# -*- coding: utf-8 -*-
"""Радиус поражения дефекта кодировки: _fetch_site декодирует ВСЁ как utf-8.

На агрегаторе это стоило контакта заказчика. Но _fetch_site — общий краулер
сайтов компаний, и русский промышленный сайт на windows-1251 всё ещё обычное
дело. Если такие сайты есть в базе, мы теряем на них ВСЮ кириллицу: имена,
должности, подписи контактных блоков. Считаем долю на живых сайтах из базы.
"""
import json
import re
import sys
import urllib.request

sys.path.insert(0, r'C:\sender\server')
import enrich_contacts as EC  # noqa: E402
import enrich_db as EDB  # noqa: E402


def main():
    буф = []

    def P(s):
        буф.append(str(s))

    e = EDB.EnrichDB().cx
    таблицы = [r[0] for r in e.execute(
        "select name from sqlite_master where type='table'")]
    P(f'таблицы: {таблицы[:14]}')
    сайты = []
    for т in таблицы:
        try:
            колонки = [r[1] for r in e.execute(f'PRAGMA table_info({т})')]
        except Exception:  # noqa: BLE001
            continue
        for к in колонки:
            if not re.search(r'site|url|домен|domain|сайт', к, re.I):
                continue
            try:
                строки = e.execute(
                    f'select distinct "{к}" from "{т}" where "{к}" like '
                    f"'%.%' limit 400").fetchall()
            except Exception:  # noqa: BLE001
                continue
            for (v,) in строки:
                v = (v or '').strip()
                if not v or 'zakupki.gov' in v or 'filestore' in v:
                    continue
                d = EC._domain(v if v.startswith('http') else 'http://' + v)
                if not d or '.' not in d:
                    continue
                if any(a in d for a in EC._АГРЕГАТОРЫ_ТЕНДЕР):
                    continue
                if d not in сайты:
                    сайты.append(d)
            if len(сайты) > 60:
                break
        if len(сайты) > 60:
            break
    P(f'доменов-кандидатов из базы: {len(сайты)}')
    итог = {'проверено': 0, 'cp1251': 0, 'utf8': 0, 'не_ответил': 0,
            'потеряно_кириллицы': []}
    плохие = []
    for d in сайты[:14]:
        u = 'http://' + d
        try:
            req = urllib.request.Request(u, headers={
                'User-Agent': EC.VC.UA, 'Accept-Language': 'ru-RU,ru;q=0.9',
                'Accept': 'text/html,application/xhtml+xml'})
            with EC._DIRECT.open(req, timeout=18) as r:
                blob = r.read(400000)
                ct = (r.headers.get('Content-Type') or '')
        except Exception as ex:  # noqa: BLE001
            итог['не_ответил'] += 1
            P(f'  {d}: нет ответа ({type(ex).__name__})')
            continue
        итог['проверено'] += 1
        мета = re.search(rb'charset=["\']?([\w\-]+)', blob[:4000], re.I)
        объявл = (re.search(r'charset=([\w\-]+)', ct, re.I).group(1)
                  if re.search(r'charset=([\w\-]+)', ct, re.I)
                  else (мета.group(1).decode() if мета else '?')).lower()
        как_боевой = blob.decode('utf-8', 'replace')
        битых = как_боевой.count('\ufffd')
        кир_бой = sum(1 for c in как_боевой if 'а' <= c.lower() <= 'я')
        кир_1251 = sum(1 for c in blob.decode('cp1251', 'replace')
                       if 'а' <= c.lower() <= 'я')
        плохо = битых > 200
        if плохо:
            итог['cp1251'] += 1
            плохие.append(d)
            итог['потеряно_кириллицы'].append(
                {'сайт': d, 'кодировка': объявл, 'кириллицы_боевой': кир_бой,
                 'кириллицы_верно': кир_1251})
        else:
            итог['utf8'] += 1
        P(f'  {d}: объявлено={объявл} U+FFFD={битых} кириллица_боевой='
          f'{кир_бой} кириллица_cp1251={кир_1251} {"<-- ТЕРЯЕМ" if плохо else ""}')
    P(f'сайтов с убитой кириллицей: {плохие}')
    print('\n'.join(буф)[-11000:])
    print('ИТОГ ' + json.dumps(итог, ensure_ascii=False))


if __name__ == '__main__':
    main()

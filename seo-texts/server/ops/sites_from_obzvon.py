# -*- coding: utf-8 -*-
"""Сайты компаний из выгрузки обзвона — для тех, у кого в enrich.db их нет.

Наводка владельца 29.07: обход прошёл 203 компании из 555 и встал, потому что
у остальных в companies.site пусто. Но сайт может лежать в ВЫГРУЗКЕ ОБЗВОНА:
и в obzvon-index.db, и в call_company (seo.db) есть колонка sites — она просто
не переносилась в enrich.db.

Что делает: берёт ИНН без сайта, ищет их в обеих выгрузках, чистит мусор
(счётчики, CDN, сам checko, агрегаторы) и записывает найденное в
companies.site. После этого обходчик и сборщик руководства видят эти компании
как обычные.

Ничего не перезаписывает: если сайт уже есть — компания пропускается.
Запуск: python sites_from_obzvon.py [--only sales] [--dry]
"""
import io
import json
import os
import re
import sqlite3
import sys

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB       # noqa: E402
import enrich_contacts as EC  # noqa: E402

СУХОЙ = '--dry' in sys.argv
ТОЛЬКО = (sys.argv[sys.argv.index('--only') + 1]
          if '--only' in sys.argv else 'sales')
ОБЗ = r'C:\sender\obzvon-index.db'
СЕО = r'C:\seostat\data\seo.db'

# мусор, который выгрузка тащит в колонку «Сайты»: счётчики, CDN, сам источник
_МУСОР = re.compile(
    r'yastatic\.net|an\.yandex\.|mc\.yandex\.|avatars\.mds\.yandex|ads\.adfox\.'
    r'|chrome\.google\.com|checko\.ru|yandex\.st|google-analytics|googletagmanager'
    r'|gosuslugi\.ru/|w3\.org|schema\.org|\.jpg|\.png|\.svg', re.I)


def первый_живой(строка):
    """Первый пригодный домен из «сайт1 | сайт2 | …» выгрузки."""
    for кусок in re.split(r'[|,;\s]+', str(строка or '')):
        к = кусок.strip().strip('.,;"\'')
        if len(к) < 5 or _МУСОР.search(к):
            continue
        if not re.match(r'^(?:https?://)?[a-z0-9-]+(?:\.[a-z0-9-]+)+', к, re.I):
            continue
        # агрегаторы и справочники сайтом компании не считаем
        if not EC._is_own_site(к if к.startswith('http') else 'http://' + к):
            continue
        return re.sub(r'^https?://', '', к).rstrip('/')
    return ''


def ро(путь):
    if not os.path.exists(путь):
        return None
    try:
        cx = sqlite3.connect(f'file:{путь}?mode=ro', uri=True, timeout=120)
        cx.row_factory = sqlite3.Row
        return cx
    except Exception:  # noqa: BLE001
        return None


def main():
    db = EDB.EnrichDB()
    e = db.cx

    инны = []
    БАЗА = json.load(open(r'C:\sender\_ops\sales_base.json', encoding='utf-8'))
    было = set()
    for строки in БАЗА.values():
        for x in строки:
            i = str(x.get('inn') or '').strip()
            if i and i not in было:
                было.add(i)
                инны.append(i)
    if ТОЛЬКО != 'sales':
        for ln in io.open(r'C:\seostat\drop\drop-storage\centrifugal-core-inns.txt',
                          encoding='utf-8', errors='replace'):
            m = re.search(r'\b(\d{10}|\d{12})\b', ln)
            if m and m.group(1) not in было:
                было.add(m.group(1))
                инны.append(m.group(1))

    есть = {r[0] for r in e.execute(
        "select inn from companies where coalesce(trim(site),'')<>''")}
    нужны = [i for i in инны if i not in есть]
    out = {'ИНН_всего': len(инны), 'уже_с_сайтом': len(инны) - len(нужны),
           'ищем_для': len(нужны), 'из_obzvon_index': 0, 'из_seo_db': 0,
           'мусор_отсеян': 0, 'записано': 0, 'примеры': []}
    if not нужны:
        print(json.dumps(out, ensure_ascii=False))
        return

    найдено = {}
    q = ','.join('?' for _ in нужны)
    ob = ро(ОБЗ)
    if ob is not None:
        for r in ob.execute(
                f"select inn, sites from obzvon where inn in ({q}) "
                "and coalesce(trim(sites),'')<>''", нужны):
            s = первый_живой(r['sites'])
            if s:
                найдено.setdefault(r['inn'], (s, 'obzvon-index'))
            elif (r['sites'] or '').strip():
                out['мусор_отсеян'] += 1
        out['из_obzvon_index'] = len(найдено)
    se = ро(СЕО)
    if se is not None:
        было_n = len(найдено)
        for r in se.execute(
                f"select inn, sites from call_company where inn in ({q}) "
                "and coalesce(trim(sites),'')<>''", нужны):
            if r['inn'] in найдено:
                continue
            s = первый_живой(r['sites'])
            if s:
                найдено[r['inn']] = (s, 'seo.db')
            elif (r['sites'] or '').strip():
                out['мусор_отсеян'] += 1
        out['из_seo_db'] = len(найдено) - было_n

    for inn, (сайт, откуда) in найдено.items():
        if len(out['примеры']) < 12:
            out['примеры'].append({'инн': inn, 'сайт': сайт, 'откуда': откуда})
        if СУХОЙ:
            continue
        # upsert_company не затирает непустое существующее — здесь его и нет
        db.upsert_company(inn, site=сайт)
        out['записано'] += 1
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()

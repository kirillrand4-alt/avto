# -*- coding: utf-8 -*-
"""Сколько групп ВК теряет ПЕРВОЕ-совпадение в vk_slug_from_site.

Дефект виден глазами: у plastika-okon.ru слаг вышел «js». Причина —
_VK_LINK_RE ловит ЛЮБОЙ путь vk.com/<токен>, а виджет VK OpenAPI подключается
как //vk.com/js/api/openapi.js. Слово «js» в _VK_SLUG_DENY не внесено, и
функция возвращает его, обрывая перебор на первом же совпадении.

Считаем на кэше страниц: сколько компаний отдают мусорный первый слаг и
сколько из них имеют НАСТОЯЩУЮ группу, если проверить все кандидаты.
В базу не пишем.
"""
import gzip
import json
import os
import re
import sqlite3
import sys
import time
import traceback
import urllib.parse
import urllib.request

sys.path.insert(0, r'C:\sender\server')
import enrich_contacts as EC  # noqa: E402
import enrich_db as EDB       # noqa: E402

БАЗА = r'C:\sender\_ops\sales_base.json'
# служебные пути vk.com, которые НЕ являются сообществом
МУСОР = {'js', 'css', 'images', 'img', 'static', 'doc', 'docs', 'link', 'app',
         'shareimg', 'share', 'away', 'widget', 'video', 'audio', 'photo',
         'wall', 'topic', 'club', 'public', 'feed', 'im', 'login', 'help',
         'about', 'dev', 'apps', 'search', 'vk', 'page', 'note', 'market',
         'products', 'connect', 'id', 'write', 'mail', 'support'}


def P(*a):
    print(*a)
    sys.stdout.flush()


def вк(method, **prm):
    tok = EC._read_secret('VK_TOKEN') or os.environ.get('VK_TOKEN', '')
    prm.update(access_token=tok, v='5.199')
    u = f'https://api.vk.com/method/{method}?' + urllib.parse.urlencode(prm)
    try:
        raw = EC._DIRECT.open(urllib.request.Request(
            u, headers={'User-Agent': getattr(EC.VC, 'UA', 'Mozilla/5.0')}),
            timeout=20).read()
        d = json.loads(EC._раскодировать(raw, 'charset=utf-8'))
    except Exception as ex:  # noqa: BLE001
        return None, f'{type(ex).__name__}'
    if d.get('error'):
        return None, str((d['error'] or {}).get('error_msg'))[:60]
    return d.get('response'), ''


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    d = json.load(open(БАЗА, encoding='utf-8'))
    строки = []
    if isinstance(d, dict):
        for v in d.values():
            if isinstance(v, list):
                строки += v
    else:
        строки = d
    по_инн = {}
    for x in строки:
        i = str(x.get('inn') or '').strip()
        if i and i not in по_инн:
            по_инн[i] = x
    con = sqlite3.connect(EDB.DB_PATH)
    cur = con.cursor()
    кэш = os.environ.get('PAGECACHE_DIR', r'C:\seostat\drop\pagecache')
    пул = []
    for inn, x in по_инн.items():
        r = cur.execute('SELECT name, site FROM companies WHERE inn=?', (inn,)).fetchone()
        if not r or not (r[1] or ''):
            continue
        if os.path.exists(os.path.join(кэш, f'{inn}.json.gz')):
            пул.append({'inn': inn, 'name': r[0] or '', 'site': r[1]})
        if len(пул) >= n:
            break
    P('компаний с кэшем страниц:', len(пул))

    ст = {'компаний': len(пул), 'ссылок_vk_есть': 0, 'первый_мусор': 0,
          'старый_слаг': 0, 'новых_кандидатов': 0, 'группа_старым': 0,
          'группа_новым': 0, 'спасено': 0}
    примеры_мусора, спасённые = [], []
    for c in пул:
        try:
            with gzip.open(os.path.join(кэш, f'{c["inn"]}.json.gz'), 'rb') as f:
                dd = json.loads(f.read().decode('utf-8', 'replace'))
            html = ' '.join((p.get('html') or '') for p in (dd.get('pages') or []))
        except Exception:  # noqa: BLE001
            continue
        все = [m.group(1).strip('.').lower() for m in EC._VK_LINK_RE.finditer(html)]
        if не_пусто := [s for s in все if s]:
            ст['ссылок_vk_есть'] += 1
        # что вернёт БОЕВАЯ функция
        старый = ''
        for s in все:
            if s and s not in EC._VK_SLUG_DENY and not s.isdigit():
                старый = s
                break
        # что вернёт функция с расширенным деним
        канд, вид = [], set()
        for s in все:
            if s and s not in МУСОР and not s.isdigit() and s not in вид:
                вид.add(s)
                канд.append(s)
        if старый:
            ст['старый_слаг'] += 1
        if старый and старый in МУСОР:
            ст['первый_мусор'] += 1
            if len(примеры_мусора) < 8:
                примеры_мусора.append((c['site'], старый, канд[:3]))
        ст['новых_кандидатов'] += len(канд)

        стар_ок = False
        if старый:
            r1, e1 = вк('groups.getById', group_ids=старый, fields='contacts')
            time.sleep(0.34)
            g1 = (r1.get('groups') if isinstance(r1, dict) else r1) or []
            стар_ок = bool(g1)
            if стар_ок:
                ст['группа_старым'] += 1
        нов_ок, нов_слаг = False, ''
        for s in канд[:3]:
            r2, e2 = вк('groups.getById', group_ids=s, fields='contacts')
            time.sleep(0.34)
            g2 = (r2.get('groups') if isinstance(r2, dict) else r2) or []
            if g2:
                нов_ок, нов_слаг = True, s
                break
        if нов_ок:
            ст['группа_новым'] += 1
        if нов_ок and not стар_ок:
            ст['спасено'] += 1
            if len(спасённые) < 10:
                спасённые.append((c['site'], старый or '-', '->', нов_слаг))

    P('')
    for e in примеры_мусора:
        P('  МУСОРНЫЙ ПЕРВЫЙ СЛАГ:', e)
    for e in спасённые:
        P('  СПАСЕНО:', e)
    P('ИТОГ ВК-ФИКС: ' + json.dumps(ст, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except Exception:  # noqa: BLE001
        P('!! упало:', traceback.format_exc()[-700:].replace('\n', ' | '))

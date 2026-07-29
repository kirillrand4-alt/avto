# -*- coding: utf-8 -*-
"""Разведка карточек справочников + VK, шаг 0: что вообще доступно.

Ничего не пишем в базу. Только смотрим:
  * сколько компаний в sales_base и у скольких есть сайт в enrich.db;
  * какие ключи есть в окружении (xmlriver / VK / 2GIS);
  * отвечают ли с сервера 2ГИС (API и SSR-страница поиска) и VK API.
"""
import json
import os
import re
import sqlite3
import sys
import traceback
import urllib.parse
import urllib.request

sys.path.insert(0, r'C:\sender\server')
import enrich_contacts as EC  # noqa: E402
import enrich_db as EDB       # noqa: E402

БАЗА = r'C:\sender\_ops\sales_base.json'


def P(*a):
    print(*a)
    sys.stdout.flush()


def шаг(имя, fn):
    try:
        fn()
    except Exception:  # noqa: BLE001
        P(f'!! {имя} упал:', traceback.format_exc()[-400:].replace('\n', ' | '))


def строки_базы():
    d = json.load(open(БАЗА, encoding='utf-8'))
    out = []
    if isinstance(d, dict):
        for v in d.values():
            if isinstance(v, list):
                out += v
    elif isinstance(d, list):
        out = d
    return out


def гет(u, тайм=15, hdr=None):
    """Сырые байты + заявленный ctype. Кодировку разбирает EC._раскодировать."""
    h = {'User-Agent': getattr(EC.VC, 'UA', 'Mozilla/5.0')}
    if hdr:
        h.update(hdr)
    try:
        r = EC._DIRECT.open(urllib.request.Request(u, headers=h), timeout=тайм)
        return r.read(), r.headers.get('Content-Type', ''), r.status
    except Exception as ex:  # noqa: BLE001
        тело = b''
        try:
            тело = ex.read()[:400]  # HTTPError несёт тело с причиной
        except Exception:  # noqa: BLE001
            pass
        return тело, f'ОШИБКА {type(ex).__name__}: {str(ex)[:90]}', 0


ИТОГ = {}


def main():
    def _база():
        строки = строки_базы()
        ИТОГ['база'] = len(строки)
        P('sales_base строк:', len(строки), 'ключи:',
          sorted(строки[0].keys())[:20] if строки else '-')
    шаг('sales_base', _база)

    def _db():
        con = sqlite3.connect(EDB.DB_PATH)
        cur = con.cursor()
        всего = cur.execute('SELECT COUNT(*) FROM companies').fetchone()[0]
        с_сайтом = cur.execute(
            "SELECT COUNT(*) FROM companies WHERE site IS NOT NULL AND site<>''"
        ).fetchone()[0]
        ИТОГ['сайтов'] = с_сайтом
        P('enrich.db:', EDB.DB_PATH, '| companies:', всего, '| с сайтом:', с_сайтом)
        P('  пример сайтов:', cur.execute(
            "SELECT inn,name,site FROM companies WHERE site<>'' LIMIT 3").fetchall())
    шаг('enrich.db', _db)

    def _ключи():
        имена = ('XMLRIVER_USER', 'XMLRIVER_KEY', 'VK_TOKEN', 'VK_TOKEN_USER',
                 'VK_SERVICE_TOKEN', 'DGIS_KEY', 'TWOGIS_KEY', 'DADATA_TOKEN',
                 'DOLPHIN_TOKEN', 'YANDEX_MAPS_KEY', 'CAPMONSTER_KEY')
        ключи = {}
        for и in имена:
            try:
                v = EC._read_secret(и) or ''
            except Exception:  # noqa: BLE001
                v = ''
            v = v or os.environ.get(и, '')
            ключи[и] = (f'есть({len(v)})' if v else 'НЕТ')
        P('ключи:', json.dumps(ключи, ensure_ascii=False))
    шаг('ключи', _ключи)

    def _2gis_api():
        демо = 'ruxlih0718'
        u = ('https://catalog.api.2gis.ru/3.0/items?q='
             + urllib.parse.quote('Криогенмаш Балашиха') + '&key=' + демо
             + '&fields=items.contact_groups,items.address,items.org')
        raw, ct, st = гет(u)
        txt = EC._раскодировать(raw, ct) if raw else str(ct)
        P('2ГИС API demo-key: HTTP', st, 'байт', len(raw), '|',
          txt[:300].replace('\n', ' '))
    шаг('2gis-api', _2gis_api)

    def _2gis_ssr():
        u2 = 'https://2gis.ru/search/' + urllib.parse.quote('Криогенмаш')
        raw2, ct2, st2 = гет(u2)
        t2 = EC._раскодировать(raw2, ct2) if raw2 else str(ct2)
        P('2ГИС SSR /search: HTTP', st2, 'байт', len(raw2), 'ctype', str(ct2)[:60])
        P('   initialState:', 'initialState' in t2, '| contact_groups:',
          'contact_groups' in t2, '| кириллицы:', len(re.findall(r'[а-яё]', t2, re.I)))
        P('   голова:', t2[:200].replace('\n', ' '))
    шаг('2gis-ssr', _2gis_ssr)

    def _vk():
        tok = EC._read_secret('VK_TOKEN') or os.environ.get('VK_TOKEN', '')
        if not tok:
            P('VK: токена нет')
            return
        uv = ('https://api.vk.com/method/groups.getById?group_ids=vk&v=5.199'
              '&fields=contacts,site,description&access_token=' + tok)
        rawv, ctv, stv = гет(uv)
        P('VK groups.getById: HTTP', stv, '|',
          (EC._раскодировать(rawv, ctv) if rawv else str(ctv))[:220])
    шаг('vk', _vk)

    P('ИТОГ: база=%s сайтов=%s' % (ИТОГ.get('база'), ИТОГ.get('сайтов')))


if __name__ == '__main__':
    main()

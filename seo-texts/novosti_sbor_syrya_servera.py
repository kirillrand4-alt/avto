# -*- coding: utf-8 -*-
"""Сырьё для разбора в песочнице: сервер собирает материалы и кладёт их на дроп.

Разделение труда (решение владельца 17.09): СЫРЬЁ СОБИРАЕТ СЕРВЕР (у него ключ xmlriver
и доступ к источникам), КЛАССИФИЦИРУЕТ ПЕСОЧНИЦА (у неё живой путь к провайдеру, тогда
как с сервера один из двух адресов router.cheap мёртв).

Здесь НЕ ВЫЗЫВАЕТСЯ провайдер ни разу: ни одного токена квоты, ни одного шанса словить
10054. Только сбор и выкладка.

Запросы — те же десять, что дали 49 сырых материалов и ноль событий: замер должен быть
сравним со старым. Контрольный выдуманный запрос обязан дать ноль материалов.

Запуск: python3 seo-texts/zapusk_na_servere.py novosti_sbor_syrya_servera.py [дней] [на_запрос]
"""
import json
import os
import sqlite3
import sys
import time

sys.path.insert(0, r'C:\sender\server')
import news_scan as NS  # noqa: E402

BAZA = r'C:\sender\enrich.db'
IMYA_NA_DROPE = '3s-syryo-novostey-sbor.json'

OTRASLI = ['химический завод', 'нефтехимический комбинат', 'нефтеперерабатывающий завод',
           'газоперерабатывающий завод', 'производство полимеров',
           'завод минеральных удобрений', 'производство аммиака', 'производство метанола',
           'металлургический комбинат', 'сталелитейный завод']
TRIGGER = 'подписано соглашение о строительстве'
KONTROL = ['подписано соглашение о строительстве комбинат щварцкопфер']


def na_drop(imya, telo):
    url = os.environ.get('DROP_URL') or 'https://parsercompressor.online/drop'
    tok = os.environ.get('DROP_TOKEN') or ''
    if not tok:
        for p in (r'C:\sender\server\runner-secrets.env', r'C:\sender\runner-secrets.env',
                  r'C:\sender\server\.env', r'C:\sender\.env'):
            try:
                for line in open(p, encoding='utf-8', errors='replace'):
                    if line.strip().startswith('DROP_TOKEN='):
                        tok = line.split('=', 1)[1].strip()
                    if line.strip().startswith('DROP_URL='):
                        url = line.split('=', 1)[1].strip()
            except Exception:  # noqa: BLE001
                continue
            if tok:
                break
    if not tok:
        print('  ДРОП: токена нет, %s не выложен' % imya)
        return False
    import urllib.request as U
    b = telo.encode('utf-8') if isinstance(telo, str) else telo
    req = U.Request('%s/%s' % (url.rstrip('/'), imya), data=b, method='PUT',
                    headers={'X-Drop-Token': tok})
    with U.urlopen(req, timeout=180) as r:
        print('  ДРОП: %s выложен (%d Б), ответ %s' % (imya, len(b), r.status))
    return True


def main():
    dney = int(sys.argv[1]) if len(sys.argv) > 1 else 45
    na_zapros = int(sys.argv[2]) if len(sys.argv) > 2 else 8
    zapros = ['%s %s' % (TRIGGER, o) for o in OTRASLI]

    t0 = time.time()
    print('### СБОР: %d запросов, окно %d дней, до %d на запрос' % (len(zapros), dney, na_zapros))
    try:
        raw = NS.col_xmlriver(zapros, dney, na_zapros, engines=('yandex',))
    except Exception as ex:  # noqa: BLE001
        print('коллектор упал: %s: %s' % (type(ex).__name__, str(ex)[:200]))
        return 2
    print('  сырых материалов: %d за %.0f с' % (len(raw), time.time() - t0))

    # контроль: выдуманный запрос обязан дать ноль
    try:
        kon = NS.col_xmlriver(KONTROL, dney, na_zapros, engines=('yandex',))
        print('  КОНТРОЛЬ (выдуманный комбинат): %d материалов (должно быть 0)' % len(kon))
    except Exception as ex:  # noqa: BLE001
        print('  КОНТРОЛЬ упал: %s' % str(ex)[:120])

    # дедуп-пометка: виден ли материал в seen_news (не выбрасываем, а помечаем)
    vid = {}
    try:
        con = sqlite3.connect('file:%s?mode=ro' % BAZA, uri=True)
        cur = con.cursor()
        for x in raw:
            if not isinstance(x, dict):
                continue
            u = x.get('url') or x.get('link') or ''
            try:
                k = NS._norm_url(u)
            except Exception:  # noqa: BLE001
                k = u
            vid[u] = bool(k and cur.execute('SELECT 1 FROM seen_news WHERE k=?',
                                            (k,)).fetchone())
        con.close()
    except Exception as ex:  # noqa: BLE001
        print('  seen_news не прочиталась: %s' % str(ex)[:110])

    vygruzka = []
    for i, x in enumerate(raw):
        if not isinstance(x, dict):
            x = {'title': str(x)}
        u = x.get('url') or x.get('link') or ''
        vygruzka.append({
            'n': i + 1,
            'title': x.get('title') or x.get('name') or '',
            'snippet': (x.get('snippet') or x.get('passage') or x.get('text') or '')[:800],
            'url': u,
            'source': x.get('source') or x.get('src') or 'xmlriver-yandex',
            'ts': x.get('ts') or x.get('date') or '',
            'uzhe_videli': vid.get(u),
            'kluchi_ishodnika': sorted(x.keys())[:12],
        })
    pust = sum(1 for v in vygruzka if not v['title'])
    videli = sum(1 for v in vygruzka if v['uzhe_videli'])
    print('  из них без заголовка: %d | уже в seen_news: %d' % (pust, videli))
    print('  первые заголовки:')
    for v in vygruzka[:8]:
        print('   - %s' % (v['title'] or '(пусто)')[:104])

    na_drop(IMYA_NA_DROPE, json.dumps(vygruzka, ensure_ascii=False, indent=1))
    print('\n=== ИТОГ СБОРА: материалов %d, с заголовком %d, новых (не в seen_news) %d, '
          'за %.0f с ===' % (len(vygruzka), len(vygruzka) - pust, len(vygruzka) - videli,
                             time.time() - t0))
    return 0


if __name__ == '__main__':
    sys.exit(main())

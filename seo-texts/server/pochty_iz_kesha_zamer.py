# -*- coding: utf-8 -*-
r"""Первая фаза добора: вынуть адреса из кэша страниц, БЕЗ записи в базу.

Вопрос владельца 27.08: «у нас 35к паспортов, все ли почты мы вытянули со
страниц?» Нет: адрес, снятый с сайта, есть только у 9 897 из 35 495 паспортов.
Считаем по кэшу, у скольких из остальных адрес на страницах ЕСТЬ — и сколько
из них новых для базы.

Читает только диск, в базу не пишет. Результат построчно в jsonl с fsync:
прогон на 25 тысяч кэшей длинный, обрыв не должен стирать измеренное.
Резюмируемый — повторный запуск продолжает с места обрыва.

    python pochty_iz_kesha_zamer.py
"""
import gzip
import json
import os
import re
import sqlite3
import sys
import time

BD = os.environ.get('ENRICH_DB', r'C:\sender\enrich.db')
KESH = os.environ.get('PAGECACHE_DIR', r'C:\seostat\drop\pagecache')
ВЫХОД = r'C:\sender\_tmp\pochty-v-keshe.jsonl'
С_САЙТА = {'own-site', 'zenno', 'обзвон-сайт'}
_ПОЧТА = re.compile(r'[\w.+-]+@[\w.-]+\.\w{2,6}')
# Расширения картинок в имени файла ловятся регуляркой почты (logo@2x.png),
# служебные ящики систем аналитики и заглушки нам тоже не нужны.
_МУСОР = ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.ico', '@2x',
          'sentry.io', 'example.com', 'domain.com', 'wixpress.com',
          'sentry-next', '.bmp', 'yourdomain')


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    сделано = set()
    if os.path.exists(ВЫХОД):
        with open(ВЫХОД, encoding='utf-8', errors='replace') as f:
            for s in f:
                try:
                    сделано.add(json.loads(s)['инн'])
                except Exception:  # noqa: BLE001
                    pass

    c = sqlite3.connect('file:%s?mode=ro' % BD.replace('\\', '/'), uri=True)
    паспорт = {str(r[0]) for r in c.execute(
        "select inn from site_facts where coalesce(facts_json,'')<>''")}
    с_сайта, любые = set(), {}
    for r in c.execute("select inn, lower(coalesce(email,'')) em, "
                       "coalesce(source,'') s, coalesce(pometka,'') p from emails"):
        инн = str(r[0])
        if r[1]:
            любые.setdefault(инн, set()).add(r[1])
            if r[2] in С_САЙТА or 'кэш-добор' in (r[3] or ''):
                с_сайта.add(инн)
    c.close()

    цели = sorted(паспорт - с_сайта - сделано)
    d = {'паспортов': len(паспорт), 'адрес_с_сайта_уже_есть': len(с_сайта),
         'проверяем': len(цели), 'уже_проверено_ранее': len(сделано)}
    print(json.dumps(d, ensure_ascii=False), flush=True)

    итог = {'кэша нет': 0, 'почт нет на страницах': 0, 'ЕСТЬ ПОЧТА': 0,
            'из них полностью новые': 0, 'адресов_всего': 0}
    вых = open(ВЫХОД, 'a', encoding='utf-8')
    t0 = time.time()
    for n, инн in enumerate(цели, 1):
        п = os.path.join(KESH, инн + '.json.gz')
        if not os.path.exists(п):
            итог['кэша нет'] += 1
            continue
        try:
            with gzip.open(п, 'rt', encoding='utf-8', errors='replace') as fh:
                дан = json.load(fh)
        except Exception:  # noqa: BLE001
            итог['кэша нет'] += 1
            continue
        стр = дан.get('pages') or дан.get('stranicy') or []
        найд = {}
        for p in стр[:10]:
            h = str((p or {}).get('html') or (p or {}).get('text') or '')[:80000]
            if '@' not in h:
                continue
            урл = str((p or {}).get('url') or '')[:200]
            for a in _ПОЧТА.findall(h):
                a = a.lower()
                if not any(m in a for m in _МУСОР) and a not in найд:
                    найд[a] = урл
        if not найд:
            итог['почт нет на страницах'] += 1
            вых.write(json.dumps({'инн': инн, 'почт': 0}, ensure_ascii=False) + '\n')
        else:
            итог['ЕСТЬ ПОЧТА'] += 1
            итог['адресов_всего'] += len(найд)
            новые = set(найд) - (любые.get(инн) or set())
            if not (любые.get(инн) or set()):
                итог['из них полностью новые'] += 1
            # ПИШЕМ ВСЕ АДРЕСА, а не примеры: вторая фаза берёт запись отсюда,
            # и трёх образцов ей мало. Рядом — страница, на которой адрес найден:
            # по ней add_email решает, снят ли он с собственного сайта компании.
            вых.write(json.dumps({'инн': инн, 'почт': len(найд),
                                  'новых': len(новые),
                                  'адреса': [[a, найд[a]] for a in sorted(найд)]},
                                 ensure_ascii=False) + '\n')
        if n % 500 == 0:
            вых.flush()
            os.fsync(вых.fileno())
            print(json.dumps({'прошли': n, 'секунд': round(time.time() - t0),
                              **итог}, ensure_ascii=False), flush=True)
    вых.flush()
    os.fsync(вых.fileno())
    вых.close()
    итог['секунд'] = round(time.time() - t0)
    print(json.dumps(итог, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())

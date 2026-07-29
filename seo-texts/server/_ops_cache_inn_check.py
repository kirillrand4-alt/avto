# -*- coding: utf-8 -*-
"""Совпадает ли ИНН, под который записан кэш, с именем файла кэша.

В потоке переразметки нашлась строка «файл 7817311045.json.gz -> инн
3666123900»: имя файла и разрешённый ИНН РАЗНЫЕ. Кэш назван по компании, а
ИНН доставался поиском по домену — если домен совпал с чужой карточкой, все
телефоны компании уехали бы соседу. Ровно так уже вышло с hh, поэтому здесь
проверяем ДО того, как поверить прогону.

Считаем: сколько строк совпало, сколько разъехалось и на чём именно.
"""
import io
import json
import os
import re
import sys

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB  # noqa: E402

ПОТОК = r'C:\seostat\drop\pagecache_roles.jsonl'
e = EDB.EnrichDB().cx


def main():
    строки = []
    for ln in io.open(ПОТОК, encoding='utf-8', errors='replace'):
        try:
            строки.append(json.loads(ln))
        except Exception:  # noqa: BLE001
            continue
    совпало, разъехалось = 0, []
    без_инн_в_имени = 0
    for x in строки:
        имя = str(x.get('файл') or '')
        m = re.match(r'(\d{10}|\d{12})', имя)
        if not m:
            без_инн_в_имени += 1
            continue
        if not x.get('inn'):
            continue
        if m.group(1) == str(x['inn']):
            совпало += 1
        else:
            разъехалось.append({'файл': имя, 'инн_из_имени': m.group(1),
                                'инн_записи': x['inn'], 'ошибка': x.get('err')})
    out = {'строк_потока': len(строки), 'имя_без_инн': без_инн_в_имени,
           'совпало': совпало, 'разъехалось': len(разъехалось),
           'примеры': разъехалось[:10]}
    # что реально записано под «чужой» ИНН
    for x in разъехалось[:6]:
        n = e.execute("SELECT COUNT(*) FROM phone_contacts WHERE inn=? AND "
                      "source='сайт компании'", (x['инн_записи'],)).fetchone()[0]
        x['телефонов_у_инн_записи'] = n
        c = e.execute('SELECT name, site FROM companies WHERE inn=?',
                      (x['инн_записи'],)).fetchone()
        x['кому_принадлежит_инн'] = (c or ['', ''])[0]
        x['сайт'] = (c or ['', ''])[1]
        c2 = e.execute('SELECT name, site FROM companies WHERE inn=?',
                       (x['инн_из_имени'],)).fetchone()
        x['кому_принадлежит_имя_файла'] = (c2 or ['', ''])[0]
        x['сайт_из_имени'] = (c2 or ['', ''])[1]
    print(json.dumps(out, ensure_ascii=False, indent=1)[:5000])
    print(json.dumps({k: v for k, v in out.items() if k != 'примеры'},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()

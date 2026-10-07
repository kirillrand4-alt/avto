# -*- coding: utf-8 -*-
r"""Файл 5 (парк): чья страница-источник номера. Владелец 07.10: «номера с checko.ru бесполезны,
выкинь», «только сайт или тендерные площадки». Для каждой не-checko ссылки из park5.jsonl —
живая страница и проверка meyer_nalichie.чья (свой сайт / ИНН / название на странице);
ядра названия — из enrich.db/obzvon и из park_panel.db (новые для Meyer там только и есть).
Выход (fsync): C:\sender\server\park5-chya.jsonl -> копия на дроп.
"""
import io
import json
import os
import re
import shutil
import sqlite3
import sys
import urllib.parse

DIR = r'C:\sender\server'
sys.path.insert(0, DIR)
sys.path.insert(0, r'C:\sender')
os.chdir(DIR)
import meyer_proverka as MP  # noqa: E402
import meyer_nalichie as MN  # noqa: E402

ДРОП = r'C:\seostat\drop\drop-storage'
ВЫХОД = os.path.join(DIR, 'park5-chya.jsonl')


def main():
    стр = [json.loads(s) for s in io.open(os.path.join(DIR, 'park5.jsonl'), encoding='utf-8')]
    комп = стр[0]['данные']
    пары = sorted({(x['inn'], x['url']) for x in стр[1:]
                   if x['url'] and 'checko.ru' not in (urllib.parse.urlsplit(x['url']).hostname or '')})
    MN.загрузить_компании({i for i, _ in пары})
    c = sqlite3.connect('file:%s?mode=ro' % os.path.join(ДРОП, 'park_panel.db'), uri=True)
    for инн, имя in c.execute('select inn, nazvanie from predpriyatie'):
        инн = str(инн)
        if инн not in комп:
            continue
        ядра, домены = MN.КОМП.setdefault(инн, (set(), set()))
        for кус in re.findall(r'[«"]+([^«»"]{3,})[»"]+', имя or ''):
            ядра.add(re.sub(r'\s+', ' ', кус).strip().lower())
    c.close()
    if os.path.exists(ВЫХОД):
        os.remove(ВЫХОД)
    итог = {}
    with io.open(ВЫХОД, 'a', encoding='utf-8') as f:
        for инн, url in пары:
            ст, html, _ = MN.скачать(url)
            текст = MP.в_текст(html) if ст == 'ok' else ''
            з = {'inn': инн, 'url': url, 'страница': ст,
                 'чья': MN.чья(инн, url, текст) if текст else 'страница не открылась',
                 'ядра': sorted(MN.КОМП.get(инн, (set(), set()))[0])[:4],
                 'домены': sorted(MN.КОМП.get(инн, (set(), set()))[1])[:4],
                 'заголовок': re.sub(r'\s+', ' ', (re.search(r'(?is)<title[^>]*>(.*?)</title>', html or '') or [None, ''])[1])[:120]}
            f.write(json.dumps(з, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())
            итог[з['чья'][:3]] = итог.get(з['чья'][:3], 0) + 1
    shutil.copyfile(ВЫХОД, os.path.join(ДРОП, 'park5-chya.jsonl'))
    print('===ИТОГ===')
    print(json.dumps({'ссылок': len(пары), 'итог': итог}, ensure_ascii=False))


if __name__ == '__main__':
    main()

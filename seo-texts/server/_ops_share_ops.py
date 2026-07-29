# -*- coding: utf-8 -*-
"""Выложить боевые скрипты конвейера на дроп, чтобы забрать их в песочницу.

Зачем: часть кода, который реально пишет контакты (ops-скрипты обхода сайтов,
чеко и ЕИС), живёт ТОЛЬКО на сервере — в репозитории её нет. Править вслепую
нельзя, а панельный get режет файл на 300 КБ, поэтому кладём через дроп.
"""
import json
import os
import shutil

DROP = r'C:\seostat\drop\drop-storage'
WANT = [
    r'C:\sender\server\enrich_contacts.py',
    r'C:\sender\server\enrich_db.py',
    r'C:\sender\_ops\sales_sites.py',
    r'C:\sender\_ops\staff_crawl.py',
    r'C:\sender\_ops\checko_contacts.py',
    r'C:\sender\_ops\sales_eis.py',
    r'C:\sender\_ops\core_sites.py',
    r'C:\sender\_ops\core_eis.py',
    r'C:\sender\_ops\sales_discover.py',
    r'C:\sender\_ops\phones_clean.py',
]


def main():
    out = {'выложено': [], 'нет_файла': []}
    for p in WANT:
        if not os.path.exists(p):
            out['нет_файла'].append(p)
            continue
        name = 'srv-' + os.path.basename(p)
        shutil.copy2(p, os.path.join(DROP, name))
        out['выложено'].append({'имя': name, 'байт': os.path.getsize(p)})
    print(json.dumps(out, ensure_ascii=False))


if __name__ == '__main__':
    main()

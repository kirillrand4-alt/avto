# -*- coding: utf-8 -*-
"""Убрать из резюма строки по файлам, которые надо переработать заново.

После починки привязки ИНН пострадавшие файлы кэша нужно прогнать ещё раз, но
резюм считает их сделанными. Удаляем ровно их строки, остальное резюмо
сохраняем — переделывать двести файлов ради десяти незачем.

Запуск: python _ops_reset_stream.py поток.jsonl ИНН1 ИНН2 ...
"""
import io
import json
import os
import re
import sys

ИМЯ = next((a for a in sys.argv[1:] if a.endswith('.jsonl')),
           'pagecache_roles.jsonl')
ПУТЬ = r'C:\seostat\drop' + '\\' + ИМЯ
ЦЕЛИ = [a for a in sys.argv[1:] if a.isdigit()]


def main():
    if not os.path.exists(ПУТЬ):
        print(json.dumps({'нет файла': ПУТЬ}, ensure_ascii=False))
        return
    оставить, убрано = [], 0
    for ln in io.open(ПУТЬ, encoding='utf-8', errors='replace'):
        try:
            x = json.loads(ln)
        except Exception:  # noqa: BLE001
            оставить.append(ln)
            continue
        имя = str(x.get('файл') or '')
        m = re.match(r'(\d{10}|\d{12})', имя)
        # выкидываем и по «правильному» ИНН из имени, и по ошибочному в записи
        if (m and m.group(1) in ЦЕЛИ) or str(x.get('inn') or '') in ЦЕЛИ:
            убрано += 1
            continue
        оставить.append(ln)
    with io.open(ПУТЬ, 'w', encoding='utf-8') as f:
        f.writelines(оставить)
        f.flush()
        os.fsync(f.fileno())
    print(json.dumps({'поток': ИМЯ, 'убрано_строк': убрано,
                      'осталось': len(оставить)}, ensure_ascii=False))


if __name__ == '__main__':
    main()

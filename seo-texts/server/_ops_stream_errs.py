# -*- coding: utf-8 -*-
"""Ошибки резюмируемого прогона: что именно не доехало и почему.

Прогон переразметки кэша дважды упёрся в одни и те же пять файлов. Пока не
видно текста ошибки, непонятно, это битые файлы или сбой кода, — а «пять из
двухсот» слишком легко списать на мелочь и потерять.

Запуск: python _ops_stream_errs.py имя_потока.jsonl
"""
import io
import json
import os
import sys

ИМЯ = next((a for a in sys.argv[1:] if a.endswith('.jsonl')),
           'pagecache_roles.jsonl')
ПУТЬ = r'C:\seostat\drop' + '\\' + ИМЯ


def main():
    if not os.path.exists(ПУТЬ):
        print(json.dumps({'нет файла': ПУТЬ}, ensure_ascii=False))
        return
    строки = []
    for ln in io.open(ПУТЬ, encoding='utf-8', errors='replace'):
        try:
            строки.append(json.loads(ln))
        except Exception:  # noqa: BLE001
            continue
    ош = [x for x in строки if x.get('err')]
    свод = {}
    for x in ош:
        свод[str(x['err'])[:80]] = свод.get(str(x['err'])[:80], 0) + 1
    print(json.dumps({'строк': len(строки), 'с_ошибкой': len(ош),
                      'виды_ошибок': свод,
                      'примеры': ош[-8:]}, ensure_ascii=False, indent=1)[:3000])


if __name__ == '__main__':
    main()

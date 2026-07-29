# -*- coding: utf-8 -*-
r"""Глазами: что РЕАЛЬНО стоит в окнах «Контактное лицо» и что из них берёт _фио.

Нужно, чтобы отличить три разные причины пустого контакта:
  * окна нет вовсе (агрегатор прячет контакт за регистрацией);
  * окно есть, но в нём нет человека (обезличенная строка);
  * окно есть, человек есть, а _фио его не достаёт (дефект разбора).
"""
import io
import json
import os
import re
import sys
import traceback

sys.path.insert(0, r'C:\sender\server')
import enrich_contacts as EC  # noqa: E402

ПОТОК = r'C:\seostat\drop\re_agg_stream.jsonl'


def p(*a):
    print(*a)
    sys.stdout.flush()


def main():
    лимит = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    только_пустые = '--empty' in sys.argv
    n = 0
    стат = {'окон': 0, 'фио': 0, 'почта': 0, 'телефон': 0, 'пусто_совсем': 0}
    for ln in io.open(ПОТОК, encoding='utf-8', errors='replace'):
        try:
            j = json.loads(ln)
        except Exception:  # noqa: BLE001
            continue
        for w in (j.get('окна') or []):
            стат['окон'] += 1
            ф = EC._фио(w)
            почты = [x.lower() for x in EC.EMAIL_RE.findall(w)
                     if not EC._is_junk_email(x)
                     and not any(a.split('.')[0] in x.lower()
                                 for a in EC._АГРЕГАТОРЫ_ТЕНДЕР)]
            тм = next(EC.phones_in(w), None)
            if ф:
                стат['фио'] += 1
            if почты:
                стат['почта'] += 1
            if тм:
                стат['телефон'] += 1
            if not (ф or почты or тм):
                стат['пусто_совсем'] += 1
            if только_пустые and ф:
                continue
            if n < лимит:
                n += 1
                p('ОКНО[%s] фио=%r почта=%s тел=%s :: %s'
                  % (j.get('inn'), ф, (почты[0] if почты else ''),
                     (тм.group(0).strip() if тм else ''),
                     re.sub(r'\s+', ' ', w)[:200]))
    p('ИТОГ ' + json.dumps(стат, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except Exception:  # noqa: BLE001
        p('ФАТАЛЬНО:', traceback.format_exc()[-800:])

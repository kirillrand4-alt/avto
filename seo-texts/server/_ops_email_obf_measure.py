# -*- coding: utf-8 -*-
"""Замер: сколько адресов теряется на НЕОХВАЧЕННЫХ формах обфускации.

Деобфускация в конвейере есть, но требует СКОБОК вокруг слова: «info [at]
zavod.ru», «info (собака) zavod.ru». На русских сайтах адрес чаще пишут без
скобок — «info собака zavod точка ru» — и такие формы разбор не берёт.

Прежде чем усложнять регулярку, надо увидеть цифру: если на всём кэше форма
встречается ноль раз, сложность не нужна. Ничего не пишем — только считаем и
показываем живые куски текста.
"""
import gzip
import io
import json
import os
import re
import sys

sys.path.insert(0, r'C:\sender\server')
import enrich_contacts as EC  # noqa: E402

КЭШ = r'C:\seostat\drop\pagecache'

# формы БЕЗ скобок и прочее, чего нет в боевом _DEOBF
ФОРМЫ = [
    ('слово собака без скобок',
     re.compile(r'[\w.\-]{2,}\s+(?:собака|at|эт)\s+[\w.\-]{2,}', re.I)),
    ('слово точка без скобок',
     re.compile(r'[\w\-]{2,}\s+(?:точка|dot|тчк)\s+(?:ru|рф|com|su)\b', re.I)),
    ('(a) вместо (at)',
     re.compile(r'[\w.\-]{2,}\s*[\[({]\s*a\s*[\])}]\s*[\w.\-]{2,}', re.I)),
    ('пробелы вокруг @',
     re.compile(r'[\w.\-]{2,}\s+@\s+[\w.\-]{2,}\.[a-z]{2,}', re.I)),
    ('собака-слитно-дефисами',
     re.compile(r'[\w.\-]{2,}[-_](?:собака|at)[-_][\w.\-]{2,}', re.I)),
]


def текст(h):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ',
                  re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', h,
                         flags=re.S | re.I)))


def main():
    out = {'файлов': 0, 'страниц': 0}
    счёт = {имя: 0 for имя, _ in ФОРМЫ}
    примеры = {имя: [] for имя, _ in ФОРМЫ}
    компаний = {имя: set() for имя, _ in ФОРМЫ}
    if not os.path.isdir(КЭШ):
        print(json.dumps({'ошибка': 'нет кэша'}, ensure_ascii=False))
        return
    for имя_ф in sorted(os.listdir(КЭШ)):
        п = os.path.join(КЭШ, имя_ф)
        try:
            if имя_ф.endswith('.gz'):
                with gzip.open(п, 'rt', encoding='utf-8', errors='replace') as f:
                    j = json.load(f)
            else:
                j = json.load(io.open(п, encoding='utf-8', errors='replace'))
        except Exception:  # noqa: BLE001
            continue
        out['файлов'] += 1
        for p in (j.get('pages') or []):
            if not isinstance(p, dict) or not p.get('html'):
                continue
            out['страниц'] += 1
            t = текст(p['html'])
            # интересуют ТОЛЬКО куски, где обычная регулярка адрес НЕ видит
            for имя, rx in ФОРМЫ:
                for m in rx.finditer(t):
                    кусок = m.group(0)
                    if EC.EMAIL_RE.search(кусок):
                        continue      # адрес и так читается, форма ни при чём
                    счёт[имя] += 1
                    компаний[имя].add(имя_ф)
                    if len(примеры[имя]) < 6:
                        примеры[имя].append(
                            t[max(0, m.start() - 30):m.end() + 20])
    out['находки'] = {имя: {'штук': счёт[имя], 'страниц_кэша': len(компаний[имя]),
                            'примеры': примеры[имя]}
                      for имя, _ in ФОРМЫ}
    print(json.dumps(out, ensure_ascii=False)[:5000])


if __name__ == '__main__':
    main()

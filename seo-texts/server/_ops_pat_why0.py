# -*- coding: utf-8 -*-
"""Почему у «своих» патентов ноль авторов: смотрим СЫРОЙ текст страницы.

Пять компаний дали «свои патенты есть, авторов 0». Ноль надо доказать или
признать дефектом разбора — берём конкретные страницы из потока и печатаем,
что там буквально написано вокруг слова «Автор».
"""
import io
import json
import os
import re
import sys

sys.path.insert(0, r'C:\sender\server')
sys.path.insert(0, r'C:\sender\_ops')
import enrich_contacts as EC     # noqa: E402

ПОТОК = r'C:\sender\_ops\pat_patents.jsonl'
цели = []
for ln in io.open(ПОТОК, encoding='utf-8', errors='replace'):
    try:
        x = json.loads(ln)
    except Exception:  # noqa: BLE001
        continue
    if x.get('свои_патенты') and not x.get('авторов'):
        for u in x['свои_патенты'][:2]:
            цели.append((x['имя'], u))
print('страниц «свои, но 0 авторов»:', len(цели))

_АВТ = re.compile(r'Автор(?:\(ы\)|ы)?\s*:\s*(.{2,900}?)\s*'
                  r'(?:Патентооблад|Заявител|Приоритет)', re.S | re.I)
_ЧЕЛ = re.compile(r'^([А-ЯЁ][а-яё\-]{2,})\s+([А-ЯЁ][а-яё]+|[А-ЯЁ]\.)\s*'
                  r'([А-ЯЁ][а-яё]+|[А-ЯЁ]\.)?$')
_ЧИСТ = re.compile(r'\((?:RU|SU|US|DE|UA|BY|KZ|FR|GB|JP|CH|IT|SE)\)|&#\d+;')

for имя, u in цели[:6]:
    try:
        h, m, _ = EC._fetch_site(u)
    except Exception as ex:  # noqa: BLE001
        print(' ', u, 'ИСКЛ', type(ex).__name__)
        continue
    t = EC._текст(h or '')
    print('=' * 15, имя, u, '| текст', len(t))
    # 1) есть ли слово «Автор» ВООБЩЕ
    поз = [mm.start() for mm in re.finditer(r'Автор', t)]
    print('   вхождений «Автор»:', len(поз))
    for p in поз[:2]:
        print('   СЫРО:', repr(t[p:p + 330]))
    # 2) срабатывает ли регулярка блока
    ma = _АВТ.search(t)
    print('   блок найден:', bool(ma))
    if ma:
        блок = _ЧИСТ.sub(' ', ma.group(1))
        print('   БЛОК:', repr(блок[:300]))
        for кус in re.split(r'[,;]| и ', блок):
            кус = re.sub(r'\s+', ' ', кус).strip(' .')
            print('     кусок %r -> %s' % (кус[:60], bool(_ЧЕЛ.match(кус))))
print('WHY0 ЗАВЕРШЕНА')

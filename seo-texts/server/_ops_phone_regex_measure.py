# -*- coding: utf-8 -*-
"""Замер новой регулярки телефонов на КЭШЕ СТРАНИЦ, а не на придуманных строках.

Проверяем два изменения разом:
  * (?<!\\d) плюс подпись-вето — сколько «телефонов» на самом деле были
    реквизитами (ОГРН/ИНН/р-с) и уходят;
  * код 3–5 цифр вместо жёстких трёх — сколько номеров региональных заводов
    («8 (3812) 39-45-67») не находились вовсе.

Считаем по НОРМАЛИЗОВАННЫМ десяти цифрам, иначе одно написание номера в двух
формах даст мнимую разницу. Ничего не пишем — только меряем.

Ещё смотрим уже накопленную таблицу phone_contacts: сколько её строк новая
регулярка НЕ считает телефоном (кандидаты в мусор) — это оценка загрязнения.
"""
import gzip
import io
import json
import os
import re
import sys

sys.path.insert(0, r'C:\sender\server')
import enrich_contacts as EC  # noqa: E402
import enrich_db as EDB       # noqa: E402

КЭШ = r'C:\seostat\drop\pagecache'
_PH_SEP_СТАР = r'[\s\-\u2010-\u2015\u2212\u00a0().]'
СТАРАЯ = re.compile(r'(?:\+7|8)' + _PH_SEP_СТАР + r'*\d{3}' + _PH_SEP_СТАР
                    + r'*\d{3}' + _PH_SEP_СТАР + r'*\d{2}' + _PH_SEP_СТАР + r'*\d{2}')


def норм(с):
    ц = re.sub(r'\D', '', с or '')
    if len(ц) == 11 and ц[0] in '78':
        ц = ц[1:]
    return ц[:10] if len(ц) >= 10 else ''


def текст(h):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ',
                  re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', h,
                         flags=re.S | re.I)))


def main():
    файлов = 0
    было_всего, стало_всего = set(), set()
    новые, ушедшие = {}, {}
    примеры_новых, примеры_ушедших = [], []
    if os.path.isdir(КЭШ):
        имена = sorted(os.listdir(КЭШ))[:1200]
        for имя in имена:
            п = os.path.join(КЭШ, имя)
            try:
                if имя.endswith('.gz'):
                    with gzip.open(п, 'rt', encoding='utf-8', errors='replace') as f:
                        j = json.load(f)
                else:
                    j = json.load(io.open(п, encoding='utf-8', errors='replace'))
            except Exception:  # noqa: BLE001
                continue
            файлов += 1
            куски = []
            if isinstance(j, dict):
                for k in ('html', 'text', 'pages'):
                    v = j.get(k)
                    if isinstance(v, str):
                        куски.append(v)
                    elif isinstance(v, list):
                        куски += [x if isinstance(x, str) else
                                  (x.get('html') or x.get('text') or '')
                                  for x in v]
            for кус in куски:
                if not кус:
                    continue
                t = текст(кус) if '<' in кус[:400] else кус
                с = {норм(x) for x in СТАРАЯ.findall(t)}
                н = {норм(m.group(0)) for m in EC.phones_in(t)}
                с.discard('')
                н.discard('')
                было_всего |= с
                стало_всего |= н
                for x in н - с:
                    новые[x] = новые.get(x, 0) + 1
                    if len(примеры_новых) < 14:
                        m = next((m for m in EC.phones_in(t)
                                  if норм(m.group(0)) == x), None)
                        if m:
                            примеры_новых.append(
                                t[max(0, m.start() - 30):m.end() + 10])
                for x in с - н:
                    ушедшие[x] = ушедшие.get(x, 0) + 1
                    if len(примеры_ушедших) < 14:
                        m = СТАРАЯ.search(t, 0)
                        while m and норм(m.group(0)) != x:
                            m = СТАРАЯ.search(t, m.end())
                        if m:
                            примеры_ушедших.append(
                                t[max(0, m.start() - 40):m.end() + 10])

    out = {'файлов_кэша': файлов,
           'номеров_старой': len(было_всего), 'номеров_новой': len(стало_всего),
           'НОВЫХ_номеров': len(новые), 'УШЛО_номеров': len(ушедшие),
           'примеры_новых': примеры_новых, 'примеры_ушедших': примеры_ушедших}

    # что новая регулярка думает про уже накопленную базу
    e = EDB.EnrichDB().cx
    строки = list(e.execute('SELECT inn, phone, source FROM phone_contacts'))
    не_телефон = [r for r in строки if not list(EC.phones_in(str(r[1] or '')))]
    out['в_базе_телефонов'] = len(строки)
    out['в_базе_не_проходят_новую'] = len(не_телефон)
    out['примеры_из_базы'] = [{'инн': r[0], 'тел': r[1], 'источник': r[2]}
                              for r in не_телефон[:14]]
    print(json.dumps(out, ensure_ascii=False)[:6500])


if __name__ == '__main__':
    main()

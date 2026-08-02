# -*- coding: utf-8 -*-
"""Были ли у нас РАБОЧИЕ ссылки на эти площадки — ответ по базе, а не по памяти.

Владелец спросил, работал ли поиск ТЭК-Торг раньше. Отвечать надо данными:
если в базе есть факты с живыми ссылками на tektorg/etpgpb/sberbank-ast, значит
формат существует и я просто выбрал неверный; если таких ссылок нет вовсе —
значит я сочинил шаблон с нуля, и «перестало работать» здесь не при чём.
"""
import sys
from collections import Counter
from urllib.parse import urlparse

sys.path.insert(0, r'C:\seostat')
from app.services import centro_catalog  # noqa: E402


def main():
    with centro_catalog.connect() as conn:
        ряды = centro_catalog._rows(
            conn, "SELECT source, source_url FROM fact "
                  "WHERE COALESCE(source_url,'') LIKE 'http%'", ())
    домены = Counter()
    примеры = {}
    for r in ряды:
        д = (urlparse(r['source_url']).netloc or '').lower()
        домены[д] += 1
        примеры.setdefault(д, (r['source'], r['source_url']))
    print(f'фактов со ссылкой: {len(ряды)}, разных доменов: {len(домены)}')
    for д, n in домены.most_common(15):
        и, у = примеры[д]
        print(f'  {n:>6}  {д:<28} [{(и or "")[:22]}]  {у[:80]}')
    интерес = [д for д in домены if any(
        к in д for к in ('tektorg', 'etpgpb', 'sberbank-ast', 'roseltorg',
                         'rts-tender'))]
    print()
    print('ссылки на торговые площадки в базе:',
          ', '.join(интерес) if интерес else 'НИ ОДНОЙ')


if __name__ == '__main__':
    main()

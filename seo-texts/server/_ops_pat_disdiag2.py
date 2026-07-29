# -*- coding: utf-8 -*-
"""Подбор рабочего размера промпта + починка URL с кириллицей."""
import re
import sys
import time
import urllib.parse

sys.path.insert(0, r'C:\sender\server')
sys.path.insert(0, r'C:\sender\_ops')
sys.argv = [sys.argv[0]]
import enrich_contacts as EC     # noqa: E402
import _ops_pat_disclosure as D  # noqa: E402

print('### A. предельный размер промпта у шлюза')
основа = ('Ниже кусок документа. Верни СТРОГО JSON {"people":[{"person":"..",'
          '"post":".."}]}\n\n')
проба = ('Совет директоров АО «Пример»: 1. Иванов Иван Иванович 2. Петров Пётр '
         'Петрович. Главный инженер — Сидоров Сидор Сидорович. ')
for цель in (2000, 4000, 6000, 8000):
    п = основа + проба * max(1, цель // len(проба))
    т0 = time.time()
    ответ, беда = D.провайдер(п, 700)
    print('  %6d симв -> %5.1fс | беда=%r | ответ=%r'
          % (len(п), time.time() - т0, беда, (ответ or '')[:90]))

print('### B. URL с кириллицей')
сыр = ('https://uralhimmash.ru/upload/aktsioneram/'
       'Отчет_об_итогах_голосования_30.06.2026_ГЗОСА_.pdf')


def квотить(u):
    """Проценты для не-ASCII в пути: без этого doc_text отдаёт ноль символов."""
    ч = urllib.parse.urlsplit(u)
    return urllib.parse.urlunsplit((
        ч.scheme, ч.netloc, urllib.parse.quote(ч.path, safe='/%'),
        urllib.parse.quote(ч.query, safe='=&%'), ч.fragment))


for u in (сыр, квотить(сыр)):
    try:
        t = EC.doc_text(u)
    except Exception as ex:  # noqa: BLE001
        print('  ИСКЛ', type(ex).__name__, str(ex)[:60])
        continue
    print('  %s -> символов %d' % ('СЫРОЙ  ' if u == сыр else 'КВОТИРО',
                                   len(t or '')))
    if t:
        print('     ', repr(re.sub(r'\s+', ' ', t)[:160]))
print('ДИСДИАГ2 ЗАВЕРШЕНА')

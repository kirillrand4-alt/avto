# -*- coding: utf-8 -*-
"""Пометить в базах номера, которые личными быть не могут. ПОМЕТИТЬ, не удалить.

ОСНОВАНИЕ. 2-я сессия проверила у себя мой счёт и согласилась: в p25.db 316 городских
номеров помечены «личный» против 136 верных, и 311 таких строк несут source их файлов.
Причину назвали обе стороны одинаково — их выкладки не несли колонки вида, и заливке
было неоткуда взять признак, она его угадывала. Свою сторону они починили с выкладки
026 и ПРОСЯТ пересчитать уже залитое.

Колонка `nomer_ne_lichnyy` заведена 1-й сессией ровно для этого случая, так что метка
кладётся в предназначенное место, а не в новое.

ПРАВИЛО РОВНО ОДНО, И ДРУГОГО НЕТ: личный мобильный после нормализации начинается на 79.
Городской личным не бывает нигде — ни на площадке, ни на сайте, ни в карточке закупки.

ЧЕГО ПРИБОР НЕ ДЕЛАЕТ. Не трогает сам номер (`value`), не удаляет строк, не меняет
`phone_type`. Номер настоящий и нужен: по городскому дозваниваются через приёмную, а с
добавочным — сразу человеку. Неверен только ярлык «личный», и правится только он.

БЕЗ --apply НИЧЕГО НЕ ПИШЕТСЯ. Сухой прогон печатает, что было бы сделано. Это не
формальность: сегодня у меня уже был случай, когда `--apply` не доехал из-за неверного
имени ключа аргументов, задание отработало «успешно» и молча не сделало ничего.
"""
import collections
import json
import re
import sqlite3
import sys

BAZY = (('p25', r'C:\seostat\data\p25.db'),
        ('centrifugal', r'C:\seostat\data\centrifugal.db'))
APPLY = '--apply' in sys.argv


def cifry(n):
    c = re.sub(r'\D', '', str(n or ''))
    if len(c) == 11 and c[0] in '78':
        return '7' + c[1:]
    if len(c) == 10 and c[0] == '9':
        return '7' + c
    return ''


itog = {}
for imya, put in BAZY:
    sch = collections.Counter()
    try:
        b = sqlite3.connect(put)
        polya = [r[1] for r in b.execute('pragma table_info(contact)')]
    except Exception as e:  # noqa: BLE001
        itog[imya] = 'база недоступна: %s' % e
        continue
    if 'nomer_ne_lichnyy' not in polya:
        # Колонку создаю только если её нет, и только её: менять чужую схему шире
        # нужного нельзя, а пометке нужно место.
        if APPLY:
            b.execute('alter table contact add column nomer_ne_lichnyy text')
            b.commit()
            polya.append('nomer_ne_lichnyy')
            sch['колонка nomer_ne_lichnyy создана'] += 1
        else:
            sch['колонки nomer_ne_lichnyy нет, будет создана'] += 1

    k_vid = [x for x in polya if re.search(r'phone_type|\bkind\b|\btip\b|vid', x, re.I)]
    pometit = []
    for r in b.execute('select id, value, %s from contact'
                       % ','.join(k_vid + (['nomer_ne_lichnyy']
                                           if 'nomer_ne_lichnyy' in polya else []))):
        cid, val = r[0], r[1]
        ost = dict(zip(k_vid + (['nomer_ne_lichnyy'] if 'nomer_ne_lichnyy' in polya
                                else []), r[2:]))
        vid = ' '.join(str(ost.get(k) or '') for k in k_vid)
        if not re.search(r'личн|мобильн|сотов', vid, re.I):
            sch['метки «личный» нет — не трогаю'] += 1
            continue
        c = cifry(val)
        if c.startswith('79'):
            sch['верно: мобильный'] += 1
            continue
        if (ost.get('nomer_ne_lichnyy') or '').strip():
            sch['уже помечен ранее'] += 1
            continue
        pometit.append((cid, c or re.sub(r'\D', '', str(val or '')), vid.strip()))

    if APPLY and pometit:
        b.executemany(
            'update contact set nomer_ne_lichnyy = ? where id = ?',
            [('да: не начинается на 79 — личным мобильным быть не может', cid)
             for cid, _c, _v in pometit])
        b.commit()
        sch['ПОМЕЧЕНО'] += len(pometit)
    else:
        sch['БУДЕТ ПОМЕЧЕНО (сухой прогон)'] += len(pometit)

    print('--- %s' % imya)
    for cid, c, vid in pometit[:6]:
        print('    id %-8s %-13s вид: %s' % (cid, c or '—', vid[:40]))
    for k, v in sch.most_common():
        print('    REC %s\t%d' % (k, v))
    itog[imya] = {k: v for k, v in sch.items()}

print('ИТОГ ' + json.dumps({'режим': 'запись' if APPLY else 'сухой прогон',
                            'по базам': itog}, ensure_ascii=False))

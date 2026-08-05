# -*- coding: utf-8 -*-
"""У кого метка «личный» стоит на ГОРОДСКОМ номере. Проверить всех, начиная с себя.

2-я сессия заметила: если «личный» ставится городскому, главная мера ТЗ завышается, и
увидим мы это только на обзвоне. Они написали 1-й сессии, что это её сторона.

Вопрос «чья ошибка» решается не перепиской, а счётом по файлам. Правило простое и
общее: личный мобильный в России начинается на 79 после нормализации. Номер 7-495-…
это московский городской, и меткой «личный» он быть не может ни у кого из нас.

Считаю по ВСЕМ выкладкам на дропе, раскладывая по автору (по имени файла: 1S, 2S, 3S),
и своё считаю первым. Если ошибка моя — это надо увидеть раньше, чем указывать на чужую.
"""
import collections
import csv
import glob
import json
import os
import re

D = r'C:\seostat\drop\drop-storage'
csv.field_size_limit(10 ** 8)

KOL_NOMERA = ('telefon', 'znachenie', 'nomer', 'LICHNYY_MOBILNYY', 'telefon_ciframi',
              'mobilnyy', 'telefon_kak_napisan', 'telefony')
# Колонки, в которых может стоять ярлык вида номера.
KOL_VIDA = ('vid', 'tip', 'vid_nomera', 'kakoy_nomer', 'priznak')
LICHNYY_YARLYK = re.compile(r'личн|мобильн|сотов', re.I)
NE_LICHNYY_YARLYK = re.compile(r'не\s+личн|общий|линия|городск|коммутатор|приёмн|приемн', re.I)


def cifry(n):
    c = re.sub(r'\D', '', str(n or ''))
    if len(c) == 11 and c[0] in '78':
        return '7' + c[1:]
    if len(c) == 10 and c[0] == '9':
        return '7' + c
    return ''


def chey(imya):
    u = imya.upper()
    for metka in ('1S', '1-S', 'OT-1'):
        if metka in u:
            return '1-я сессия'
    for metka in ('2S', '2-S', 'OT-2'):
        if metka in u:
            return '2-я сессия'
    for metka in ('3S', '3-S', 'OT-3'):
        if metka in u:
            return '3-я сессия (моё)'
    return 'без пометки автора'


sch = collections.Counter()
primery = collections.defaultdict(list)
for p in sorted(glob.glob(os.path.join(D, '*.csv'))):
    avtor = chey(os.path.basename(p))
    try:
        with open(p, encoding='utf-8-sig', newline='') as f:
            rd = csv.DictReader(f, delimiter=';')
            polya = rd.fieldnames or []
            kn = [x for x in polya if x and x.strip() in KOL_NOMERA]
            kv = [x for x in polya if x and x.strip() in KOL_VIDA]
            # Колонка, ИМЯ которой само утверждает «личный мобильный», — тоже ярлык.
            kn_lichnye = [x for x in kn if LICHNYY_YARLYK.search(x)]
            if not kn:
                continue
            for r in rd:
                for k in kn:
                    c = cifry(r.get(k))
                    if not c:
                        continue
                    vid = ' '.join(str(r.get(x) or '') for x in kv)
                    # Ярлык «личный» либо в колонке вида, либо в САМОМ ИМЕНИ колонки.
                    yarlyk = (LICHNYY_YARLYK.search(vid) and not NE_LICHNYY_YARLYK.search(vid)) \
                        or (k in kn_lichnye)
                    if not yarlyk:
                        continue
                    if c.startswith('79'):
                        sch[avtor + ' | верно: мобильный помечен личным'] += 1
                    else:
                        sch[avtor + ' | ОШИБКА: ГОРОДСКОЙ помечен личным'] += 1
                        if len(primery[avtor]) < 6:
                            primery[avtor].append(
                                (os.path.basename(p), c, (r.get('chelovek') or
                                                          r.get('fio') or '')[:26],
                                 (vid or ('колонка ' + k))[:40]))
    except Exception:  # noqa: BLE001
        continue

for avtor, sp in primery.items():
    print('--- %s' % avtor)
    for f, c, kto, vid in sp:
        print('   %-44s %-12s %-26s %s' % (f[:44], c, kto, vid))
for k, v in sorted(sch.items()):
    print('REC %s\t%d' % (k, v))
print('ИТОГ ' + json.dumps({
    'ошибок всего': sum(v for k, v in sch.items() if 'ОШИБКА' in k),
    'по авторам': {k.split(' | ')[0]: v for k, v in sch.items() if 'ОШИБКА' in k},
}, ensure_ascii=False))

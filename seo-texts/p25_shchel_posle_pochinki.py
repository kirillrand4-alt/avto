# -*- coding: utf-8 -*-
"""Сколько щелей закрыл починенный шаблон и что осталось провайдеру.

Порядок работ, который считаю правильным: сперва починить ДЕШЁВЫЙ прибор, потом
тратить платный. Шаблон телефона теперь берёт пятизначные коды городов; надо измерить,
сколько из 1 644 непрочитанных карточек он закрыл сам, и только остаток нести
провайдеру. Иначе провайдер будет читать то, что регулярка и так прочла бы, а квота
у него общая и её велено беречь.
"""
import collections
import importlib.util
import json
import os
import re
import sys

sys.path.insert(0, r'C:\sender\_ops')
spec = importlib.util.spec_from_file_location('tel', r'C:\sender\_ops\3s_p25_telefon_shablon.py')
TEL = importlib.util.module_from_spec(spec)
spec.loader.exec_module(TEL)

VHOD = r'C:\sender\_ops\3s_karty_dlya_provaydera.jsonl'
VYHOD = r'C:\sender\_ops\3s_karty_ostatok_provaydery.jsonl'

FIO_POLNOE = re.compile(r'\b[А-ЯЁ][а-яё]{2,}\s+[А-ЯЁ][а-яё]{2,}\s+'
                        r'[А-ЯЁ][а-яё]{2,}(?:ович|евич|ьевич|овна|евна|ьевна|ична)\b')
FIO_PARA = re.compile(r'\b[А-ЯЁ][а-яё]{3,}\s+[А-ЯЁ][а-яё]{2,}\b')

sch = collections.Counter()
ostatok = []
vernulos = []
for ln in open(VHOD, encoding='utf-8'):
    try:
        z = json.loads(ln)
    except Exception:  # noqa: BLE001
        continue
    t = z.get('tekst') or ''
    n = TEL.nomera(t)
    silnye = [x for x in n if x['vid'] == 'номер']
    est_fio = bool(FIO_POLNOE.search(t) or FIO_PARA.search(t))
    if silnye and est_fio:
        sch['ЗАКРЫТО ПОЧИНЕННЫМ ШАБЛОНОМ: есть номер и человек'] += 1
        vernulos.append((z.get('company', ''), silnye[0]['kak_napisan'], silnye[0]['cifry']))
        continue
    if silnye and not est_fio:
        sch['номер вернулся, человека всё равно нет'] += 1
    elif est_fio and not silnye:
        sch['человек есть, номера нет и после починки'] += 1
    else:
        sch['ни номера, ни человека и после починки'] += 1
    z['nomera_posle_pochinki'] = [x['kak_napisan'] for x in n[:4]]
    ostatok.append(z)

with open(VYHOD, 'w', encoding='utf-8') as f:
    for z in ostatok:
        f.write(json.dumps(z, ensure_ascii=False) + '\n')

print('вернулось починкой (примеры):')
for c, kak, cif in vernulos[:10]:
    print('   %-30s %-22s -> %s' % (c[:30], kak, cif))
for k, v in sch.most_common():
    print('REC %s\t%d' % (k, v))
print('ИТОГ ' + json.dumps({
    'было в щели': len(ostatok) + len(vernulos),
    'ЗАКРЫЛА ПОЧИНКА ШАБЛОНА': len(vernulos),
    'ОСТАЛОСЬ ПРОВАЙДЕРУ': len(ostatok),
    'знаков к провайдеру': sum(z['znakov'] for z in ostatok),
    'файл': os.path.basename(VYHOD)}, ensure_ascii=False))

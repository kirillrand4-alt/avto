# -*- coding: utf-8 -*-
"""Где именно регулярка молчит на 9 335 карточках. Замер перед тем, как звать провайдера.

ПРАВИЛО ВЛАДЕЛЬЦА: всю тяжёлую работу — через провайдерский API. Я его за смену не
позвала ни разу и разобрала весь корпус карточек регуляркой. Регулярка дёшева и там,
где вёрстка обычная, работает; но где заказчик написал контакты по-своему, она молчит —
и молчит БЕЗ ПРИЗНАКА, то есть выглядит как «контактов нет».

Прежде чем тратить квоту провайдера, надо знать РАЗМЕР ЩЕЛИ: сколько карточек несут
явные признаки контакта (цифры, похожие на номер; слова «тел», «моб», «обращаться»),
но мой разбор из них ничего не достал. Провайдера звать только туда — это и дешевле,
и честнее: там его чтение действительно добавляет, а не повторяет регулярку.
"""
import collections
import csv
import json
import os
import re

KART = r'C:\seostat\drop\drop-storage\tp-kartochki-polnye.csv'
VYHOD = r'C:\sender\_ops\3s_karty_dlya_provaydera.jsonl'
csv.field_size_limit(10 ** 8)

TEL = re.compile(r'(?:\+7|\b8)[\s\-(]*(\d{3,4})[\s\-)]*\d{2,3}[\s\-]*\d{2}[\s\-]*\d{2}\b')
FIO_POLNOE = re.compile(r'\b[А-ЯЁ][а-яё]{2,}\s+[А-ЯЁ][а-яё]{2,}\s+'
                        r'[А-ЯЁ][а-яё]{2,}(?:ович|евич|ьевич|овна|евна|ьевна|ична)\b')
FIO_PARA = re.compile(r'\b[А-ЯЁ][а-яё]{3,}\s+[А-ЯЁ][а-яё]{2,}\b')
# Признаки того, что контакт в тексте ЕСТЬ, даже если мой разбор его не взял.
PRIZNAK_KONTAKTA = re.compile(
    r'\bтел\b|\bт\.\s*\d|моб\w*|сот\w*|обращат|звонит|контакт|доб\.|вн\.\s*\d|'
    r'@[\w.\-]+\.[a-z]{2,}|\d{3}[\s\-]\d{2}[\s\-]\d{2}', re.I)
# Цифры, похожие на номер, но не пойманные шаблоном: другое разбиение, скобки, пробелы.
CIFRY_KAK_NOMER = re.compile(r'(?:\D|^)(\d[\d\s\-()]{8,16}\d)(?:\D|$)')

sch = collections.Counter()
dlya_provaydera = []
with open(KART, encoding='utf-8-sig', newline='') as f:
    for r in csv.DictReader(f, delimiter=';'):
        t = re.sub(r'\s+', ' ', r.get('comment') or '')
        if not t:
            sch['карточка без текста'] += 1
            continue
        est_tel = bool(TEL.search(t))
        est_fio = bool(FIO_POLNOE.search(t) or FIO_PARA.search(t))
        priznak = bool(PRIZNAK_KONTAKTA.search(t))
        # Цифры, которые ВЫГЛЯДЯТ номером, но шаблон их не взял, — прямая улика молчания.
        syrye = [m.group(1) for m in CIFRY_KAK_NOMER.finditer(t)
                 if 10 <= len(re.sub(r'\D', '', m.group(1))) <= 11]
        ne_vzyatye = [c for c in syrye if not TEL.search(c)]

        if est_tel and est_fio:
            sch['разобрано регуляркой: и номер, и человек'] += 1
            continue
        if not priznak and not syrye:
            sch['контакта в тексте нет вовсе — провайдер не поможет'] += 1
            continue
        # Дальше — щель. Называю её вид, чтобы видеть, чего именно не хватает.
        if est_tel and not est_fio:
            vid = 'номер есть, человека регулярка не взяла'
        elif est_fio and not est_tel:
            vid = 'человек есть, номера регулярка не взяла'
        elif ne_vzyatye:
            vid = 'цифры выглядят номером, шаблон их не взял'
        else:
            vid = 'признак контакта есть, разбор пуст'
        sch['ЩЕЛЬ: ' + vid] += 1
        dlya_provaydera.append({
            'tender_id': r.get('tender_id', ''), 'company_id': r.get('company_id', ''),
            'company': r.get('company', ''), 'vid_shcheli': vid,
            'ne_vzyatye_cifry': ne_vzyatye[:4],
            'znakov': len(t), 'tekst': t[:9000]})

with open(VYHOD, 'w', encoding='utf-8') as f:
    for z in dlya_provaydera:
        f.write(json.dumps(z, ensure_ascii=False) + '\n')

print('примеры щелей:')
for z in dlya_provaydera[:6]:
    print('  [%s] %-28s %s' % (z['tender_id'], z['company'][:28], z['vid_shcheli']))
    print('      %s' % z['tekst'][:170])
for k, v in sch.most_common():
    print('REC %s\t%d' % (k, v))
print('ИТОГ ' + json.dumps({
    'карточек к провайдеру': len(dlya_provaydera),
    'знаков всего': sum(z['znakov'] for z in dlya_provaydera),
    'файл': os.path.basename(VYHOD)}, ensure_ascii=False))

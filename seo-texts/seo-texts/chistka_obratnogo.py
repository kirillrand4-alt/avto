# -*- coding: utf-8 -*-
"""Чистка находок обратного хода по правилам ПЕРВОЙ сессии.

Они прогнали свой обратный ход и написали: на первых 25 записях мусора было 64%. Правила
назвали словами, скрипта на дропе нет — реализую по описанию и возвращаю им числа, чтобы
сравнение было предметным, а не «у нас тоже чисто».

ПРАВИЛА ПЕРВОЙ СЕССИИ (их формулировки):
  1. агрегаторы по пути адреса — страница-агрегатор даёт номер не предприятия, а свой;
  2. список фамилий рядом — если возле контакта перечислено много людей, он ничей;
  3. 8-800 — это линия, а не человек;
  4. имя завода в той же окрестности — номер общий, заводской, а не личный;
  5. «номер на двух и более людях либо ИНН личным не бывает».

Ничего не удаляю: ставлю причину в поле `musor`. Правило владельца «разделять, а не
отсеивать» сильнее чужого правила чистки — их цель отличить личный от общего, а не выкинуть.
"""
import json, re, sys, collections

VHOD = 'lpr-obratnyy.jsonl'
AGREGATOR = re.compile(
    r'(rusprofile|checko|list-org|sbis|zachestnyibiznes|audit-it|synapsenet|kartoteka|'
    r'sparkinterfax|seldon|tenderland|bicotender|allbiz|yell|zoon|orgpage|spravka|'
    r'organizacii|kompaniya|catalog|katalog|2gis|flamp|otzyv)', re.I)
LINIYA = re.compile(r'\b8[\s\-(]*800\b|\b800[\s\-)]*\d{3}')
FAMILIYA = re.compile(r'\b[А-ЯЁ][а-яё\-]{3,}\s+[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]*'
                      r'(?:ович|евич|ьевич|овна|евна|ьевна|ична|инична)\b')


def cifry(s):
    d = re.sub(r'\D', '', s or '')
    return d[-10:] if len(d) >= 10 else ''


rows = [json.loads(l) for l in open(VHOD, encoding='utf-8') if l.strip()]
# кто ещё сидит на этом номере — по всему файлу, а не в пределах записи
po_nomeru = collections.defaultdict(set)
po_inn = collections.defaultdict(set)
for r in rows:
    for k in r.get('kontakty') or []:
        n = cifry(k['znachenie'])
        if n:
            po_nomeru[n].add(r['fio'])
            po_inn[n].add(r['inn'])

sch = collections.Counter()
for r in rows:
    imya_zavoda = [w.lower() for w in re.findall(r'[А-ЯЁа-яё]{5,}', r['predpriyatie'])][:2]
    for k in r.get('kontakty') or []:
        prichiny = []
        n = cifry(k['znachenie'])
        ss = k.get('ssylka') or ''
        cit = k.get('citata') or ''
        if AGREGATOR.search(ss):
            prichiny.append('страница-агрегатор, номер не предприятия')
        if k['tip'] == 'телефон' and LINIYA.search(k['znachenie']):
            prichiny.append('линия 8-800, не человек')
        if len(FAMILIYA.findall(cit)) >= 3:
            prichiny.append(f'рядом перечислено {len(FAMILIYA.findall(cit))} человек — номер ничей')
        if imya_zavoda and any(w in cit.lower() for w in imya_zavoda) and n and not n.startswith('9'):
            prichiny.append('имя завода в той же окрестности — номер общий')
        if n and len(po_nomeru[n]) > 1:
            prichiny.append(f'номер числится за {len(po_nomeru[n])} людьми')
        if n and len(po_inn[n]) > 1:
            prichiny.append(f'номер стоит у {len(po_inn[n])} предприятий')
        k['musor'] = ' | '.join(prichiny)
        sch['грязных' if prichiny else 'чистых'] += 1
        for p in prichiny:
            sch[p.split(',')[0].split(' —')[0][:44]] += 1

with open(VHOD, 'w', encoding='utf-8') as f:
    for r in rows:
        f.write(json.dumps(r, ensure_ascii=False) + '\n')
vsego = sch['чистых'] + sch['грязных']
print(f'контактов {vsego}: чистых {sch["чистых"]}, помечено мусором {sch["грязных"]} '
      f'({round(100*sch["грязных"]/max(1,vsego))}%)', file=sys.stderr)
for k, v in sch.most_common():
    if k not in ('чистых', 'грязных'):
        print(f'  {v:>5}  {k}', file=sys.stderr)

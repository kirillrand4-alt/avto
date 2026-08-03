# -*- coding: utf-8 -*-
"""Применить вердикты суда к находкам обратного хода.

Судья (`proverka_chey_nomer.py`, дешёвая модель) для каждого контакта сказал, чей он.
Здесь вердикт ложится в сами записи, чтобы свод его видел.

НИЧЕГО НЕ УДАЛЯЕТСЯ, и это принципиально: «чужой» вердикт не значит, что контакт плохой —
он значит, что контакт принадлежит ДРУГОМУ названному человеку. Такой контакт переносится
на того человека, а не выбрасывается: номер живой, просто хозяин другой.
"""
import json, os, sys

SUD = 'sud-chey-nomer.jsonl'
VHOD = 'lpr-obratnyy.jsonl'
verdikt = {}
for ln in open(SUD, encoding='utf-8'):
    if not ln.strip():
        continue
    z = json.loads(ln)
    verdikt[(z['inn'], z['nash'], z['kontakt'])] = z

rows = [json.loads(l) for l in open(VHOD, encoding='utf-8') if l.strip()]
sch = {'nash': 0, 'chuzhoy': 0, 'ne_vidno': 0, 'ne_sudili': 0, 'perenesno': 0}
for r in rows:
    for k in r.get('kontakty') or []:
        v = verdikt.get((r['inn'], r['fio'], k['znachenie']))
        if not v or not v.get('sud'):
            k['sud'] = ''
            sch['ne_sudili'] += 1
            continue
        s = v['sud']
        k['sud_pochemu'] = v.get('pochemu', '')
        if s.lower() == 'не видно':
            k['sud'] = 'не видно'
            k['uverennost'] = 'спорная'
            sch['ne_vidno'] += 1
        elif s == r['fio']:
            k['sud'] = 'наш'
            k['uverennost'] = 'высокая'
            sch['nash'] += 1
        else:
            k['sud'] = f'принадлежит другому: {s}'
            k['uverennost'] = 'чужой'
            k['nastoyashchiy_hozyain'] = s
            sch['chuzhoy'] += 1

with open(VHOD, 'w', encoding='utf-8') as f:
    for r in rows:
        f.write(json.dumps(r, ensure_ascii=False) + '\n')
print(f'вердикты применены: {sch}', file=sys.stderr)
kont = [k for r in rows for k in (r.get('kontakty') or [])]
print(f'контактов всего {len(kont)} | подтверждённых судом «наш» {sch["nash"]} | '
      f'отданных другому {sch["chuzhoy"]} | нерешённых {sch["ne_vidno"] + sch["ne_sudili"]}',
      file=sys.stderr)

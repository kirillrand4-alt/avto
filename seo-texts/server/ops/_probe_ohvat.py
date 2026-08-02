# -*- coding: utf-8 -*-
"""Сколько предприятий с воздушным центробежным компрессором реально в базе.

Сборщик берёт список предприятий ТОЛЬКО из `OCHERED-centrobezhnye.csv` и
молча отбрасывает человека, чьего ИНН там нет (`if инн not in предпр:
return`). Так уже потерялись 11 технических ЛПР, найденных обходом. Надо
знать: очередь — это все предприятия с фактом «центробежная + воздух» или
её подмножество.
"""
import csv
import io
import json
import os

ДРОП = r'C:\seostat\drop\drop-storage'
csv.field_size_limit(10 ** 7)


def читать(имя):
    п = os.path.join(ДРОП, имя)
    if not os.path.exists(п):
        return []
    return list(csv.DictReader(io.StringIO(
        open(п, encoding='utf-8-sig', errors='replace').read()), delimiter=';'))


def чист_тип(t):
    return any(x.strip().startswith('центробежн') and 'насос' not in x
               for x in (t or '').split('|'))


очередь = {(r.get('inn') or '').strip() for r in читать('OCHERED-centrobezhnye.csv')}
очередь.discard('')

свод = читать('SVODNAYA-centrobezhnye.csv')
факт = {(r.get('inn') or '').strip() for r in свод
        if чист_тип(r.get('tip_mashiny')) and r.get('sreda') == 'воздух'}
факт.discard('')

без = {(r.get('inn') or '').strip() for r in читать('BEZ-TEHLPR-1486.csv')}
без.discard('')

база = {(r.get('inn') or '').strip()
        for r in читать('BAZA-CENTROBEZHNIKI-OBSHCHAYA.csv')}
база.discard('')

print(json.dumps({
    'в_очереди_OCHERED': len(очередь),
    'с_фактом_центробежная_воздух_в_SVODNAYA': len(факт),
    'факт_но_НЕ_в_очереди': len(факт - очередь),
    'очередь_но_без_факта': len(очередь - факт),
    'в_списке_без_техЛПР': len(без),
    'без_техЛПР_но_НЕ_в_очереди': len(без - очередь),
    'в_итоговой_базе': len(база),
    'факт_но_НЕ_в_базе': len(факт - база),
    'примеры_факт_вне_очереди': sorted(факт - очередь)[:10],
}, ensure_ascii=False))

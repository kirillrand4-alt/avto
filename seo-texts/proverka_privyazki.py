# -*- coding: utf-8 -*-
"""Чужая привязка: человек назван вместе со СВОИМ предприятием, а я приписала его нашему.

НАШЁЛ ВЛАДЕЛЕЦ, случай дословный:
    запрос был по «Сегежский целлюлозно-бумажный комбинат»
    в цитате: «Латышкевич Александр Марьянович, главный механик «РУСАЛ Надвоицы» … Доклад о
              взаимодействии АО «Сегежский ЦБК» с ГАПОУ РК …»
То есть страница — программа конференции, где перечислены люди РАЗНЫХ предприятий, и наше
название на ней тоже есть. Мой разбор взял имя и приписал его нашему ИНН, потому что имя и
название встретились на одной странице.

ЭТО ТА ЖЕ ОШИБКА, ЧТО Я УЖЕ ЧИНИЛА ДЛЯ ТЕЛЕФОНОВ, И НЕ ПОЧИНИЛА ДЛЯ ПРИВЯЗКИ. Для контактов я
записала правило: близость номера к фамилии не доказывает, что номер её. Для предприятия то же
самое: соседство имени с названием на странице не доказывает, что человек оттуда. Разница лишь
в том, что у телефона я это заметила, а у привязки — нет.

ПРИЗНАК ЧУЖОГО, который здесь считается: сразу ПОСЛЕ имени (в окне 120 знаков) названо
предприятие в кавычках или с формой собственности, и оно НЕ наше. Тогда человек принадлежит
ему, а не нам — так пишут всегда: «Иванов И.И., главный инженер «Такого-то завода»».
"""
import collections
import json
import re
import sys

VHOD = sys.argv[1] if len(sys.argv) > 1 else 'lpr-pesochnica.jsonl'
# Название предприятия в тексте: в кавычках либо с формой собственности перед кавычками.
FIRMA = re.compile(r'(?:АО|ОАО|ПАО|ЗАО|ООО|ГУП|МУП|ФГУП|НАО)\s*[«"]([^»"]{3,60})[»"]'
                   r'|[«"]([^»"]{3,60})[»"]')


def slova(s):
    return {w.lower() for w in re.split(r'[^А-Яа-яЁёA-Za-z0-9]+', s or '') if len(w) > 4}


def chuzhaya_firma(citata, imya, nashe):
    """Первое предприятие, названное сразу после имени, если оно не наше."""
    i = citata.find(imya[:24]) if imya else -1
    if i < 0:
        return ''
    okno = citata[i:i + 120]
    nash_sl = slova(nashe)
    for m in FIRMA.finditer(okno):
        naz = (m.group(1) or m.group(2) or '').strip()
        if not naz or len(naz) < 4:
            continue
        if slova(naz) & nash_sl:
            return ''          # названо наше — привязка верна
        return naz
    return ''


sch = collections.Counter()
primery = []
for ln in open(VHOD, encoding='utf-8'):
    if not ln.strip():
        continue
    z = json.loads(ln)
    nashe = z.get('predpriyatie') or ''
    for ch in (z.get('lyudi') or []):
        sch['людей всего'] += 1
        c = ch.get('citata') or ''
        if not c:
            sch['без цитаты — судить не по чему'] += 1
            continue
        chuzh = chuzhaya_firma(c, ch.get('fio') or '', nashe)
        if chuzh:
            sch['ЧУЖАЯ ПРИВЯЗКА: рядом с именем названо другое предприятие'] += 1
            if len(primery) < 8:
                primery.append({'nash_inn': z.get('inn'), 'nashe': nashe[:50],
                                'imya': (ch.get('fio') or '')[:40],
                                'ego_firma': chuzh[:40], 'citata': c[:160]})
        else:
            sch['привязка не опровергнута'] += 1
print(json.dumps({'счёт': dict(sch), 'примеры': primery}, ensure_ascii=False, indent=1))

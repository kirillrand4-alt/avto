# -*- coding: utf-8 -*-
r"""Пересчёт замера №1 по СОХРАНЁННЫМ окнам: что дал патч _фио.

Окна лежат в потоке ровно в том виде, в каком их режет боевая функция
(«Контактн\w+ лиц\w+ ...» + 260 символов), поэтому повтор сборки контакта по
ним точен до знака и не требует повторного обхода агрегаторов.

Считаем ДВЕ колонки: старым _фио (обрезал фамилию) и текущим боевым.
"""
import io
import json
import os
import re
import sys
import traceback

sys.path.insert(0, r'C:\sender\server')
import enrich_contacts as EC  # noqa: E402

ПОТОК = r'C:\seostat\drop\re_agg_stream.jsonl'


def p(*a):
    print(*a)
    sys.stdout.flush()


def фио_старый(текст):
    """Точная копия _фио ДО патча — для честной колонки «было»."""
    for rx in (EC._ФИО_ПОЛН, EC._ФИО_ИНИЦ):
        for m in rx.finditer(текст or ''):
            к = m.group(1).strip()
            if EC._FIO_STOP.search(к) or EC._НЕ_ИМЯ.search(к):
                continue
            сл = к.split()
            if any(EC._ОТЧЕСТВО.search(w) for w in сл):
                return к
            if len(сл) == 3:
                к = ' '.join(сл[-2:])
                сл = сл[-2:]
            if len(сл) >= 2 and '.' in сл[-1]:
                return к
    return ''


def контакты(окна, фн):
    """Сборка контактов ровно как в find_tender_aggregator_contacts."""
    из = []
    for окно in окна:
        фио = фн(окно)
        письма = [x.lower() for x in EC.EMAIL_RE.findall(окно)
                  if not EC._is_junk_email(x)
                  and not any(a.split('.')[0] in x.lower()
                              for a in EC._АГРЕГАТОРЫ_ТЕНДЕР)]
        тм = next(EC.phones_in(окно), None)
        if not (фио or письма):
            continue
        из.append({'person': фио, 'email': (письма[0] if письма else ''),
                   'phone': (тм.group(0).strip() if тм else '')})
        if len(из) >= 6:
            break
    свод = {}
    for x in из:
        свод[(x['person'], x['email'])] = x
    return list(свод.values())


def счёт(д, фн):
    в = {'компаний': 0, 'с_контактом': 0, 'контактов': 0, 'фио': 0,
         'почт': 0, 'телефонов': 0, 'фио_без_фамилии': 0}
    прим = []
    for j in д:
        в['компаний'] += 1
        к = контакты(j.get('окна') or [], фн)
        if к:
            в['с_контактом'] += 1
        в['контактов'] += len(к)
        for c in к:
            if c.get('person'):
                в['фио'] += 1
                # «Б. Б.» / «Е. А.» — одни инициалы, фамилии нет
                if not re.search(r'[А-ЯЁ][а-яё]{2,}', c['person']):
                    в['фио_без_фамилии'] += 1
            if c.get('email'):
                в['почт'] += 1
            if c.get('phone'):
                в['телефонов'] += 1
            прим.append(dict(c, inn=j.get('inn'), name=(j.get('name') or '')[:46]))
    return в, прим


def main():
    д = []
    for ln in io.open(ПОТОК, encoding='utf-8', errors='replace'):
        try:
            д.append(json.loads(ln))
        except Exception:  # noqa: BLE001
            continue
    сб, пб = счёт(д, фио_старый)
    сн, пн = счёт(д, EC._фио)
    p('БЫЛО(старый _фио) ' + json.dumps(сб, ensure_ascii=False))
    p('СТАЛО(патч _фио)  ' + json.dumps(сн, ensure_ascii=False))
    # что именно изменилось
    кб = {(x['inn'], x['email'], x['phone']): x['person'] for x in пб}
    for x in пн:
        к = (x['inn'], x['email'], x['phone'])
        if кб.get(к) != x['person']:
            p('ИЗМЕНИЛОСЬ inn=%s было=%r стало=%r почта=%s тел=%s'
              % (x['inn'], кб.get(к), x['person'], x['email'], x['phone']))
    for x in пн:
        p('КОНТАКТ ' + json.dumps(x, ensure_ascii=False)[:250])
    p('ИТОГ компаний=%d с_контактом=%d контактов=%d фио=%d почт=%d телефонов=%d'
      % (сн['компаний'], сн['с_контактом'], сн['контактов'], сн['фио'],
         сн['почт'], сн['телефонов']))


if __name__ == '__main__':
    try:
        main()
    except Exception:  # noqa: BLE001
        p('ФАТАЛЬНО:', traceback.format_exc()[-800:])

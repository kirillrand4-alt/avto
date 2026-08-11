# -*- coding: utf-8 -*-
"""ВЕЕР ЛИНЗ ПО ТУПИКУ: 2 040 карточек ЕИС, где мой разбор сказал «нет ни одной подписи о
контактах». Правило владельца: в тупике идти к провайдеру НЕСКОЛЬКИМИ разными углами
разбора одного материала, а не одним запросом.

Материал: 20 живых текстов карточек (`PARK-EIS-KARTOCHKI-TEKST-3S.jsonl`), у 19 из которых
мой парсер не нашёл НИ ОДНОЙ подписи.

Три линзы, каждая спрашивает своё:
   1. ПРЯМАЯ    — есть ли на странице человек, телефон, почта; выписать дословно.
   2. ОБРАТНАЯ  — доказать, что контактов НЕТ; назвать, что стоит на их месте.
   3. СТРОЕНИЕ  — какие вообще разделы на странице и в каком из них по закону обязаны
                  стоять контакты.

Зачем три: если прямая линза найдёт контакт, а обратная его же не заметит — верить нельзя
ни одной, и это будет видно сразу. Совпадение двух линз из трёх — вот что считается ответом.

ОТРИЦАТЕЛЬНЫЙ КОНТРОЛЬ: к пачке подмешивается выдуманный текст без единого контакта. Если
линза «найдёт» в нём человека с телефоном — она сочиняет, и числам прогона верить нельзя.

Числа в КОНЦЕ.
"""
import collections
import io
import json
import os
import re
import sys

sys.path.insert(0, '/home/user/avto/seo-texts')
import gen_provider as G  # noqa: E402

SCRATCH = os.environ.get('P25_SCRATCH', '.')
VHOD = os.path.join(SCRATCH, 'PARK-EIS-KARTOCHKI-TEKST-3S.jsonl')
VYHOD = os.path.join(SCRATCH, 'PARK-EIS-LINZY-3S.jsonl')
KONTROL_TEKST = ('Единая информационная система в сфере закупок. Раздел справки. '
                 'Здесь размещаются нормативные документы и инструкции пользователя. '
                 'Версия системы 12.3. Никаких сведений об организациях на этой странице нет.')
LINZY = [
    ('прямая', 'Ниже — текст страницы из ЕИС. Найди КОНТАКТЫ организации: фамилию и имя '
               'должностного лица, телефон, адрес электронной почты. Выписывай ДОСЛОВНО то, '
               'что видишь; ничего не придумывай. Если контактов нет — так и скажи.'),
    ('обратная', 'Ниже — текст страницы из ЕИС. Твоя задача — ДОКАЗАТЬ, что контактных '
                 'сведений (человек, телефон, почта) на ней НЕТ. Если доказать не удаётся, '
                 'потому что контакты там всё-таки есть — выпиши их дословно и признай это.'),
    ('строение', 'Ниже — текст страницы из ЕИС. Перечисли, какие РАЗДЕЛЫ на ней есть, и '
                 'скажи, в каком из разделов по закону 223-ФЗ обязаны стоять контактные '
                 'сведения заказчика. Если такого раздела на странице нет — скажи прямо.'),
]
SHEMA = ('Ответь ТОЛЬКО JSON: {"chelovek": "ФИО или пустая строка", '
         '"telefon": "номер или пустая строка", "pochta": "почта или пустая строка", '
         '"est_kontakty": true/false, "pochemu": "коротко, по какому месту текста решил"}')


def tekst_otveta(msg):
    if isinstance(msg, str):
        return msg
    try:
        return ''.join(b.text for b in msg.content if b.type == 'text').strip()
    except Exception:  # noqa: BLE001
        return ''


def obyekt(t):
    i = t.find('{')
    while i >= 0:
        for j in range(len(t), i, -1):
            if t[j - 1] != '}':
                continue
            try:
                return json.loads(t[i:j])
            except Exception:  # noqa: BLE001
                break
        i = t.find('{', i + 1)
    return {}


kartochki = []
for s in io.open(VHOD, encoding='utf-8'):
    try:
        kartochki.append(json.loads(s))
    except Exception:  # noqa: BLE001
        continue
kartochki = kartochki[:int(os.environ.get('P25_SKOLKO', '8'))]
kartochki.append({'inn': 'КОНТРОЛЬ', 'predpriyatie': 'выдуманная страница без контактов',
                  'tekst': KONTROL_TEKST, 'podpisi_moi': [], 'ssylka': ''})
print('карточек на разбор: %d (последняя — отрицательный контроль)' % len(kartochki))

klient = G.make_client()
sch = collections.Counter()
itog = []
for k in kartochki:
    otvety = {}
    for imya, vopros in LINZY:
        try:
            msg = G.call(klient, [{'role': 'user',
                                   'content': '%s\n\n%s\n\nТЕКСТ СТРАНИЦЫ:\n%s'
                                              % (vopros, SHEMA, k['tekst'][:7000])}],
                         # ПОДПИСЬ ВЫЗОВА — ИЗ КОДА, А НЕ ПО ПАМЯТИ. Первый заход упал 27 раз
                         # подряд на `call() got an unexpected keyword argument`: я передала
                         # `max_tokens`, которого у `call(client, messages, model, attempts)`
                         # нет. Тот же класс, что «имя поля ответа задачи угадано»: подпись
                         # надо читать, а не помнить.
                         model=os.environ.get('P25_MODEL', 'claude-fable-5'), attempts=3)
            o = obyekt(tekst_otveta(msg))
        except Exception as e:  # noqa: BLE001
            # ПРИЧИНА СБОЯ ПЕЧАТАЕТСЯ. Первый заход дал 27 сбоев из 27 и напечатал только
            # «СБОЙ линзы», а сводка при этом бодро сообщила «линзы: контактов НЕТ — 8».
            # То есть двадцать семь неудачных вызовов прочитались как содержательный ответ.
            # Это ровно то, за чем я слежу у других: ноль как диагноз прибора.
            sch['СБОЙ линзы %s: %s' % (imya, str(e)[:60])] += 1
            o = {'SBOY': True}
        otvety[imya] = o
    # ответом считается то, что сказали ХОТЯ БЫ ДВЕ линзы из трёх
    # ГОЛОСУЮТ ТОЛЬКО ОТВЕТИВШИЕ ЛИНЗЫ. Сбойная линза не голосует «нет» — она молчит, и
    # карточка, у которой смолчали все, попадает в отдельную строку «НЕ СПРОШЕНО», а не в
    # «контактов нет». Иначе падение провайдера выглядит как доказанное отсутствие контактов.
    otvetivshie = [o for o in otvety.values() if not o.get('SBOY')]
    golosa = [o.get('est_kontakty') is True for o in otvetivshie]
    est = sum(1 for g in golosa if g) >= 2
    tel = next((str(o.get('telefon') or '').strip() for o in otvety.values()
                if str(o.get('telefon') or '').strip()), '')
    chel = next((str(o.get('chelovek') or '').strip() for o in otvety.values()
                 if str(o.get('chelovek') or '').strip()), '')
    poch = next((str(o.get('pochta') or '').strip() for o in otvety.values()
                 if str(o.get('pochta') or '').strip()), '')
    # ЗАСЛОН: то, что провайдер выписал «дословно», обязано быть в тексте страницы
    v_tekste = all(not x or x[:12] in k['tekst'] for x in (tel, chel, poch))
    if k['inn'] == 'КОНТРОЛЬ':
        sch['КОНТРОЛЬ: ответило линз %d, из них «контакты есть» %d'
            % (len(otvetivshie), sum(golosa))] += 1
    elif not otvetivshie:
        sch['НЕ СПРОШЕНО: все три линзы упали'] += 1
    else:
        sch['мой парсер нашёл подписей: %d' % len(k.get('podpisi_moi') or [])] += 1
        sch['линзы: контакты ЕСТЬ' if est else 'линзы: контактов НЕТ'] += 1
        sch['линз ответило: %d из 3' % len(otvetivshie)] += 1
        if est and not v_tekste:
            sch['ЗАСЛОН: выписанное НЕ найдено в тексте страницы'] += 1
        if est and v_tekste:
            sch['НАХОДКА: контакт есть, а мой парсер его не видел'] += 1
    itog.append({'inn': k['inn'], 'predpriyatie': k.get('predpriyatie'),
                 'ssylka': k.get('ssylka'), 'podpisi_moi': k.get('podpisi_moi'),
                 'golosov_za': sum(golosa), 'chelovek': chel, 'telefon': tel, 'pochta': poch,
                 'v_tekste': v_tekste, 'linzy': otvety})
    print('  %-12s ответило линз %d/3, «есть» %d  человек:%-20s тел:%-16s в тексте:%s'
          % (str(k['inn'])[:12], len(otvetivshie), sum(golosa), chel[:20], tel[:16],
             v_tekste if otvetivshie else '—'))

with io.open(VYHOD, 'w', encoding='utf-8') as f:
    for z in itog:
        f.write(json.dumps(z, ensure_ascii=False) + '\n')
print('\n########## ЧИСЛА')
for k, v in sch.most_common():
    print('  %-56s %4d' % (k[:56], v))
print('  файл: %s' % VYHOD)
print('ИТОГ ' + json.dumps({'разобрано': len(kartochki) - 1,
                            'находок': sch.get('НАХОДКА: контакт есть, а мой парсер его не видел', 0)},
                           ensure_ascii=False))

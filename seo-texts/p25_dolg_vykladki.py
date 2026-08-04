# -*- coding: utf-8 -*-
"""Долг выкладки и здоровье потоков — числом из файлов, а не по памяти.

Отвечает на пункты сторожа 1-3 разом:
  * сколько добытого НЕ попало ни в одну выкладку;
  * жив ли поток (по времени последней записи, а не по счётчику в логе);
  * сколько записей со сбоем и переспрошены ли они успешно.

Пройденной считается только запись БЕЗ поля err — упавшая цель очередь не закрывает.

ПЕРВЫЙ ЗАХОД ЭТОГО ПРИБОРА ОБЪЯВИЛ ДОЛГ В 496 СТРОК И БЫЛ НЕПРАВ. Он сравнивал то,
что даёт именной канал (ФИО людей), с колонками ТЕЛЕФОНОВ выкладок — совпасть не
могло ни разу, и весь канал выглядел невыложенным. Правило «большое число это повод
проверить прибор» сработало на мне же. Теперь у каждого потока названо, ЧТО он
добывает, и сверка идёт с колонками того же рода: люди с людьми, номера с номерами.
"""
import collections
import csv
import glob
import json
import os
import re
import time

# путь, список, поле значения, РОД добытого ('человек' или 'контакт')
POTOKI = (
    (r'C:\sender\_ops\p25-imena.jsonl',        'lyudi',    'fio',        'человек'),
    (r'C:\sender\_ops\p25-obratnyy.jsonl',     'kontakty', 'znachenie',  'контакт'),
    (r'C:\sender\_ops\p25-obratnyy-teh.jsonl', 'kontakty', 'znachenie',  'контакт'),
    (r'C:\sender\_ops\p25-dobit.jsonl',        'naydeno',  'telefon',    'контакт'),
    (r'C:\sender\_ops\p25-dolzhnost.jsonl',    'naydeno',  'telefony',   'контакт'),
    (r'C:\sender\_ops\p25-nomer.jsonl',        'naydeno',  'nomer',      'контакт'),
    (r'C:\sender\_ops\p25-dobavochnyy.jsonl',  'naydeno',  'nomer',      'контакт'),
    (r'C:\sender\_ops\p25-tp-po-kompaniyam.jsonl', 'kartochki', 'tender_id', 'карточка'),
)
KOLONKI_KONTAKTA = ('telefon', 'znachenie', 'nomer', 'telefon_kak_napisan', 'pochta',
                    'telefony', 'mobilnyy')
KOLONKI_CHELOVEKA = ('chelovek', 'fio', 'imya', 'chelovek_v_kartochke')
csv.field_size_limit(10 ** 8)
teper = time.time()


def klyuch_znacheniya(v):
    """Номер сравнивается цифрами, человек — сжатым регистром. Написание не в счёт."""
    s = str(v or '').strip()
    if not s:
        return ''
    if re.search(r'\d{5,}', re.sub(r'\D', '', s)):
        c = re.sub(r'\D', '', s)
        return '7' + c[1:] if len(c) == 11 and c[0] in '78' else c
    return re.sub(r'\s+', ' ', s).lower()


vyl_kontakt, vyl_chelovek, fajlov = set(), set(), 0
for p in glob.glob(r'C:\seostat\drop\drop-storage\P25-*3S*.csv'):
    fajlov += 1
    try:
        with open(p, encoding='utf-8-sig', newline='') as f:
            for r in csv.DictReader(f, delimiter=';'):
                inn = (r.get('inn') or '').strip()
                if not inn:
                    continue
                for k in KOLONKI_KONTAKTA:
                    if klyuch_znacheniya(r.get(k)):
                        vyl_kontakt.add((inn, klyuch_znacheniya(r.get(k))))
                for k in KOLONKI_CHELOVEKA:
                    if klyuch_znacheniya(r.get(k)):
                        vyl_chelovek.add((inn, klyuch_znacheniya(r.get(k))))
    except Exception:  # noqa: BLE001
        continue

itog = {}
for put, spisok, pole, rod in POTOKI:
    if not os.path.exists(put):
        itog[os.path.basename(put)] = 'потока нет — не стартовал'
        continue
    strok = kontaktov = ne_vylozheno = 0
    inn_ok, inn_sboy = set(), set()
    for ln in open(put, encoding='utf-8'):
        try:
            z = json.loads(ln)
        except Exception:  # noqa: BLE001
            continue
        strok += 1
        if z.get('err'):
            inn_sboy.add(z.get('inn', ''))
            continue
        inn_ok.add(z.get('inn', ''))
        for n in (z.get(spisok) or []):
            if not isinstance(n, dict):
                continue
            syroy = n.get(pole)
            for v in (syroy if isinstance(syroy, list) else [syroy]):
                k = klyuch_znacheniya(v)
                if not k:
                    continue
                kontaktov += 1
                gde = vyl_chelovek if rod == 'человек' else vyl_kontakt
                if rod != 'карточка' and (z.get('inn', ''), k) not in gde:
                    ne_vylozheno += 1
    # СБОЙ, ПЕРЕКРЫТЫЙ УСПЕХОМ, ДОЛГОМ НЕ ЯВЛЯЕТСЯ: цель спрошена заново и ответила.
    ne_zakryto = inn_sboy - inn_ok
    itog[os.path.basename(put)] = {
        'род': rod, 'строк': strok, 'предприятий пройдено': len(inn_ok),
        'сбоев ИНН': len(inn_sboy), 'СБОЕВ БЕЗ УСПЕШНОГО ПЕРЕСПРОСА': len(ne_zakryto),
        'добыто': kontaktov, 'НЕ ВЫЛОЖЕНО': ne_vylozheno,
        'минут с последней записи': round((teper - os.path.getmtime(put)) / 60, 1),
    }

for k, v in itog.items():
    print('%-32s %s' % (k, json.dumps(v, ensure_ascii=False)))
d = [v for v in itog.values() if isinstance(v, dict)]
print('ИТОГ ' + json.dumps({
    'файлов выкладок прочитано': fajlov,
    'пар в выкладках: контактов': len(vyl_kontakt), 'людей': len(vyl_chelovek),
    'ДОЛГ ВЫКЛАДКИ': sum(v['НЕ ВЫЛОЖЕНО'] for v in d),
    'СБОЕВ БЕЗ ПЕРЕСПРОСА': sum(v['СБОЕВ БЕЗ УСПЕШНОГО ПЕРЕСПРОСА'] for v in d),
}, ensure_ascii=False))

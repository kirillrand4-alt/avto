# -*- coding: utf-8 -*-
"""Собрать вход обратного хода напрямую из дроп-файлов 2-й сессии, минуя сломанную цепочку.

Штатный vhod ищет пять серверных CSV, которых после перезапуска нет. Но 2-я сессия
выложила готовые списки имён на дроп. Беру их, оставляю только НЕпройденные пары
(которых нет в p25-obratnyy.jsonl) и только те, где ИЗВЕСТНО имя предприятия — без него
обратный ход находит однофамильцев по всей стране, это цена впустую. Пишу в тот же
VHOD-файл, что читает прогон: колонки inn, predpriyatie, fio, dolzhnost, otkuda.

Ничего не удаляет. Печатает числа. KANAL проверяется на месте: если его на сервере нет,
это будет ВИДНО, а не сойдёт за пустой прогон.
"""
import collections
import csv
import io
import json
import os
import re
import urllib.request

POTOK = r'C:\sender\_ops\p25-obratnyy.jsonl'
VHOD = r'C:\sender\_ops\3s_p25_obratnyy_vhod.csv'
KANAL = r'C:\sender\_ops\3s_lpr_obratnyy.py'
FAJLY = ['DLYA-3S-180-INN-s-imenami.csv', 'DLYA-3S-obratnyy-hod-FIO-bez-nomera.csv',
         'P25-LYUDI-2S-038.csv']


def yadro_fio(s):
    slova = [w for w in re.split(r'[^А-Яа-яЁёA-Za-z]+', str(s or '')) if len(w) > 1]
    if not slova:
        return ''
    fam = max(slova, key=len).lower().replace('ё', 'е')
    ini = ''.join(sorted(w[0].lower().replace('ё', 'е') for w in slova
                         if w.lower() != fam)[:1])
    return fam + ini


def skачать(imya):
    url = os.environ.get('DROP_URL', '').rstrip('/')
    tok = os.environ.get('DROP_TOKEN', '')
    if not url or not tok:
        return ''
    rq = urllib.request.Request('%s/%s' % (url, imya), headers={'X-Drop-Token': tok})
    try:
        with urllib.request.urlopen(rq, timeout=120) as r:
            return r.read().decode('utf-8-sig', 'replace')
    except Exception as e:  # noqa: BLE001
        print('  не скачался %s: %s' % (imya, str(e)[:50]))
        return ''


# 1) Пройденные пары и словарь ИНН -> имя предприятия из потока.
proydeno = set()
imya_po_inn = {}
if os.path.exists(POTOK):
    for s in io.open(POTOK, encoding='utf-8', errors='replace'):
        try:
            z = json.loads(s)
        except Exception:  # noqa: BLE001
            continue
        inn = str(z.get('inn') or z.get('ИНН') or '')
        fio = z.get('fio') or z.get('chelovek') or z.get('person') or ''
        if fio:
            proydeno.add((inn, yadro_fio(fio)))
        imya = z.get('predpriyatie') or z.get('company') or ''
        if inn and imya and inn not in imya_po_inn:
            imya_po_inn[inn] = imya
print('в потоке: пройдено пар %d, имён предприятий %d' % (len(proydeno), len(imya_po_inn)))


def kol(low, *varianty):
    for v in varianty:
        if low.get(v):
            return low[v].strip()
    return ''


# 2) Читаем входные файлы, копим имена, отбираем непройденные с известным именем.
vhod = {}
sch = collections.Counter()
for imya_f in FAJLY:
    tekst = skачать(imya_f)
    if not tekst:
        sch['файл не скачался: %s' % imya_f] += 1
        continue
    razd = ';' if tekst[:600].count(';') > tekst[:600].count(',') else ','
    for row in csv.DictReader(io.StringIO(tekst), delimiter=razd):
        low = {k.lower().strip(): (v or '') for k, v in row.items() if k}
        inn = re.sub(r'\D', '', kol(low, 'inn', 'инн'))
        fio = kol(low, 'chelovek', 'fio', 'фио', 'person', 'имя', 'name')
        pred = kol(low, 'predpriyatie', 'наименование', 'наименование_организации',
                   'company', 'company_name', 'organizaciya', 'организация')
        dolzh = kol(low, 'dolzhnost', 'должность', 'position', 'post')
        if not fio:
            continue
        if pred and inn and inn not in imya_po_inn:
            imya_po_inn[inn] = pred
        sch['строк с ФИО'] += 1
        klyuch = (inn, yadro_fio(fio))
        if klyuch in proydeno:
            sch['уже пройдено'] += 1
            continue
        imya_pr = pred or imya_po_inn.get(inn, '')
        if not imya_pr:
            sch['ПРОПУСК: имя предприятия неизвестно'] += 1
            continue
        if klyuch in vhod:
            continue
        vhod[klyuch] = {'inn': inn, 'predpriyatie': imya_pr, 'fio': fio.strip(),
                        'dolzhnost': dolzh, 'otkuda': imya_f}

# 3) Пишем вход прогона — ТОЧНО как штатный vhod: разделитель «;» и utf-8-sig.
# Иначе канал (он читает «;») увидит всю строку одной колонкой, ФИО не найдёт и
# честно скажет «полных ФИО 0» — что я и приняла было за «обратный ход исчерпан».
with io.open(VHOD, 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.DictWriter(f, fieldnames=['inn', 'predpriyatie', 'fio', 'dolzhnost', 'otkuda'],
                       delimiter=';')
    w.writeheader()
    w.writerows(vhod.values())

sch['ЗАПИСАНО во вход'] = len(vhod)
sch['KANAL на сервере есть'] = 1 if os.path.exists(KANAL) else 0
for k, v in sch.most_common():
    print('REC %s\t%d' % (k, v))
print('ИТОГ ' + json.dumps({'во_входе': len(vhod),
                            'KANAL_есть': os.path.exists(KANAL),
                            'файл': VHOD}, ensure_ascii=False))

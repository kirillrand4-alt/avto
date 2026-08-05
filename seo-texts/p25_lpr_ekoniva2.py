# -*- coding: utf-8 -*-
"""ЛПР ЭкоНивы: разбор, который видит «должность + Имя Фамилия», а не только ФИО из трёх слов.

ПОЧЕМУ ПЕРВЫЙ ЗАХОД ДАЛ ОДНОГО ЛОЖНОГО. Мой разбор требовал «Фамилия Имя Отчество» —
три слова. А сайт ЭкоНивы пишет иначе и в родительном падеже:

    «Ключи получили семьи заместителя главного инженера по технике животноводства
     Андрея Власенко, главного энергетика Антона Локонова…»

Тут «Антона Локонова» — имя и фамилия, два слова, склонённые. Мой шаблон их не видел, и
70 документов ушли в «без имён», хотя люди в них НАЗВАНЫ ВМЕСТЕ С ДОЛЖНОСТЬЮ и на
ПЕРВОИСТОЧНИКЕ — на сайте самого предприятия. Это тот же класс, что сегодняшняя потеря
«Юрьевич/Львович» на шаблоне отчества.

ЧТО ДЕЛАЕТ ЭТОТ РАЗБОР. Ищет связку «ДОЛЖНОСТЬ + ИМЯ», где должность стоит ПЕРЕД именем
(так пишут в новостях), берёт два слова с большой буквы сразу за должностью и приводит
их к именительному падежу простым правилом окончаний.

ПРИНАДЛЕЖНОСТЬ ДОКАЗЫВАЕТСЯ ХОСТОМ. Человек засчитывается, только если страница лежит на
домене предприятия: это первоисточник. Всё прочее печатается отдельно, с пометкой, и в
свод не идёт — близость не доказывает принадлежность.
"""
import collections
import importlib.util
import json
import os
import re

KANDIDATY = [r'C:\sender\_ops\3s_lpr_obratnyy.py', r'C:\sender\server\lpr_obratnyy.py']
DOMEN = 'ekoniva-apk.ru'

# Должности круга 1-2. Порядок важен: узкие раньше широких.
DOLZHNOSTI = (
    r'заместител\w+\s+главного\s+инженера(?:\s+по\s+[а-яё]+(?:\s+[а-яё]+)?)?',
    r'главн\w+\s+инженер\w*(?:\s+по\s+[а-яё]+)?',
    r'главн\w+\s+энергетик\w*',
    r'главн\w+\s+механик\w*',
    r'главн\w+\s+технолог\w*',
    r'главн\w+\s+агроном\w*',
    r'техническ\w+\s+директор\w*',
    r'директор\w*\s+по\s+производству',
    r'начальник\w*\s+(?:цеха|производства|энергослужбы|участка)',
    r'руководител\w+\s+(?:подразделения|направления)',
)
SVYAZKA = re.compile(
    r'(%s)\s+([А-ЯЁ][а-яё]+[ауеяю]?)\s+([А-ЯЁ][а-яё]+[ауеяю]?)' % '|'.join(DOLZHNOSTI),
    re.I)
TEL = re.compile(r'(?:\+7|\b8)[\s\-(]{0,3}\d[\d\s\-()]{7,18}\d')
POCHTA = re.compile(r'[\w.\-]+@[\w.\-]+\.[a-z]{2,}', re.I)

ZAPROSY = [
    'site:%s "главный энергетик"' % DOMEN,
    'site:%s "главный инженер"' % DOMEN,
    'site:%s "заместитель главного инженера"' % DOMEN,
    'site:%s "главный механик"' % DOMEN,
    'site:%s "технический директор"' % DOMEN,
    'site:%s "начальник цеха"' % DOMEN,
    'site:%s подразделение сотрудники' % DOMEN,
    'site:%s новости завод оборудование' % DOMEN,
    'site:%s компрессор' % DOMEN,
    'site:%s "директор по производству"' % DOMEN,
]


def imenitelnyy(s):
    """Родительный падеж -> именительный, простым правилом окончаний.

    «Антона Локонова» -> «Антон Локонов», «Андрея Власенко» -> «Андрей Власенко».
    Правило грубое и названо грубым: там, где не сработает, останется как есть, и это
    видно в цитате рядом — цитата печатается всегда.
    """
    out = []
    for w in s.split():
        if len(w) > 4:
            if w.endswith('а') and not w.endswith(('ка', 'ха', 'на')):
                w = w[:-1]
            elif w.endswith('я'):
                w = w[:-1] + 'й'
        out.append(w)
    return ' '.join(out)


def host(u):
    return re.sub(r'^www\.', '',
                  re.sub(r'^https?://', '', str(u or '')).split('/')[0].lower())


serp = None
for p in KANDIDATY:
    if os.path.exists(p):
        sp = importlib.util.spec_from_file_location('s', p)
        m = importlib.util.module_from_spec(sp)
        sp.loader.exec_module(m)
        serp = m.serp
        break
if not serp:
    print('ИТОГ ' + json.dumps({'поиска нет': True}, ensure_ascii=False))
    raise SystemExit

sch = collections.Counter()
nashi, chuzhie = {}, []
kontakty_ofisa = set()
for z in ZAPROSY:
    try:
        docs, err = serp(z)
    except Exception as e:  # noqa: BLE001
        sch['запрос упал'] += 1
        continue
    if err:
        sch['ошибка канала'] += 1
        continue
    docs = docs or []
    sch['запросов'] += 1
    for d in docs[:10]:
        url, t = d.get('url') or '', re.sub(r'\s+', ' ', str(d.get('tekst') or ''))
        svoy = DOMEN in host(url)
        for m in SVYAZKA.finditer(t):
            dolzh = re.sub(r'\s+', ' ', m.group(1)).strip().lower()
            imya = imenitelnyy('%s %s' % (m.group(2), m.group(3)))
            zapis = {'chelovek': imya, 'dolzhnost': dolzh, 'url': url,
                     'citata': t[max(0, m.start() - 90):m.end() + 90]}
            if svoy:
                k = imya.lower()
                if k not in nashi:
                    nashi[k] = zapis
                    sch['ЛЮДЕЙ С ПЕРВОИСТОЧНИКА'] += 1
            else:
                chuzhie.append(zapis)
                sch['названы НЕ на сайте предприятия (в свод не идут)'] += 1
        if svoy:
            for x in TEL.findall(t):
                kontakty_ofisa.add(('телефон', x.strip()))
            for x in POCHTA.findall(t):
                if 'ekoniva' in x.lower():
                    kontakty_ofisa.add(('почта', x.lower()))

print('=== ЛПР ЭКОНИВЫ, НАЗВАННЫЕ НА САЙТЕ ПРЕДПРИЯТИЯ (первоисточник)')
for k, v in nashi.items():
    print('\n  %-26s %s' % (v['chelovek'], v['dolzhnost']))
    print('     ссылка: %s' % v['url'][:104])
    print('     цитата: …%s…' % v['citata'][:210])
if not nashi:
    print('  ни одного')

print('\n=== контакты, найденные на страницах предприятия')
for vid, x in sorted(kontakty_ofisa):
    print('  %-8s %s' % (vid, x))

if chuzhie:
    print('\n=== названы НЕ на сайте предприятия — показываю, но в свод не беру')
    for v in chuzhie[:8]:
        print('  %-24s %-34s %s' % (v['chelovek'], v['dolzhnost'][:34], v['url'][:52]))

print()
for k, v in sch.most_common():
    print('REC %s\t%d' % (k, v))
print('ИТОГ ' + json.dumps({'людей с первоисточника': len(nashi),
                            'запросов': sch.get('запросов', 0)}, ensure_ascii=False))

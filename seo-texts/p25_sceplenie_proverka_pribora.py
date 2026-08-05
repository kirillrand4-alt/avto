# -*- coding: utf-8 -*-
"""«12 из 12» — проверяю СВОЙ прибор, прежде чем нести число. И нахожу в нём дыру.

Прошлый прогон дал «имя найдено в полном тексте: 12 из 12». Красивое число — повод
проверить прибор, а не радоваться. Смотрю, чем я сравнивала:

    w.lower() in tekst.lower()        <- подстрока, БЕЗ границ слова

И вот что это значит на 20 000 знаков страницы hh:

    «МЕТР»    совпадёт внутри «параМЕТР», «килоМЕТР»
    «РЕГИОН»  совпадёт со словом «Регион:» — оно стоит на КАЖДОЙ странице hh
    «ЗАВОДОВ» совпадёт с любым «завод» в тексте вакансии

То есть у половины находок совпадение может быть с обычным словом, а не с названием
предприятия. Это ровно тот класс, за который я платила сегодня трижды: `мост` внутри
«недвижимости», `АНО` внутри «Иванов», наш собственный ярлык «пневматика» в заголовке hh.

ЧИНЮ ДВУМЯ ПРОВЕРКАМИ СРАЗУ, и вторая — настоящая:

  1. границы слова + отсев общих слов (регион, метр, группа, сервис, завод…);
  2. **работодатель со страницы**: hh пишет «Вакансия X в городе Y, работа в компании Z».
     Достаю Z и сравниваю ЯДРА названий. Это доказательство, а не совпадение букв.

Печатаю оба исхода рядом, чтобы разница была видна, а не заявлена.
"""
import collections
import json
import os
import re
import sqlite3
import sys

sys.path.insert(0, r'C:\sender\server')
import news_scan as NS  # noqa: E402

SENDER, ENRICH = r'C:\sender\sender.db', r'C:\sender\enrich.db'
SKOLKO = int(sys.argv[1]) if len(sys.argv) > 1 else 12

OPF = re.compile(r'\b(?:ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ|АКЦИОНЕРНОЕ ОБЩЕСТВО|'
                 r'ПУБЛИЧНОЕ|НЕПУБЛИЧНОЕ|ЗАКРЫТОЕ|ОТКРЫТОЕ|ООО|ОАО|ЗАО|АО|ПАО|НАО|ГУП|'
                 r'МУП|ФГУП|АНО|ГРУППА КОМПАНИЙ|ГК|УПРАВЛЯЮЩАЯ КОМПАНИЯ|УК|ТОРГОВЫЙ ДОМ|'
                 r'ТД|НАУЧНО-ПРОИЗВОДСТВЕННОЕ ПРЕДПРИЯТИЕ|НПП|НПО|ГОСУДАРСТВЕННОЕ)\b', re.I)
OBSHCHIE = {'РЕГИОН', 'МЕТР', 'ГРУППА', 'СЕРВИС', 'ПЛЮС', 'ЗАВОД', 'ЗАВОДОВ', 'ЗАВОДА',
            'КОМПАНИЯ', 'ЦЕНТР', 'ТЕХНО', 'ПРОМ', 'СТРОЙ', 'ТОРГ', 'ГОРОД', 'РОССИЯ',
            'МОСКВА', 'ПРОИЗВОДСТВО', 'СИСТЕМА', 'ПРОЕКТ', 'ЭНЕРГО', 'РЕСУРС'}
RABOTA_V = re.compile(r'работа в компании\s+([^\n,|]{2,60})', re.I)


def yadro(name):
    s = re.sub(r'[«»"\']', ' ', str(name or ''))
    s = OPF.sub(' ', s)
    return [w for w in re.split(r'[\s,\-]+', s) if len(w) >= 4]


cs = sqlite3.connect('file:%s?mode=ro' % SENDER.replace('\\', '/'), uri=True)
kol = [r[1] for r in cs.execute('pragma table_info(confirm_reviews)')]
pend = [dict(zip(kol, r)) for r in cs.execute(
    'select %s from confirm_reviews where status="pending" order by id desc'
    % ','.join('"%s"' % k for k in kol))]
cs.close()
ce = sqlite3.connect('file:%s?mode=ro' % ENRICH.replace('\\', '/'), uri=True)
imena = {str(i): str(n or '') for i, n in ce.execute('select inn, name from companies')}
sig = collections.defaultdict(list)
for inn, url in ce.execute('select inn, source_url from signals'):
    if inn:
        sig[str(inn)].append(url or '')
ce.close()

ish = collections.Counter()
razbor = []
for d in pend[:SKOLKO]:
    inn = str(d.get('inn') or '')
    nm = imena.get(inn, '')
    url = (sig.get(inn) or [''])[0]
    z = {'id': d.get('id'), 'inn': inn, 'company': nm, 'url': url}
    tekst = ''
    if url:
        try:
            it = NS.fetch_article({'link': url, 'title': ''})
            tekst = str(it.get('full_text') or '')
        except Exception:  # noqa: BLE001
            pass
    ya = yadro(nm)
    # старый способ — подстрока
    staro = [w for w in ya if w.lower() in tekst.lower()]
    # новый 1 — границы слова + отсев общих
    novo = [w for w in ya if w.upper() not in OBSHCHIE
            and re.search(r'\b%s' % re.escape(w), tekst, re.I)]
    # новый 2 — работодатель со страницы
    m = RABOTA_V.search(tekst)
    rab = (m.group(1).strip() if m else '')
    ya_rab = set(w.upper() for w in yadro(rab))
    sovpalo_rab = bool(ya_rab & set(w.upper() for w in ya)) if rab else False
    z.update({'ядро': ya[:4], 'подстрокой': staro[:4], 'со словом': novo[:4],
              'работодатель со страницы': rab, 'ядра сошлись': sovpalo_rab})
    if sovpalo_rab:
        z['ИСХОД'] = 'ДОКАЗАНО работодателем страницы'
    elif novo:
        z['ИСХОД'] = 'имя есть как слово (слабее)'
    elif staro:
        z['ИСХОД'] = 'ТОЛЬКО ПОДСТРОКА — совпадение с обычным словом'
    else:
        z['ИСХОД'] = 'имени нет'
    ish[z['ИСХОД']] += 1
    razbor.append(z)

print('=== ПИСЬМО ЗА ПИСЬМОМ')
for z in razbor:
    print('\n  #%-5s %s' % (z['id'], str(z['company'])[:52]))
    print('     ядро %s' % z['ядро'])
    print('     подстрокой: %-28s со словом: %s' % (str(z['подстрокой'])[:28], z['со словом']))
    print('     работодатель со страницы: «%s» -> ядра сошлись: %s'
          % (str(z['работодатель со страницы'])[:44], z['ядра сошлись']))
    print('     ИСХОД: %s' % z['ИСХОД'])

print('\n\n########## ЧИСЛА: старый прибор против нового')
print('  всего проверено %d' % len(razbor))
print('  старый («подстрока найдена»)          %d'
      % sum(1 for z in razbor if z['подстрокой']))
for k, v in ish.most_common():
    print('  %-40s %3d' % (k, v))
print('ИТОГ ' + json.dumps({'проверено': len(razbor), 'исходы': dict(ish)},
                           ensure_ascii=False))

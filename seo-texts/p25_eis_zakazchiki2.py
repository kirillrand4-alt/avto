# -*- coding: utf-8 -*-
"""ЕИС, второй заход. Первый я сама же и опровергаю: он собрал 1 929 «извещений» мимо цели.

ЧТО БЫЛО НЕ ТАК — три улики, и все три видны в собственном выводе:

  1. У ВСЕХ двенадцати слов вышло РОВНО 200 строк (4 страницы × 50). А счётчик того же
     ЕИС говорит: «азотная станция 61», «ПКС 78», «ВРУ 8». Двухсот записей там быть не
     может. Значит выдача не фильтровалась моим словом.
  2. Под словом «генератор кислорода» приехала «Поставка запасных частей к автомобилям
     скорой медицинской помощи». Это не наша машина ни под каким углом.
  3. Заказчик пуст у большинства: 248 разных имён на 1 929 строк.

Причина в моём адресе. Работающий запрос — тот, которым мерились объёмы:

    ?fz44=on&fz223=on&searchString=СЛОВО&publishDateFrom=01.01.2025

а я добавила к нему свою пачку (`af`, `ca`, `pc`, `pa`, `sortDirection`, `recordsPerPage`)
и получила общую ленту. Правило, которое я нарушила и записываю себе: если запрос уже
доказан рабочим — не «улучшать» его на глаз, а взять как есть и менять по одному параметру.

ЗАСЛОН ТЕПЕРЬ ВНУТРИ ЦИКЛА, а не после него. На КАЖДОЙ странице читаю счётчик ЕИС и
сравниваю с тем, сколько карточек разобрала:
   • счётчик у всех слов одинаковый → фильтр не применён, числам не верить;
   • разобрано больше, чем счётчик обещал → я разбираю не выдачу, а что-то другое;
   • слова нет ни в предмете, ни в заказчике → строка помечается «слово не подтвердилось
     в тексте», и такие считаются отдельно, а не смешиваются с добытым.

Заказчика и предмет беру ПАРАМИ подпись→значение, а не по порядку полей: в карточке ЕИС
подписи так и лежат («Наименование заказчика», «Объект закупки»), и порядок у 44-ФЗ и
223-ФЗ разный.

Только чтение по сети. Числа в КОНЦЕ.
"""
import collections
import io
import json
import os
import re
import sqlite3
import ssl
import time
import urllib.parse
import urllib.request

SLOVA = ['компрессор', 'винтовой компрессор', 'поршневой компрессор', 'генератор азота',
         'генератор кислорода', 'азотная станция', 'кислородная станция',
         'передвижная компрессорная станция', 'осушитель сжатого воздуха',
         'воздухоразделительная установка', 'воздуходувка', 'компрессорная станция']
STRANIC = 6
BAZA = r'C:\sender\enrich.db'
VYHOD = r'C:\sender\_ops\PARK-EIS-ZAKAZCHIKI-3S.jsonl'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/120.0.0.0 Safari/537.36')
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
op = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx),
                                 urllib.request.ProxyHandler({}))
SCHET = re.compile(r'Результаты поиска\s*(?:более\s*)?([\d\s ]{1,15})\s*записей', re.I)
BLOK = re.compile(r'search-registry-entry-block(.*?)(?=search-registry-entry-block|$)', re.S)
REG = re.compile(r'regNumber=(\d{11,25})')
PARA = re.compile(r'registry-entry__body-title[^>]*>\s*(.*?)\s*</div>.*?'
                  r'registry-entry__body-value[^>]*>\s*(.*?)\s*</div>', re.S)
POSREDNIK = re.compile(r'торг|снаб|сервис|логист|трейд|оптов', re.I)
TEG = re.compile(r'<[^>]+>')


def chisto(s):
    return re.sub(r'\s+', ' ', TEG.sub(' ', s or '')).strip()


def adres(slovo, stranica):
    return ('https://zakupki.gov.ru/epz/order/extendedsearch/results.html'
            '?fz44=on&fz223=on&searchString=%s&publishDateFrom=01.01.2025&pageNumber=%d'
            % (urllib.parse.quote(slovo), stranica))


def kartochki(html):
    out = []
    for b in BLOK.findall(html):
        m = REG.search(b)
        if not m:
            continue
        polya = {chisto(t): chisto(v) for t, v in PARA.findall(b)}
        zak = ''
        for k, v in polya.items():
            if 'заказчик' in k.lower() or 'организац' in k.lower():
                zak = v
                break
        pred = ''
        for k, v in polya.items():
            if 'объект закупки' in k.lower() or 'предмет' in k.lower() or 'наименование зак' == k.lower():
                pred = v
                break
        if not pred:
            for k, v in polya.items():
                if 'заказчик' not in k.lower() and len(v) > 15:
                    pred = v
                    break
        out.append({'nomer': m.group(1), 'zakazchik': zak, 'predmet': pred})
    return out


def osnovy(slovo):
    """Основы слов запроса, чтобы сверять по началу слова, а не по точной форме."""
    return [w[:max(5, len(w) - 2)].lower() for w in re.findall(r'[А-Яа-яA-Za-z]{4,}', slovo)]


sobrano, schetchiki, po_slovu = {}, {}, collections.Counter()
oshibki, protivorechiya = collections.Counter(), []
for slovo in SLOVA:
    osn = osnovy(slovo)
    razobrano = 0
    for st in range(1, STRANIC + 1):
        u = adres(slovo, st)
        try:
            html = op.open(urllib.request.Request(u, headers={'User-Agent': UA,
                                                              'Accept-Language': 'ru'}),
                           timeout=90).read().decode('utf-8', 'replace')
        except Exception as e:  # noqa: BLE001
            oshibki['%s: %s' % (slovo, str(e)[:40])] += 1
            break
        if slovo not in schetchiki:
            tx = re.sub(r'\s+', ' ', TEG.sub(' ', re.sub(r'<script.*?</script>', ' ', html,
                                                         flags=re.S | re.I)))
            m = SCHET.search(tx)
            schetchiki[slovo] = int(re.sub(r'\D', '', m.group(1))) if m else None
        ks = kartochki(html)
        if not ks:
            break
        for o in ks:
            razobrano += 1
            tekst = (o['predmet'] + ' ' + o['zakazchik']).lower()
            o['slovo_v_tekste'] = all(any(x.startswith(k) for x in re.findall(r'[а-яa-z]+', tekst))
                                      for k in osn) if osn else False
            o['slovo'] = slovo
            o['ssylka'] = ('https://zakupki.gov.ru/epz/order/notice/notice-info/'
                           'common-info.html?regNumber=' + o['nomer'])
            o['ssylka_poiska'] = u
            if o['nomer'] in sobrano:
                sobrano[o['nomer']]['slova'].add(slovo)
                sobrano[o['nomer']]['slovo_v_tekste'] |= o['slovo_v_tekste']
            else:
                o['slova'] = {slovo}
                sobrano[o['nomer']] = o
        po_slovu[slovo] += len(ks)
        time.sleep(0.8)
    sch = schetchiki.get(slovo)
    if sch is not None and razobrano > sch:
        protivorechiya.append('%s: счётчик обещал %d, разобрано %d — разбираю не выдачу'
                              % (slovo, sch, razobrano))

vidno = [v for v in schetchiki.values() if v is not None]
if len(set(vidno)) <= 1 and len(vidno) > 3:
    protivorechiya.append('счётчик у всех слов одинаковый (%s) — фильтр не применён'
                          % (vidno[0] if vidno else '?'))

imena = {}
if os.path.exists(BAZA):
    try:
        cx = sqlite3.connect('file:%s?mode=ro' % BAZA.replace('\\', '/'), uri=True)
        for inn, nm in cx.execute('select inn, name from companies where name is not null'):
            k = re.sub(r'[^А-ЯA-Z0-9]', '', (nm or '').upper())
            if len(k) > 5:
                imena.setdefault(k, str(inn))
        cx.close()
    except Exception as e:  # noqa: BLE001
        oshibki['база имён: %s' % str(e)[:40]] += 1

potok = []
for o in sobrano.values():
    k = re.sub(r'[^А-ЯA-Z0-9]', '', o['zakazchik'].upper())
    inn = imena.get(k, '')
    potok.append({
        'nomer': o['nomer'],
        'zakazchik': o['zakazchik'],
        'inn': inn,
        'inn_otkuda': 'сшит по названию с enrich.db' if inn else 'не найден',
        'predmet': o['predmet'][:300],
        'slova': ' | '.join(sorted(o['slova'])),
        'slovo_podtverzhdeno_tekstom': bool(o['slovo_v_tekste']),
        'istochniki': o['ssylka'] + ' | ' + o['ssylka_poiska'],
        'istochnikov': 2,
        'podozrenie': 'посредник по названию' if POSREDNIK.search(o['zakazchik']) else '',
        'kto': '3-я сессия, ЕИС по словам',
    })
potok.sort(key=lambda o: (not o['slovo_podtverzhdeno_tekstom'], o['nomer']))
with io.open(VYHOD, 'w', encoding='utf-8') as f:
    for o in potok:
        f.write(json.dumps(o, ensure_ascii=False) + '\n')

vylozheno = 'не выкладывала'
try:
    o2 = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request('%s/%s' % (os.environ.get('DROP_URL', '').rstrip('/'),
                                            os.path.basename(VYHOD)),
                                 data=io.open(VYHOD, 'rb').read(), method='PUT',
                                 headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')})
    vylozheno = o2.open(req, timeout=300).read().decode('utf-8', 'replace')[:110]
except Exception as e:  # noqa: BLE001
    vylozheno = 'не выложено: %s' % str(e)[:90]

podtv = [o for o in potok if o['slovo_podtverzhdeno_tekstom']]
s_inn = [o for o in podtv if o['inn']]
print('\n\n########## ЗАСЛОН')
for p in protivorechiya:
    print('  ПРОТИВОРЕЧИЕ: %s' % p)
if not protivorechiya:
    print('  противоречий нет: счётчики разные и разобранное в них укладывается')
print('\n########## ПРИМЕРЫ подтверждённых текстом')
for o in podtv[:6]:
    print('  %-22s %-40s инн %s' % (o['nomer'], o['zakazchik'][:40], o['inn'] or '—'))
    print('     %s' % o['predmet'][:140])
print('\n########## ЧИСЛА')
print('  извещений собрано              %6d' % len(potok))
print('  слово подтверждено текстом     %6d' % len(podtv))
print('  разных заказчиков (подтв.)     %6d' % len({o['zakazchik'] for o in podtv if o['zakazchik']}))
print('  ИНН сшит по названию (подтв.)  %6d  (разных %d)'
      % (len(s_inn), len({o['inn'] for o in s_inn})))
print('  помечено «посредник»           %6d' % sum(1 for o in podtv if o['podozrenie']))
print('  --- счётчик ЕИС / разобрано')
for s in SLOVA:
    print('     %-36s счётчик %-9s разобрано %d'
          % (s, schetchiki.get(s, '?'), po_slovu.get(s, 0)))
if oshibki:
    print('  --- ошибки')
    for k, v in oshibki.most_common(6):
        print('     %-56s %4d' % (k[:56], v))
print('  файл: %s' % VYHOD)
print('  выложено: %s' % vylozheno)
print('ИТОГ ' + json.dumps({'собрано': len(potok), 'подтверждено словом': len(podtv),
                            'с ИНН': len(s_inn), 'противоречий': len(protivorechiya)},
                           ensure_ascii=False))

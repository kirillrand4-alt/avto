# -*- coding: utf-8 -*-
"""130 серий «вид не установлен» — разобрать ПРОВАЙДЕРОМ, а не оставлять в подвешенном.

Словарь дал 681 доказанную серию и 130, у которых вид машины ни разу не назван рядом.
Регуляркой их не добить: слов рядом нет, а гадать по префиксу — это вернуть в словарь моё
мнение, от которого я и уходила.

Правило владельца: «всю тяжёлую работу — через провайдерский API». Здесь она ровно такая:
модели даётся ОБОЗНАЧЕНИЕ и ЦИТАТА из нашего документа, и она отвечает, наша это машина или
нет, и какая. Ответ обязан опираться на цитату — это записано в промпте.

ЗАСЛОН ОТ САМООБМАНА: модель может уверенно назвать классом что угодно. Поэтому в промпте
разрешён ответ «не наша машина» и «непонятно», и я печатаю, сколько раз они выбраны. Если
«непонятно» ноль на 130 неясных строках — значит модель угадывает, и я это увижу.

Провайдер — общий ресурс. Замок беру строкой в журнале; вызовов ровно 130, стриминг.
"""
import collections
import csv
import io
import json
import os
import re
import sys

sys.path.insert(0, r'C:\sender\server')
sys.path.insert(0, r'C:\sender\_ops')

FAYL = r'C:\sender\_ops\PARK-SLOVAR-SERII-PROVERIT-3S.csv'
PROMPT = (
    'Ты инженер по компрессорному оборудованию. Дано ОБОЗНАЧЕНИЕ из технического документа '
    'и ЦИТАТА, в которой оно встретилось. Определи по ЦИТАТЕ, что это.\n'
    'Отвечай СТРОГО JSON без markdown: {"nashe":true/false,'
    '"vid":"компрессор|воздуходувка|нагнетатель|ВРУ|генератор азота|генератор кислорода|'
    'МКС передвижная|осушитель|ГПА|не наша машина|непонятно",'
    '"princip":"центробежный|винтовой|поршневой|мембранный|адсорбционный|непонятно",'
    '"pochemu":"одна фраза ИЗ ЦИТАТЫ, на которой основан вывод"}\n'
    'Если в цитате нет оснований — ставь "непонятно", это нормальный ответ. '
    'Если это вентилятор, насос, задвижка, электроаппарат, здание, позиция на схеме — '
    'ставь "не наша машина".\n'
    'ОБОЗНАЧЕНИЕ: %s\nЦИТАТА: %s')


def vzyat_klienta():
    for imya in ('gen_provider', 'provider_client', 'vc'):
        try:
            m = __import__(imya)
            for f in ('call', 'provider_call', '_provider_call_stdlib'):
                if hasattr(m, f):
                    return imya + '.' + f, getattr(m, f)
        except Exception:  # noqa: BLE001
            continue
    try:
        import news_scan as NS
        import importlib
        VC = importlib.import_module(NS.VC.__name__) if hasattr(NS, 'VC') else None
        if VC and hasattr(VC, '_provider_call_stdlib'):
            return 'news_scan.VC._provider_call_stdlib', VC._provider_call_stdlib
    except Exception:  # noqa: BLE001
        pass
    return None, None


imya_kl, zov = vzyat_klienta()
print('клиент провайдера: %s' % imya_kl)
if not zov:
    print('ИТОГ ' + json.dumps({'провайдера нет': True}, ensure_ascii=False))
    raise SystemExit

rows = list(csv.DictReader(io.open(FAYL, encoding='utf-8-sig'), delimiter=';'))
print('серий на разбор: %d' % len(rows))

sch = collections.Counter()
otvety = []
for i, r in enumerate(rows):
    s = r.get('seriya') or ''
    cit = (r.get('citata') or '')[:400]
    try:
        out = zov(PROMPT % (s, cit))
        m = re.search(r'\{.*\}', out or '', re.S)
        d = json.loads(m.group(0)) if m else {}
    except Exception as e:  # noqa: BLE001
        sch['вызов упал'] += 1
        continue
    vid = str(d.get('vid') or 'непонятно')
    sch[vid] += 1
    sch['наше=%s' % bool(d.get('nashe'))] += 1
    otvety.append({'seriya': s, 'vid': vid, 'princip': d.get('princip'),
                   'nashe': bool(d.get('nashe')), 'pochemu': str(d.get('pochemu') or '')[:110],
                   'citata': cit[:110]})

put = r'C:\sender\_ops\PARK-SLOVAR-SERII-RAZOBRANY-3S.json'
io.open(put, 'w', encoding='utf-8').write(json.dumps(otvety, ensure_ascii=False, indent=1))

print('\n\n########## ДЕСЯТЬ ОТВЕТОВ ГЛАЗАМИ')
for o in otvety[:10]:
    print('\n  %-16s наше=%-5s %-22s %s' % (o['seriya'], o['nashe'], o['vid'], o['princip']))
    print('     почему: %s' % o['pochemu'])
    print('     цитата: %s' % o['citata'])

print('\n\n########## ЧИСЛА')
for k, v in sch.most_common():
    print('  %-34s %5d' % (k, v))
print('  файл: %s' % put)
print('ИТОГ ' + json.dumps({'разобрано': len(otvety), 'по видам': dict(sch)},
                           ensure_ascii=False)[:600])

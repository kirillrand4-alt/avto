# -*- coding: utf-8 -*-
"""Провайдерский разбор СЕРИЙ: наша машина, не наша или непонятно. С цитатой у каждой.

Сторож спрашивает это каждый тик, а я отвечала числами соседнего замера — разбора страниц
контактов. Закрываю пункт по-настоящему: беру серии из словаря и прошу модель сказать по
КАЖДОЙ, что это, опираясь на цитату из документа, которая при серии уже лежит.

Три исхода, и «непонятно» — полноправный, а не стыдный:

    наша машина      компрессор, воздуходувка, нагнетатель, ВРУ, генератор азота/кислорода,
                     осушитель, МКС — то, чем торгует владелец
    не наша машина   насос, вентилятор, котёл, кран, трубопровод и прочее оборудование ОПО
    непонятно        обозначение есть, а из цитаты вид машины не следует

ЗАСЛОН НА ВЫДУМКУ, тот же, что в разборе страниц: ответ модели засчитывается, только если
обозначение из ответа совпадает с тем, что я послала. Модель охотно «поправляет» серию на
похожую (К-250 -> К-250-61-5), и такая поправка выглядит убедительно, но это уже другая
запись словаря.

ОТРИЦАТЕЛЬНЫЙ КОНТРОЛЬ: в каждую пачку подкладываю выдуманное обозначение «ЩВ-777/9» с
выдуманной цитатой про насос. Если модель назовёт его нашей машиной — разбору грош цена,
и я скажу это первой строкой.

Числа в КОНЦЕ.
"""
import collections
import io
import json
import os
import re
import sys
import threading
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_provider as gp  # noqa: E402

KANDIDATY = [x for x in os.environ.get('P25_MODEL', 'claude-fable-5').split(',') if x.strip()]
SLOVAR = 'PARK-SLOVAR-SERII-3S-v4.csv'
VYHOD = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'PARK-SLOVAR-RAZBOR-3S.jsonl')
V_PACHKE = 25
POTOKOV = 4
drop = os.environ.get('DROP_URL', '').rstrip('/')
tok = {'X-Drop-Token': os.environ.get('DROP_TOKEN', '')}
op = urllib.request.build_opener(urllib.request.ProxyHandler({}))

PROMPT = '''Ты разбираешь обозначения оборудования из российских документов промышленной
безопасности. По каждой строке скажи, что это за машина, опираясь ТОЛЬКО на цитату.

Верни JSON-массив, по одному элементу на строку входа, без пояснений:
{"oboznachenie": "<ровно как во входе>", "vid": "наша машина|не наша машина|непонятно",
 "kakaya": "компрессор|воздуходувка|нагнетатель|ВРУ|генератор азота|генератор кислорода|
 осушитель|МКС|насос|вентилятор|котёл|иное|—", "pochemu": "<до 12 слов из цитаты>"}

«Наша машина» — только компрессор, воздуходувка, нагнетатель, ВРУ, генератор азота или
кислорода, осушитель сжатого воздуха, передвижная компрессорная станция.
Если из цитаты вид не следует — «непонятно». Не догадывайся по буквам обозначения.
Обозначение верни ДОСЛОВНО как во входе, не исправляй его.

Строки:
'''
KONTROL = {'oboznachenie': 'ЩВ-777/9',
           'citata': 'Заключение ЭПБ на техническое устройство насос центробежный ЩВ-777/9, '
                     'зав. № 1, применяемый на опасном производственном объекте'}


def s_dropa(imya):
    return op.open(urllib.request.Request('%s/%s' % (drop, imya), headers=tok),
                   timeout=180).read().decode('utf-8-sig', 'replace')


def tekst_otveta(msg):
    if isinstance(msg, str):
        return msg
    return ''.join(getattr(b, 'text', '') or '' for b in getattr(msg, 'content', []) or []
                   if getattr(b, 'type', '') == 'text')


st = s_dropa(SLOVAR).splitlines()
sh = [x.strip() for x in st[0].split(';')]
ji = sh.index('seriya') if 'seriya' in sh else 0
jc = sh.index('citata') if 'citata' in sh else len(sh) - 1
serii = []
for s in st[1:]:
    p = s.split(';')
    if len(p) <= jc:
        continue
    serii.append({'oboznachenie': p[ji].strip(), 'citata': ';'.join(p[jc:])[:400]})

pachki = [serii[i:i + V_PACHKE] for i in range(0, len(serii), V_PACHKE)]
zamok = threading.Lock()
ochered = list(range(len(pachki)))
razbor, snyato, sch = [], collections.Counter(), {'sprosheno': 0, 'kontrol_probit': 0}
klient = gp.make_client()


def odna(i):
    pachka = list(pachki[i]) + [KONTROL]
    vhod = '\n'.join('%d) %s — цитата: %s' % (n + 1, o['oboznachenie'], o['citata'])
                     for n, o in enumerate(pachka))
    otvet = ''
    for m in KANDIDATY:
        try:
            otvet = tekst_otveta(gp.call(klient, [{'role': 'user', 'content': PROMPT + vhod}],
                                         model=m, attempts=2))
            break
        except Exception as e:  # noqa: BLE001
            with zamok:
                snyato['%s не ответила: %s' % (m, str(e)[:30])] += 1
    mm = re.search(r'\[.*\]', otvet or '', re.S)
    if not mm:
        with zamok:
            snyato['ответ без JSON-массива'] += 1
        return
    try:
        spisok = json.loads(mm.group(0))
    except Exception:  # noqa: BLE001
        with zamok:
            snyato['битый JSON'] += 1
        return
    poslano = {o['oboznachenie'] for o in pachka}
    with zamok:
        sch['sprosheno'] += 1
        for o in spisok if isinstance(spisok, list) else []:
            if not isinstance(o, dict):
                continue
            ob = str(o.get('oboznachenie') or '').strip()
            if ob == KONTROL['oboznachenie']:
                if str(o.get('vid') or '').startswith('наша'):
                    sch['kontrol_probit'] += 1
                continue
            # ЗАСЛОН: обозначение должно быть тем же, что послано
            if ob not in poslano:
                snyato['модель вернула ДРУГОЕ обозначение — снимаю'] += 1
                continue
            razbor.append({'oboznachenie': ob, 'vid': str(o.get('vid') or 'непонятно'),
                           'kakaya': str(o.get('kakaya') or '—')[:40],
                           'pochemu': str(o.get('pochemu') or '')[:120],
                           'kto': 'разбор моделью %s' % KANDIDATY[0]})


def rabotnik():
    while True:
        with zamok:
            if not ochered:
                return
            i = ochered.pop(0)
        try:
            odna(i)
        except Exception as e:  # noqa: BLE001
            with zamok:
                snyato['исключение: %s' % str(e)[:30]] += 1


nitki = [threading.Thread(target=rabotnik) for _ in range(POTOKOV)]
for n in nitki:
    n.start()
for n in nitki:
    n.join()

with io.open(VYHOD, 'w', encoding='utf-8') as f:
    for o in razbor:
        f.write(json.dumps(o, ensure_ascii=False) + '\n')
try:
    rq = urllib.request.Request('%s/%s' % (drop, os.path.basename(VYHOD)),
                                data=io.open(VYHOD, 'rb').read(), method='PUT', headers=tok)
    vyl = op.open(rq, timeout=300).read().decode('utf-8', 'replace')[:80]
except Exception as e:  # noqa: BLE001
    vyl = 'НЕ ВЫЛОЖЕНО: %s' % str(e)[:60]

vidy = collections.Counter(o['vid'][:24] for o in razbor)
kakie = collections.Counter(o['kakaya'] for o in razbor if o['vid'].startswith('наша'))
print('\n\n########## ПО ОДНОЙ, ПЕРВЫЕ ДЕСЯТЬ')
for o in razbor[:10]:
    print('  %-14s %-16s %-18s %s' % (o['oboznachenie'][:14], o['vid'][:16],
                                      o['kakaya'][:18], o['pochemu'][:44]))
print('\n########## ЧИСЛА')
print('  серий во входе                 %5d  (файл %s)' % (len(serii), SLOVAR))
print('  пачек спрошено                 %5d из %d' % (sch['sprosheno'], len(pachki)))
print('  разобрано серий                %5d' % len(razbor))
for k, v in vidy.most_common():
    print('     %-30s %5d' % (k, v))
print('  --- какая машина у «нашей»')
for k, v in kakie.most_common(9):
    print('     %-30s %5d' % (k[:30], v))
print('  ОТРИЦАТЕЛЬНЫЙ КОНТРОЛЬ «ЩВ-777/9» (насос): назван нашей машиной %d раз из %d %s'
      % (sch['kontrol_probit'], sch['sprosheno'],
         '— РАЗБОРУ ВЕРИТЬ НЕЛЬЗЯ' if sch['kontrol_probit'] else '— контроль чист'))
for k, v in snyato.most_common(8):
    print('     снято: %-46s %5d' % (k[:46], v))
print('  выложено: %s' % vyl)
print('ИТОГ ' + json.dumps({'серий': len(serii), 'разобрано': len(razbor),
                            'наша': vidy.get('наша машина', 0),
                            'не наша': vidy.get('не наша машина', 0),
                            'непонятно': vidy.get('непонятно', 0),
                            'контроль пробит': sch['kontrol_probit']}, ensure_ascii=False))

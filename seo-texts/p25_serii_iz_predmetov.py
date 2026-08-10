# -*- coding: utf-8 -*-
"""Провайдер вынимает СЕРИИ И МОДЕЛИ из предметов свежих закупок. Словарь растёт из добычи.

Прежний провайдерский прогон отвечал на вопрос «что это за серия» по уже известным сериям:
435 из 435, наша машина 292, непонятно 100, не наша 43. Это проверка словаря, а не его рост.
Здесь обратный ход: беру ПРЕДМЕТЫ закупок, добытых за последние тики (park_ingest_3d, 1 866
строк), и прошу модель вынуть из них обозначения машин — то, чего в словаре ещё нет.

Зачем это парку. Обозначение — это ключ поиска: по «ЦК-135/8» и «ТВ-80-1,6» ищутся и реестр
ЭПБ, и площадки, и сайты. Каждая новая серия — это новый запрос, а значит новые предприятия.

ЗАСЛОН НА ВЫДУМКУ, тот же, что в разборе серий и в разборе страниц: обозначение
засчитывается, только если оно СТОИТ В ПРЕДМЕТЕ буквально (сравнение по голой строке, без
пробелов и дефисов). Модель охотно достраивает «К-250» до «К-250-61-5» — правдоподобно и
неверно.

ОТРИЦАТЕЛЬНЫЙ КОНТРОЛЬ: в каждую пачку подкладывается выдуманный предмет «Поставка
канцелярских товаров и бумаги А4 для нужд управления». Если модель вынет из него
обозначение машины — разбору грош цена, и это будет сказано первой строкой.

Дефект 2-й сессии учтён: `gp.call` возвращает ОБЪЕКТ, текст лежит в блоках `content`.

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

SCRATCH = os.environ.get('P25_SCRATCH', '.')
VHOD = os.path.join(SCRATCH, 'park_ingest_3d.jsonl')
VYHOD = os.path.join(SCRATCH, 'PARK-SERII-IZ-PREDMETOV-3S.jsonl')
SLOVAR = os.path.join(SCRATCH, 'PARK-SLOVAR-EDINYY.csv')
MODEL = os.environ.get('P25_MODEL', 'claude-fable-5')
V_PACHKE = int(os.environ.get('P25_V_PACHKE', '25'))
PACHEK = int(os.environ.get('P25_PACHEK', '20'))
POTOKOV = int(os.environ.get('P25_POTOKOV', '3'))
KONTROL = 'Поставка канцелярских товаров и бумаги А4 для нужд управления'
drop = os.environ.get('DROP_URL', '').rstrip('/')
tok = {'X-Drop-Token': os.environ.get('DROP_TOKEN', '')}
op = urllib.request.build_opener(urllib.request.ProxyHandler({}))

PROMPT = (
    'Ты разбираешь предметы закупок промышленного оборудования. Для КАЖДОЙ строки верни '
    'JSON-объект в отдельной строке, без пояснений:\n'
    '{"n": номер строки, "oboznachenie": "обозначение машины ровно как в тексте или пустая '
    'строка", "vid": "компрессор|воздуходувка|нагнетатель|ВРУ|генератор азота|'
    'генератор кислорода|осушитель|не наша машина|непонятно"}\n'
    'Обозначение — это заводская марка машины: К-250-61-5, ЦК-135/8, ТВ-80-1,6, GA110, '
    'XAS 97. НЕ обозначение: технологическая позиция (поз. ПК-6), заводской номер '
    '(зав. № 118413), инвентарный номер, регистрационный номер ОПО, номер закупки.\n'
    'Если машина названа, а марки в тексте нет — обозначение пустое, вид всё равно назови.\n'
    'Строки:\n')


def tekst_otveta(msg):
    """Дефект 2-й сессии: call возвращает объект, а не строку. Текст — в блоках content."""
    return ''.join(getattr(b, 'text', '') or '' for b in getattr(msg, 'content', []) or []
                   if getattr(b, 'type', '') == 'text')


def golo(s):
    return re.sub(r'[^а-яёa-z0-9]', '', str(s or '').lower())


izvestnye = set()
if os.path.exists(SLOVAR):
    sh = None
    for s in io.open(SLOVAR, encoding='utf-8-sig'):
        p = s.rstrip('\n').split(';')
        if sh is None:
            sh = p
            continue
        if len(p) == len(sh):
            izvestnye.add(golo(dict(zip(sh, p)).get('oboznachenie')))

predmety = []
vidno = set()
for s in io.open(VHOD, encoding='utf-8'):
    try:
        o = json.loads(s)
    except Exception:  # noqa: BLE001
        continue
    p = (o.get('predmet') or '').strip()
    if p and golo(p) not in vidno:
        vidno.add(golo(p))
        predmety.append((o.get('inn'), p[:300], o.get('istochniki') or ''))

pachki = [predmety[i:i + V_PACHKE] for i in range(0, len(predmety), V_PACHKE)][:PACHEK]
klient = gp.make_client()
zamok = threading.Lock()
ochered = list(enumerate(pachki))
nashli, sch, kontrol_probit = [], collections.Counter(), 0


def rabotnik():
    global kontrol_probit
    while True:
        with zamok:
            if not ochered:
                return
            nomer, pachka = ochered.pop()
        stroki = list(pachka) + [(None, KONTROL, '')]
        vhod = '\n'.join('%d. %s' % (i + 1, p) for i, (_, p, _u) in enumerate(stroki))
        try:
            otvet = tekst_otveta(gp.call(klient, [{'role': 'user', 'content': PROMPT + vhod}],
                                         model=MODEL, attempts=3))
        except Exception as e:  # noqa: BLE001
            with zamok:
                sch['пачка не разобралась: %s' % str(e)[:30]] += 1
            return
        for stroka in otvet.splitlines():
            stroka = stroka.strip().strip('`')
            if not stroka.startswith('{'):
                continue
            try:
                d = json.loads(stroka)
            except Exception:  # noqa: BLE001
                continue
            i = int(d.get('n') or 0) - 1
            if i < 0 or i >= len(stroki):
                continue
            inn, predmet, ssylki = stroki[i]
            ob = (d.get('oboznachenie') or '').strip()
            vid = (d.get('vid') or '').strip()
            if inn is None:  # это контроль
                with zamok:
                    if ob or vid not in ('не наша машина', 'непонятно', ''):
                        kontrol_probit += 1
                continue
            with zamok:
                if not ob:
                    sch['марки в предмете нет, вид назван: %s' % vid[:20]] += 1
                    continue
                if golo(ob) not in golo(predmet):
                    sch['ОБОЗНАЧЕНИЕ ВЫДУМАНО — в предмете его нет'] += 1
                    continue
                nashli.append({'inn': inn, 'oboznachenie': ob, 'vid': vid,
                               'predmet': predmet[:200], 'istochniki': ssylki,
                               'novoe_dlya_slovarya': golo(ob) not in izvestnye,
                               'kto': '3-я сессия, серии из предметов закупок'})
                sch['обозначение взято'] += 1


niti = [threading.Thread(target=rabotnik) for _ in range(POTOKOV)]
for n in niti:
    n.start()
for n in niti:
    n.join()

with io.open(VYHOD, 'w', encoding='utf-8') as f:
    for z in nashli:
        f.write(json.dumps(z, ensure_ascii=False) + '\n')
try:
    rq = urllib.request.Request('%s/%s' % (drop, os.path.basename(VYHOD)),
                                data=io.open(VYHOD, 'rb').read(), method='PUT', headers=tok)
    vyl = op.open(rq, timeout=300).read().decode('utf-8', 'replace')[:70]
except Exception as e:  # noqa: BLE001
    vyl = 'НЕ ВЫЛОЖЕНО: %s' % str(e)[:50]

novye = {z['oboznachenie'] for z in nashli if z['novoe_dlya_slovarya']}
print('\n\n########## НОВЫЕ ОБОЗНАЧЕНИЯ, ПЕРВЫЕ ПЯТНАДЦАТЬ')
for z in [x for x in nashli if x['novoe_dlya_slovarya']][:15]:
    print('  %-18s %-18s %s' % (z['oboznachenie'][:18], z['vid'][:18], z['predmet'][:60]))
print('\n########## ЧИСЛА')
print('  предметов во входе             %5d  (файл %s)' % (len(predmety),
                                                           os.path.basename(VHOD)))
print('  пачек спрошено                 %5d по %d' % (len(pachki), V_PACHKE))
print('  обозначений взято              %5d  (разных %d)'
      % (len(nashli), len({z['oboznachenie'] for z in nashli})))
print('  НОВЫХ для словаря              %5d  (в словаре было %d)' % (len(novye),
                                                                     len(izvestnye)))
print('  ОТРИЦАТЕЛЬНЫЙ КОНТРОЛЬ (канцтовары): %s'
      % ('обозначение вынуто 0 раз — разбор не выдумывает' if not kontrol_probit
         else 'ВЫНУТО %d РАЗ — разбор выдумывает, числам верить нельзя' % kontrol_probit))
print('  --- что и почему')
for k, v in sch.most_common(10):
    print('     %-52s %5d' % (k[:52], v))
print('  выложено: %s' % vyl)
print('ИТОГ ' + json.dumps({'предметов': len(predmety), 'взято': len(nashli),
                            'новых': len(novye), 'контроль пробит': kontrol_probit},
                           ensure_ascii=False))

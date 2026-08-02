# -*- coding: utf-8 -*-
"""Доузнать среду там, где она не названа, и оставить в очереди только воздух.

Распоряжение владельца дословно: «мне нужны только воздушные, остальные можешь выкидывать
(где знаешь среду, а где не знаешь = узнай)».

На момент запуска из 12 265 центробежных фактов среда была названа у 5 142, а у 7 123 — нет.
Это не мелочь на полях: без среды сидело 803 предприятия, то есть больше половины очереди.
Выкинуть их как «не воздух» нельзя — среди них Норильский никель, НЛМК, ЕВРАЗ ЗСМК, АНХК, где
воздушных машин заведомо больше, чем газовых. Значит надо именно узнавать, а не гадать.

Узнаём четырьмя каналами, строго по убыванию надёжности. Каждому факту пишем не только среду,
но и КАК мы её узнали (колонка sreda_otkuda) — чтобы продавец видел разницу между «в тексте
написано „воздушный компрессор“» и «догадались по роду деятельности»:

  1. **сказано прямо** — слово в самом тексте факта (это уже сделал tip_mashiny.sreda_mashiny);
  2. **та же марка у того же предприятия** — если у ЕВРАЗ ЗСМК про К-500-61-1 в одном заключении
     сказано «воздушный», то и остальные заключения про К-500-61-1 у ЕВРАЗ ЗСМК про ту же машину.
     Это перенос факта, а не догадка;
  3. **марка однозначна по всему корпусу** — если марка встречается у разных предприятий и всюду
     с одной средой, обозначение эту среду и означает;
  4. **решил провайдер по всем контекстам марки** — модели показывают все упоминания марки в
     корпусе (в том числе те, где среда названа) и просят определить среду с обоснованием.
     Отдельно — предприятия, у которых марок нет вовсе: там решаем по роду деятельности.

Остаток, который не закрылся ничем, честно помечается «среда не установлена» и НЕ выдаётся за
воздух. Владельцу нужен воздух, а не видимость воздуха.

Использование:
    python3 sreda_dobor.py --marki           # спросить провайдера про марки
    python3 sreda_dobor.py --predpriyatiya   # спросить провайдера про предприятия без марок
    python3 sreda_dobor.py --primenit        # применить все каналы к базе фактов
"""
import csv
import json
import os
import re
import subprocess
import sys
import threading
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_provider  # noqa: E402

csv.field_size_limit(10 ** 7)
BAZA = os.path.dirname(os.path.abspath(__file__))
L = os.path.join(BAZA, 'engineers-lens')
FAKTY = os.path.join(L, 'SVOD-tri-sostoyaniya.csv')
PO_MARKAM = os.path.join(L, 'SREDA-po-markam.csv')
PO_PRED = os.path.join(L, 'SREDA-po-predpriyatiyam.csv')
MODEL = os.environ.get('MODEL_SREDA', 'deepseek-v4-pro')
NASH = {'центробежная', 'центробежная по серии'}
NE_NAZVANA = 'среда не названа'

PRAVILA = """Ты инженер по компрессорному оборудованию. Определи РАБОЧУЮ СРЕДУ машины.

Ответ по каждой позиции — одно из четырёх:
  воздух      — машина сжимает атмосферный воздух: технологический воздух, воздух КИП, дутьё
                доменной печи, аэрация аэротенков очистных сооружений, флотация, пневмотранспорт,
                паровоздуходувная станция (ПВС). Воздухоразделительная установка (ВРУ, кислородная
                станция) — ТОЖЕ ВОЗДУХ: на входе у неё атмосферный воздух, кислород и азот это уже
                продукт на выходе.
  газ         — природный или попутный газ, ГПА и магистральные газопроводы, УКПГ, ДКС, СПГ,
                аммиак, водород, этилен, пропилен, хлор, сероводород, углекислота, хладагент.
  оба         — машина работает и на воздухе, и на газе, либо в позиции две разные машины.
  не ясно     — данных не хватает. Ставь это честно, не угадывай.

Правила, нарушение которых делает ответ бесполезным:
  1. Опирайся ТОЛЬКО на приведённые контексты и на общеизвестное значение обозначения серии.
     Ничего не додумывай про предприятие.
  2. Если обозначение серии само по себе говорит о среде — скажи это в обосновании
     (например «ТВ- это турбовоздуходувка», «НЦ- это нагнетатель центробежный для ГПА»).
  3. Обоснование — одна фраза, по-русски, без длинных тире.
  4. Уверенность: «высокая», если среда следует из обозначения или прямо сказана в контексте;
     «средняя», если выведена из назначения установки; «низкая» во всех остальных случаях.

Верни ТОЛЬКО JSON-массив без обрамления, по одному объекту на позицию, в том же порядке:
[{"nomer": 1, "sreda": "воздух", "pochemu": "...", "uverennost": "высокая"}]"""


def chitat():
    return list(csv.DictReader(open(FAKTY, encoding='utf-8-sig'), delimiter=';'))


def uzhe_otvecheno(put, klyuch):
    """Что уже разобрано в прошлый раз — чтобы повтор спрашивал только неотвеченное."""
    if not os.path.exists(put):
        return {}
    return {r[klyuch]: r for r in csv.DictReader(open(put, encoding='utf-8-sig'), delimiter=';')
            if r.get('sreda') and r['sreda'] != 'ответа не было'}


def marki_iz(x):
    return [m.strip().strip('.,;').upper().replace(' ', '')
            for m in (x.get('marki') or '').split('|') if len(m.strip()) >= 3]


def sprosit(pozicii, chto):
    """Один батч к провайдеру. Возвращает список ответов той же длины (или короче при сбое)."""
    telo = '\n\n'.join(f'{i}. {p}' for i, p in enumerate(pozicii, 1))
    msg = [{'role': 'user', 'content': f'{PRAVILA}\n\nПозиции ({chto}), их {len(pozicii)}:\n\n{telo}'}]
    try:
        otv = gen_provider.call_model(MODEL, msg, max_tokens=8000, attempts=3)
        t = otv.content[0].text
    except Exception as ex:                                     # noqa: BLE001
        print(f'  сбой провайдера: {ex}', file=sys.stderr)
        return []
    m = re.search(r'\[[\s\S]*\]', t)
    if not m:
        return []
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return []


def pachkami(zadaniya, chto, vyhod, kolonki, potokov=4, pachka=10):
    """Разложить задания по пачкам и опросить провайдера в несколько потоков.

    Пачка, на которую провайдер не ответил, НЕ становится ответом «не ясно». Это была тихая
    подмена: первый прогон получил 56 отказов 502 из 79 пачек, и 1 400 марок легли в файл как
    «не ясно» — то есть отказ шлюза выглядел в отчёте как решение модели. Теперь упавшая пачка
    режется пополам и переспрашивается, а то, что не ответило и после этого, помечается
    уверенностью «ответа не было» и в применение не идёт вовсе.
    """
    pachki = [zadaniya[i:i + pachka] for i in range(0, len(zadaniya), pachka)]
    vsego = len(pachki)
    gotovo, zamok = [], threading.Lock()
    schet = {'n': 0, 'otkazov': 0, 'perespros': 0}

    def zapisat(p, otvety, popytok):
        for i, z in enumerate(p):
            o = otvety[i] if i < len(otvety) else {}
            est = bool(o.get('sreda'))
            gotovo.append({**{k: z.get(k) for k in kolonki if k != 'vopros'},
                           'sreda': o.get('sreda') if est else 'ответа не было',
                           'pochemu': (o.get('pochemu') or
                                       f'провайдер не ответил за {popytok} попыток')[:300],
                           'uverennost': (o.get('uverennost') or 'низкая') if est
                           else 'ответа не было'})

    def rabota(nomer):
        while True:
            with zamok:
                if not pachki:
                    return
                p = pachki.pop()
            otvety, popytok = [], 0
            ochered = [p]
            while ochered:
                kusok = ochered.pop()
                popytok += 1
                o = sprosit([z['vopros'] for z in kusok], chto)
                if o:
                    with zamok:
                        zapisat(kusok, o, popytok)
                    continue
                if len(kusok) > 2:                      # режем пополам и пробуем ещё раз
                    with zamok:
                        schet['perespros'] += 1
                    ochered += [kusok[:len(kusok) // 2], kusok[len(kusok) // 2:]]
                else:
                    with zamok:
                        schet['otkazov'] += len(kusok)
                        zapisat(kusok, [], popytok)
            with zamok:
                schet['n'] += 1
                if schet['n'] % 5 == 0 or not pachki:
                    c = Counter(g['sreda'] for g in gotovo)
                    print(f'  пачек {schet["n"]}/{vsego}: {dict(c)} '
                          f'| переспросов {schet["perespros"]}, без ответа {schet["otkazov"]}',
                          flush=True)

    ni = [threading.Thread(target=rabota, args=(i,), daemon=True) for i in range(potokov)]
    for t in ni:
        t.start()
    for t in ni:
        t.join()
    polya = [k for k in kolonki if k != 'vopros'] + ['sreda', 'pochemu', 'uverennost']
    klyuch = polya[0]
    staroe = {}
    if os.path.exists(vyhod):
        for r in csv.DictReader(open(vyhod, encoding='utf-8-sig'), delimiter=';'):
            staroe[r[klyuch]] = r
    for g in gotovo:                     # свежий ответ вытесняет прежний отказ
        staroe[str(g[klyuch])] = g
    with open(vyhod, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=polya, delimiter=';', extrasaction='ignore')
        w.writeheader()
        for g in staroe.values():
            w.writerow(g)
    gotovo = list(staroe.values())
    subprocess.run(['bash', os.path.join(BAZA, 'server', 'drop_client.sh'), 'up', vyhod],
                   capture_output=True, timeout=900)
    c = Counter(g['sreda'] for g in gotovo)
    print(f'→ {vyhod} ({len(gotovo)}), выложено на дроп')
    print(f'   ответы: {dict(c)}')
    print(f'   провайдер не ответил по {c.get("ответа не было", 0)} позициям — их надо переспросить')
    return gotovo


def shag_marki():
    """Каждой неизвестной марке показать ВСЕ её контексты в корпусе, включая те, где среда есть."""
    fakty = [x for x in chitat() if x['tip_mashiny'] in NASH]
    konteksty = defaultdict(list)
    nuzhny = Counter()
    for x in fakty:
        for m in marki_iz(x):
            konteksty[m].append(x)
            if x['sreda_mashiny'] == NE_NAZVANA:
                nuzhny[m] += 1
    est = uzhe_otvecheno(PO_MARKAM, 'marka')
    zadaniya = []
    for m, n in nuzhny.most_common():
        if m in est:                    # уже разобрано в прошлый заход, не тратим вызов
            continue
        k = konteksty[m]
        # сначала контексты, где среда УЖЕ названа: они самые информативные
        k = sorted(k, key=lambda x: 0 if x['sreda_mashiny'] != NE_NAZVANA else 1)[:4]
        stroki = ' // '.join(f"{(x.get('predpriyatie') or '')[:34]}: {(x.get('tekst') or '')[:230]}"
                             for x in k)
        zadaniya.append({'marka': m, 'fakty': n,
                         'vopros': f'Марка «{m}». Контексты: {stroki}'.replace('\n', ' ')})
    print(f'марок к разбору: {len(zadaniya)}, уже разобрано раньше: {len(est)} '
          f'(всего упоминаний {sum(nuzhny.values())})')
    pachkami(zadaniya, 'обозначения машин', PO_MARKAM, ['marka', 'fakty', 'vopros'])


def shag_predpriyatiya():
    """Предприятия, у чьих безсредных фактов нет марок вовсе: решаем по роду деятельности."""
    fakty = [x for x in chitat() if x['tip_mashiny'] in NASH]
    po_inn = defaultdict(list)
    for x in fakty:
        if x['sreda_mashiny'] == NE_NAZVANA and not marki_iz(x):
            po_inn[x['inn']].append(x)
    est = uzhe_otvecheno(PO_PRED, 'inn')
    zadaniya = []
    for inn, v in sorted(po_inn.items(), key=lambda kv: -len(kv[1])):
        if inn in est:
            continue
        imya = (v[0].get('predpriyatie') or '')[:70]
        stroki = ' // '.join((x.get('tekst') or '')[:200] for x in v[:4])
        zadaniya.append({'inn': inn, 'predpriyatie': imya, 'fakty': len(v),
                         'vopros': f'Предприятие «{imya}». Записи о его центробежных машинах: '
                                   f'{stroki}'.replace('\n', ' ')})
    print(f'предприятий к разбору: {len(zadaniya)} (закрывают '
          f'{sum(len(v) for v in po_inn.values())} фактов)')
    pachkami(zadaniya, 'предприятия и их машины', PO_PRED,
             ['inn', 'predpriyatie', 'fakty', 'vopros'])


PEREVOD = {'воздух': 'воздух', 'газ': 'газ или иная среда', 'оба': 'воздух и газ названы оба',
           'не ясно': 'среда не установлена'}


def shag_primenit():
    fakty = chitat()
    c = [x for x in fakty if x['tip_mashiny'] in NASH]

    po_marke, po_marke_inn = defaultdict(Counter), defaultdict(lambda: defaultdict(Counter))
    for x in c:
        s = x['sreda_mashiny']
        if s == NE_NAZVANA:
            continue
        for m in marki_iz(x):
            po_marke[m][s] += 1
            po_marke_inn[x['inn']][m][s] += 1

    tabl_m, tabl_p = {}, {}
    if os.path.exists(PO_MARKAM):
        for r in csv.DictReader(open(PO_MARKAM, encoding='utf-8-sig'), delimiter=';'):
            s = PEREVOD.get(r['sreda'])
            if s and s != 'среда не установлена' and r['uverennost'] != 'низкая':
                tabl_m[r['marka']] = s
    if os.path.exists(PO_PRED):
        for r in csv.DictReader(open(PO_PRED, encoding='utf-8-sig'), delimiter=';'):
            s = PEREVOD.get(r['sreda'])
            if s and s != 'среда не установлена' and r['uverennost'] != 'низкая':
                tabl_p[r['inn']] = s

    otkuda = Counter()
    for x in fakty:
        if x['tip_mashiny'] not in NASH:
            x['sreda_otkuda'] = ''
            continue
        if x['sreda_mashiny'] != NE_NAZVANA:
            x['sreda_otkuda'] = 'сказано прямо в тексте'
            otkuda['сказано прямо в тексте'] += 1
            continue
        mm = marki_iz(x)
        nashli = None
        for m in mm:                                        # канал 2
            d = po_marke_inn[x['inn']].get(m)
            if d:
                nashli = (d.most_common(1)[0][0], f'та же марка {m} у этого же предприятия')
                break
        if not nashli:
            for m in mm:                                    # канал 3
                d = po_marke.get(m)
                if d and len(d) == 1:
                    nashli = (d.most_common(1)[0][0], f'марка {m} однозначна по всему корпусу')
                    break
        if not nashli:
            for m in mm:                                    # канал 4а
                if m in tabl_m:
                    nashli = (tabl_m[m], f'провайдер разобрал обозначение {m}')
                    break
        if not nashli and x['inn'] in tabl_p:               # канал 4б
            nashli = (tabl_p[x['inn']], 'провайдер определил по роду деятельности предприятия')
        if nashli:
            x['sreda_mashiny'], x['sreda_otkuda'] = nashli
        else:
            x['sreda_mashiny'], x['sreda_otkuda'] = 'среда не установлена', ''
        otkuda[x['sreda_otkuda'] or 'не закрылось ничем'] += 1

    cols = list(fakty[0].keys())
    if 'sreda_otkuda' not in cols:
        cols.append('sreda_otkuda')
    with open(FAKTY, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=cols, delimiter=';', extrasaction='ignore')
        w.writeheader()
        for x in fakty:
            w.writerow(x)

    pf = [x for x in csv.DictReader(open(FAKTY, encoding='utf-8-sig'), delimiter=';')
          if x['tip_mashiny'] in NASH]
    print(f'центробежных фактов: {len(pf)}')
    print('  среда:', dict(Counter(x['sreda_mashiny'] for x in pf).most_common()))
    print('  откуда узнали:')
    for k, v in otkuda.most_common():
        print(f'     {v:>6}  {k}')
    inn = defaultdict(set)
    for x in pf:
        inn[x['inn']].add(x['sreda_mashiny'])
    vozd = {i for i, s in inn.items() if any(str(y).startswith('воздух') for y in s)}
    gaz = {i for i, s in inn.items() if s == {'газ или иная среда'}}
    print(f'  предприятий всего {len(inn)}: с воздухом {len(vozd)}, чисто газовых {len(gaz)}, '
          f'без среды {len(inn) - len(vozd) - len(gaz)}')
    subprocess.run(['bash', os.path.join(BAZA, 'server', 'drop_client.sh'), 'up', FAKTY],
                   capture_output=True, timeout=1800)
    print('выложено на дроп → SVOD-tri-sostoyaniya.csv')


if __name__ == '__main__':
    if '--marki' in sys.argv:
        shag_marki()
    elif '--predpriyatiya' in sys.argv:
        shag_predpriyatiya()
    elif '--primenit' in sys.argv:
        shag_primenit()
    else:
        print(__doc__)

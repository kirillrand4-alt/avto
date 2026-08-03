# -*- coding: utf-8 -*-
"""Широкий проход по реестру ЭПБ ради НОВЫХ предприятий.

Вывод пришёл от второй сессии и попал в меня: мой реестр ходит по нашим 1 853 ИНН, значит
структурно не может найти предприятие вне списка. «Новых ноль» было бы свойством метода, а
не замером — ровно та ошибка, которую они у себя сняли.

Проба на 16 страницах: 74 предприятия, из них 3 НЕ в нашем списке. Здесь то же самое, но по
всему словарю машин и вглубь.

Пишет построчно, продолжает с места остановки. Реестру больно не делаем: одна страница за
раз, пауза как у остальных проходов.
"""
import json, os, re, sys, time, urllib.parse
sys.path.insert(0, '/home/user/avto/seo-texts')
import mpb_po_inn as M

SLOVA = ['центробежный компрессор', 'компрессор центробежный', 'турбокомпрессор',
         'воздуходувка', 'турбовоздуходувка', 'нагнетатель воздуха', 'газодувка',
         'турбогазодувка', 'компрессорная установка', 'воздушный компрессор']
POTOK = 'epb-shirokiy.jsonl'
CUST = re.compile(r'href="/customer/(\d+)"')
STRANIC = int(os.environ.get('STRANIC', '40'))

nashi = {x.strip() for x in open('inn-vse-celi.txt') if x.strip()}
gotovo = set()
if os.path.exists(POTOK):
    for ln in open(POTOK, encoding='utf-8'):
        try:
            z = json.loads(ln)
            gotovo.add((z['slovo'], z['stranica']))
        except Exception:  # noqa: BLE001
            pass
f = open(POTOK, 'a', encoding='utf-8')
vse, novye = {}, {}
for slovo in SLOVA:
    for st in range(1, STRANIC + 1):
        if (slovo, st) in gotovo:
            continue
        qs = {'q': slovo, 'type': 'ТУ'}
        if st > 1:
            qs['page'] = st
        h = M._vzyat(f'{M.BAZA}/conclusions?' + urllib.parse.urlencode(qs), popytok=2)
        if h.startswith('__ОШИБКА__'):
            f.write(json.dumps({'slovo': slovo, 'stranica': st, 'err': h[:70],
                                'stroki': []}, ensure_ascii=False) + '\n')
            break
        stroki = []
        for tr in M.TR.findall(h):
            c = CUST.search(tr)
            if not c:
                continue
            e = M.EKSPL.search(tr)
            o = M.OBEKT.search(tr)
            n = M.NOMER.search(tr)
            ob = (o.group(1) if o else '')
            stroki.append({'inn': c.group(1),
                           'predpriyatie': (e.group(2) if e else '')[:90],
                           'obekt': ob[:220], 'nomer': n.group(2).strip() if n else '',
                           'centrobezhnoe': 'да' if (M.CENTRO.search(ob)
                                                     and not M.NASOS.search(ob)
                                                     and not M.NE_MASHINA.search(ob)) else '',
                           'sreda': M.sreda(ob)})
        f.write(json.dumps({'slovo': slovo, 'stranica': st, 'err': '',
                            'stroki': stroki}, ensure_ascii=False) + '\n')
        for r in stroki:
            vse[r['inn']] = r
            if r['inn'] not in nashi:
                novye[r['inn']] = r
        if not stroki:
            break
        f.flush()
        if st % 10 == 0:
            os.fsync(f.fileno())
            print(f'  {slovo}: стр {st}, всего предприятий {len(vse)}, НОВЫХ {len(novye)}',
                  file=sys.stderr, flush=True)
        time.sleep(0.4)
    print(f'{slovo}: готово, предприятий {len(vse)}, новых {len(novye)}',
          file=sys.stderr, flush=True)
f.close()
print(f'\nвсего предприятий в реестре по словарю: {len(vse)} | НЕТ В НАШЕМ СПИСКЕ: {len(novye)}',
      file=sys.stderr)
c = {k: v for k, v in novye.items() if v['centrobezhnoe']}
print(f'из новых с ДОКАЗАННОЙ центробежной машиной: {len(c)}', file=sys.stderr)
import csv
with open('EPB-NOVYE-PREDPRIYATIYA.csv', 'w', encoding='utf-8-sig', newline='') as g:
    w = csv.DictWriter(g, fieldnames=['inn', 'predpriyatie', 'obekt', 'centrobezhnoe',
                                      'sreda', 'nomer'], delimiter=';', extrasaction='ignore')
    w.writeheader()
    w.writerows(sorted(novye.values(), key=lambda x: (not x['centrobezhnoe'], x['inn'])))

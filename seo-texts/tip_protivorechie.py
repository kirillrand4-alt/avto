# -*- coding: utf-8 -*-
"""Две взаимоисключающие метки типа машины в одном поле: замер по всей базе.

НАХОДКА 1-Й СЕССИИ, ЗАМЕР МОЙ. Они смотрели глазами 15 карточек и увидели: 11 из 15 несут в
типе машины «центробежная | не установлен» или «центробежная | поршневая или винтовая» — две
метки, которые не могут быть верны одновременно. Правило чистки они не писали и по всей базе
не мерили, а разметчик фактов мой, поэтому беру.

ПОЧЕМУ ЭТО НЕ КОСМЕТИКА. Поле типа читает и человек в карточке, и модель приоритета. Строка
«центробежная | поршневая или винтовая» для человека — шум, а для расчёта соответствия ещё и
развилка: возьмёшь первое — предприятие в цели, возьмёшь второе — в отсев. Пока метки лежат
вместе, ответ зависит от того, кто как разберёт строку, а это худший вид неопределённости:
её не видно.

ЧТО СЧИТАЕТСЯ. По каждому факту из поля типа вынимаются все названные типы и сверяются с
вердиктом РАЗМЕТЧИКА ПО ТЕКСТУ цитаты (`musor_faktov`). Четыре исхода:

    согласны            — поле и текст говорят одно;
    поле шире текста    — в поле метка есть, в тексте подтверждения нет (это не ошибка,
                          доказательство могло прийти из другого места);
    ПОЛЕ ПРОТИВОРЕЧИТ   — в поле стоят два несовместимых типа сразу;
    текст против поля   — текст прямо называет тип, которого в поле нет, или наоборот.

Ничего не переписывается: модуль называет, а решение по правке принимается отдельно и с
бэкапом. Слово владельца — разделять, а не отсеивать.

Запуск: python3 tip_protivorechie.py
"""
import base64
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'server'))
import run_on_server as R  # noqa: E402

TUT = os.path.dirname(os.path.abspath(__file__))

SCRIPT = r'''
# -*- coding: utf-8 -*-
import collections, json, re, sqlite3, sys
sys.path.insert(0, r'C:\sender\_ops')
import _3s_musor_faktov as M

cx = sqlite3.connect(r'C:\seostat\data\centrifugal.db')
kol = [r[1] for r in cx.execute('pragma table_info(fact)')]
pole = 'equipment_type' if 'equipment_type' in kol else ''
if not pole:
    print('ИТОГ ' + json.dumps({'ошибка': 'в fact нет equipment_type', 'поля': kol[:20]},
                               ensure_ascii=False)); sys.exit()

CENTRO = re.compile(r'центробежн|турбокомпрессор', re.I)
OBEMN = re.compile(r'поршнев|винтов|роторн|спиральн|мембранн|вихрев', re.I)
NEUST = re.compile(r'не\s*установл|неизвестн|не\s*определ', re.I)

sch = collections.Counter()
primery = collections.defaultdict(list)
po_inn = collections.defaultdict(collections.Counter)

for inn, tip, quote in cx.execute(
        "select coalesce(inn,''), coalesce(%s,''), coalesce(quote,'') from fact" % pole):
    t = (tip or '').strip()
    if not t:
        sch['поле пустое'] += 1
        continue
    c, o, n = bool(CENTRO.search(t)), bool(OBEMN.search(t)), bool(NEUST.search(t))
    vid, _ = M.razobrat(quote, tip)
    tekst_nash = vid in (M.VID_NASH, M.VID_NASH_PO_MARKE, M.VID_MARKA_SREDA)
    tekst_chuzhoy = vid == M.VID_CHUZHOY_TIP
    if c and o:
        r = 'ПОЛЕ ПРОТИВОРЕЧИТ: центробежная и объёмная сразу'
    elif c and n:
        r = 'ПОЛЕ ПРОТИВОРЕЧИТ: центробежная и «не установлен» сразу'
    elif o and n:
        r = 'ПОЛЕ ПРОТИВОРЕЧИТ: объёмная и «не установлен» сразу'
    elif c and tekst_chuzhoy:
        r = 'текст против поля: поле центробежная, текст называет чужой тип'
    elif o and tekst_nash:
        r = 'текст против поля: поле объёмная, текст доказывает нашу машину'
    elif (c and tekst_nash) or (o and tekst_chuzhoy):
        r = 'согласны'
    else:
        r = 'поле шире текста: подтверждения в цитате нет'
    sch[r] += 1
    po_inn[inn][r] += 1
    if len(primery[r]) < 3:
        primery[r].append({'inn': inn, 'pole': t[:70], 'vid_po_tekstu': vid,
                           'citata': (quote or '')[:100]})

# Предприятия, у которых противоречие есть хоть в одном факте: их карточка врёт человеку.
protiv = [i for i, c in po_inn.items()
          if any(k.startswith('ПОЛЕ ПРОТИВОРЕЧИТ') for k in c)]
imena = dict(cx.execute("select inn, coalesce(predpriyatie,'') from company"))

for r, pr in primery.items():
    for z in pr:
        print('PRIM %s\t%s' % (r, json.dumps(z, ensure_ascii=False)))
for s in sorted(sch.items(), key=lambda x: -x[1]):
    print('REC %s\t%d' % s)
print('ИТОГ ' + json.dumps({
    'фактов': sum(sch.values()),
    'предприятий_с_противоречием_в_поле': len(protiv),
    'примеры_предприятий': [{'inn': i, 'imya': imena.get(i, '')[:50]} for i in protiv[:12]],
}, ensure_ascii=False))
'''


def main():
    fajly = [{'dest': r'C:\sender\_ops\_3s_musor_faktov.py',
              'b64': base64.b64encode(
                  open(os.path.join(TUT, 'musor_faktov.py'), encoding='utf-8')
                  .read().encode()).decode()},
             {'dest': r'C:\sender\_ops\3s_tip_protiv.py',
              'b64': base64.b64encode(SCRIPT.encode()).decode()}]
    R.submit('enrich_contacts', {'op': 'panel_file_put', 'files': fajly}, timeout=300)
    r = R.submit('enrich_contacts', {'op': 'panel_py', 'script': r'C:\sender\_ops\3s_tip_protiv.py',
                                     'argv': [], 'timeout': 900}, timeout=1200)
    d = r.get('data') or {}
    hvost = d.get('stdout_tail') or ''
    if not hvost:
        print('пусто:', (d.get('stderr_tail') or '')[-1500:], file=sys.stderr)
        return
    for s in hvost.splitlines():
        s = s.strip()
        if s.startswith('REC '):
            print(s[4:].replace('\t', '  ×'))
        elif s.startswith('PRIM '):
            print('  ' + s[5:])
        elif s.startswith('ИТОГ '):
            print(json.dumps(json.loads(s[5:]), ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()

# -*- coding: utf-8 -*-
"""Сколько фактов доказывают нашу машину ТОЛЬКО маркой — и что мы из-за этого теряли.

ОТКУДА ВОПРОС. Просмотр 15 случайных карточек (пункт владельца «смотреть глазами») дал
находку, которую никакой счётчик бы не дал: у ПАО «Юнипро» стояло «ни один видимый факт не
доказывает нашу машину», а факт читался «Поставка запасных частей к компрессору К-250-61-5».
К-250-61-5 — центробежный воздушный компрессор, он есть в НАШЕМ ЖЕ проверенном словаре марок.
Доказательство лежало в тексте, было опознано соседним модулем и не засчитывалось ничем:
разметчик мусора искал слова, а не марки.

Цена ошибки не в одной карточке. Степень соответствия в модели приоритета берётся по фактам:
«центробежная и воздух, доказано текстом» даёт множитель 1.00, «тип не установлен» — 0.30.
Предприятие с доказанной маркой машиной проваливалось в приоритете втрое, то есть уходило вниз
очереди звонков. Замер ниже отвечает, скольких это касается.

ЧТО СЧИТАЕТСЯ. По каждому факту базы панели разметчик зовётся дважды: как раньше (только
слова) и с маркой. Разница и есть ответ. Четыре разряда:
    словом И маркой   — доказано дважды, провенанс накапливается (правило владельца);
    только словом     — как было;
    ТОЛЬКО МАРКОЙ     — то, что мы теряли;
    ни слова, ни марки — судить не по чему.
Отдельно считаются предприятия, у которых ВСЁ доказательство держится на марке: для них
исправление меняет приоритет, а не просто ярлык факта.

Запуск: python3 marka_dokazatelstvo.py
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
import collections, json, sqlite3, sys
sys.path.insert(0, r'C:\sender\_ops')
import _3s_musor_faktov as M

cx = sqlite3.connect(r'C:\seostat\data\centrifugal.db')
kol = [r[1] for r in cx.execute('pragma table_info(fact)')]
pole_tip = 'equipment_type' if 'equipment_type' in kol else ''
zapros = ('select coalesce(inn,\'\'), coalesce(quote,\'\')'
          + (', coalesce(%s,\'\')' % pole_tip if pole_tip else ', \'\'')
          + ' from fact')

sch = collections.Counter()
po_inn = collections.defaultdict(collections.Counter)
primery = collections.defaultdict(list)

for inn, quote, tip in cx.execute(zapros):
    q = (quote or '').strip()
    if not q:
        sch['текста нет'] += 1
        po_inn[inn]['пусто'] += 1
        continue
    slovom = M._nasha_mashina(q) is not None
    mk, sreda = M._marka(q)
    vid, pochemu = M.razobrat(q, tip)
    # Слово и марка считаются ДО отмен (чужой контекст, чужой тип): нас интересует, что
    # вообще есть в тексте, а решение по факту уже принял razobrat и оно ниже отдельно.
    if slovom and mk:
        r = 'словом И маркой'
    elif slovom:
        r = 'только словом'
    elif mk:
        r = 'ТОЛЬКО МАРКОЙ (' + sreda + ')'
    else:
        r = 'ни слова, ни марки'
    sch[r] += 1
    sch['вердикт: ' + vid] += 1
    po_inn[inn][r] += 1
    if len(primery[r]) < 3:
        primery[r].append({'inn': inn, 'tekst': q[:110], 'marka': mk, 'vid': vid})

# Предприятия, где доказательство держится ТОЛЬКО на марке: ни один факт не доказан словом,
# но хотя бы один доказан маркой. Именно у них исправление двигает приоритет.
tolko_marka, tolko_marka_vozduh = [], []
for inn, c in po_inn.items():
    if c['только словом'] or c['словом И маркой']:
        continue
    mk_v = c['ТОЛЬКО МАРКОЙ (воздух)']
    mk_g = c['ТОЛЬКО МАРКОЙ (газ)']
    if mk_v or mk_g:
        tolko_marka.append(inn)
        if mk_v:
            tolko_marka_vozduh.append(inn)

# Имя колонки НЕ УГАДЫВАЕТСЯ. На этом уже спотыкались трижды: `name`, `company`,
# `istochnikov` — каждый раз задание падало на середине, а не отдавало частичный результат.
kol_c = [r[1] for r in cx.execute('pragma table_info(company)')]
pole_imya = next((k for k in ('company_name', 'name', 'title', 'org', 'short_name')
                  if k in kol_c), '')
imena = (dict(cx.execute('select inn, coalesce("%s", \'\') from company' % pole_imya))
         if pole_imya else {})
# ПРИМЕРЫ ПЕЧАТАЮТСЯ ПЕРВЫМИ, СЧЁТЧИКИ ПОСЛЕДНИМИ. Хвост раннера режет НАЧАЛО вывода, и
# первый прогон отдал одни примеры: цифры, ради которых всё и считалось, срезало молча.
for r, pr in primery.items():
    for z in pr:
        print('PRIM %s\t%s' % (r, json.dumps(z, ensure_ascii=False)))
for s in sorted(sch.items(), key=lambda x: -x[1]):
    print('REC %s\t%d' % s)
print('ИТОГ ' + json.dumps({
    'фактов_всего': sum(v for k, v in sch.items() if not k.startswith('вердикт')),
    'предприятий_с_фактами': len(po_inn),
    'предприятий_доказательство_ТОЛЬКО_марка': len(tolko_marka),
    'из_них_марка_воздушная': len(tolko_marka_vozduh),
    'примеры_предприятий': [{'inn': i, 'name': imena.get(i, '')[:60]}
                            for i in tolko_marka_vozduh[:20]],
}, ensure_ascii=False))
'''


def main():
    fajly = [{'dest': r'C:\sender\_ops\_3s_musor_faktov.py',
              'b64': base64.b64encode(
                  open(os.path.join(TUT, 'musor_faktov.py'), encoding='utf-8')
                  .read().encode()).decode()},
             {'dest': r'C:\sender\_ops\3s_marka_dok.py',
              'b64': base64.b64encode(SCRIPT.encode()).decode()}]
    R.submit('enrich_contacts', {'op': 'panel_file_put', 'files': fajly}, timeout=300)
    r = R.submit('enrich_contacts', {'op': 'panel_py', 'script': r'C:\sender\_ops\3s_marka_dok.py',
                                     'argv': [], 'timeout': 900}, timeout=1200)
    d = r.get('data') or {}
    hvost = d.get('stdout_tail') or ''
    # КАКОЙ КОНЕЦ РЕЖЕТСЯ — НЕ ДОГАДКА, А ЗАМЕР. Первый прогон отдал только примеры, хотя они
    # печатаются ПЕРЕД счётчиками: значит поле отдаёт НАЧАЛО вывода, а не хвост, вопреки имени.
    print(f'[получено {len(hvost)} знаков, строк {len(hvost.splitlines())}, '
          f'rc={d.get("rc")}]', file=sys.stderr)   # ключ ответа `rc`, не `returncode`
    if not hvost:
        print('пусто. stderr:', (d.get('stderr_tail') or '')[-2000:], file=sys.stderr)
        return
    # Печать построчно с маркером — иначе хвост раннера срезает НАЧАЛО вывода и счётчики
    # молча теряются. На этом уже спотыкались: обрезка не ошибка, она просто отдаёт меньше.
    for s in hvost.splitlines():
        s = s.strip()
        if s.startswith('REC '):
            print(s[4:].replace('\t', '  ×'))
        elif s.startswith('ИТОГ '):
            print(json.dumps(json.loads(s[5:]), ensure_ascii=False, indent=1))
        elif s.startswith('PRIM '):
            print('  ' + s[5:])


if __name__ == '__main__':
    main()

# -*- coding: utf-8 -*-
"""Площадки — В ПАРК: перевод собранного с ТЭК-Торга, Росэлторга и РТС в схему приёмника.

ЗАЧЕМ. Собранное лежит тремя файлами со СВОИМИ именами полей, а приёмник парка читает
`predmet`, `inn`, `zakazchik`, `istochniki`. Пока перевода нет, данные есть, а в парк они не
попадают — ровно тот случай, который 1-я сессия назвала у себя: её приёмник знал одно имя
поля и выбросил 66 живых строк Росэлторга, а после починки они дали 15 новых предприятий.

ЧТО ПЕРЕВОДИТСЯ (живые файлы, имена печатаются с их размерами):

    PARK-TEKTORG-ZAKUPKI-3S.jsonl     поле `zakupka`  -> predmet
    PARK-ROSELTORG-ZAKUPKI-3S.jsonl   поле `zakupka`  -> predmet
    PARK-RTS-PODTV-3S.jsonl           поле `nazvanie` / `predmet`

Ссылки НЕ ТЕРЯЮТСЯ: `istochniki` переносится как есть, а если его нет — собирается из
ссылки на карточку и ссылки на выдачу. Строка без ссылки в парк не идёт (правило владельца).

ЗАСЛОН НА ПЕРЕВОД, а не на источник: если в предмете нет слова нашей машины, строка
отбрасывается здесь же и считается — приёмник парка проверит это ещё раз своим словарём,
и два счёта должны сойтись.

Числа в КОНЦЕ.
"""
import collections
import io
import json
import os
import re
import urllib.request

SCRATCH = os.environ.get('P25_SCRATCH', '.')
VHODY = [('PARK-TEKTORG-ZAKUPKI-3S.jsonl', 'ТЭК-Торг'),
         ('PARK-ROSELTORG-ZAKUPKI-3S.jsonl', 'Росэлторг'),
         ('PARK-RTS-PODTV-3S.jsonl', 'РТС-тендер')]
VYHOD = os.path.join(SCRATCH, 'PARK-PLOSHCHADKI-DLYA-PARKA-3S.jsonl')
MASH = re.compile(r'компрессор|воздуходув|нагнетател|осушител|азотн|кислородн|'
                  r'воздухоразделит|ГПА', re.I)
drop = os.environ.get('DROP_URL', '').rstrip('/')
tok = {'X-Drop-Token': os.environ.get('DROP_TOKEN', '')}
op = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def s_dropa(imya):
    try:
        rq = urllib.request.Request('%s/%s' % (drop, imya), headers=tok)
        return op.open(rq, timeout=180).read().decode('utf-8', 'replace')
    except Exception:  # noqa: BLE001
        return ''


sch = collections.Counter()
stroki = []
for imya, ploshchadka in VHODY:
    put = os.path.join(SCRATCH, imya)
    syr = (io.open(put, encoding='utf-8').read() if os.path.exists(put) else s_dropa(imya))
    if not syr:
        sch['НЕТ ФАЙЛА: %s' % imya] += 1
        continue
    sch['%s: строк на входе' % ploshchadka] = len(syr.splitlines())
    for s in syr.splitlines():
        try:
            o = json.loads(s)
        except Exception:  # noqa: BLE001
            continue
        pred = str(o.get('zakupka') or o.get('predmet') or o.get('nazvanie')
                   or o.get('nazvanie_zakupki') or '')
        if not MASH.search(pred):
            sch['%s: в предмете нет нашей машины' % ploshchadka] += 1
            continue
        us = [u for u in str(o.get('istochniki') or '').split(' | ') if u.startswith('http')]
        for k in ('ssylka_kartochki', 'ssylka_vydachi', 'karta', 'ssylka'):
            u = str(o.get(k) or '')
            if u.startswith('http') and u not in us:
                us.append(u)
        if not us:
            sch['%s: ссылки нет — в парк не идёт' % ploshchadka] += 1
            continue
        inn = str(o.get('inn') or '').strip()
        if not inn.isdigit():
            sch['%s: ИНН на карточке не напечатан' % ploshchadka] += 1
            continue
        stroki.append({'inn': inn,
                       'predmet': pred[:250],
                       'zakazchik': str(o.get('zakazchik') or o.get('organizator')
                                        or o.get('predpriyatie') or '')[:200],
                       'nomer': str(o.get('nomer') or o.get('nomer_zakupki') or ''),
                       'istochniki': ' | '.join(us),
                       'istochnikov': len(us),
                       'inn_otkuda': str(o.get('inn_otkuda')
                                         or 'стоит после слова ИНН на карточке площадки'),
                       'slovo_podtverzhdeno_tekstom': True,
                       'kto': '3-я сессия, площадка %s' % ploshchadka})
        sch['%s: ПЕРЕВЕДЕНО в схему парка' % ploshchadka] += 1

with io.open(VYHOD, 'w', encoding='utf-8') as f:
    for z in stroki:
        f.write(json.dumps(z, ensure_ascii=False) + '\n')
try:
    rq = urllib.request.Request('%s/%s' % (drop, os.path.basename(VYHOD)),
                                data=io.open(VYHOD, 'rb').read(), method='PUT', headers=tok)
    vyl = op.open(rq, timeout=300).read().decode('utf-8', 'replace')[:70]
except Exception as e:  # noqa: BLE001
    vyl = 'НЕ ВЫЛОЖЕНО: %s' % str(e)[:50]

print('\n\n########## ЧИСЛА')
for k, v in sch.most_common():
    print('  %-52s %5d' % (k[:52], v))
print('  строк на выход                                    %5d' % len(stroki))
print('  разных ИНН                                        %5d'
      % len({z['inn'] for z in stroki}))
print('  выложено: %s' % vyl)
print('ИТОГ ' + json.dumps({'переведено': len(stroki),
                            'ИНН': len({z['inn'] for z in stroki})}, ensure_ascii=False))

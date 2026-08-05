# -*- coding: utf-8 -*-
"""Сколько входа обратного хода ещё НЕ пройдено. Чтобы не жечь пул впустую.

Вход развалился (vhod не нашёл серверные CSV). 2-я сессия выложила на дроп готовый
вход: DLYA-3S-obratnyy-hod-FIO-bez-nomera.csv. Прежде чем гнать прогон и тратить общий
xmlriver-пул, считаю: сколько пар «ФИО + ИНН» из этого входа ЕЩЁ НЕ стоят в потоке
p25-obratnyy.jsonl. Ноль непройденных — обратный ход по этому входу исчерпан, и прогон
был бы пустой тратой пула. Печатаю числа.
"""
import collections
import csv
import io
import json
import os
import re
import urllib.request

POTOK = r'C:\sender\_ops\p25-obratnyy.jsonl'
VHOD_IMENA = ['DLYA-3S-obratnyy-hod-FIO-bez-nomera.csv', 'DLYA-3S-180-INN-s-imenami.csv',
              'P25-LYUDI-2S-038.csv']


def yadro_fio(s):
    """Ядро ФИО: фамилия + первая буква имени, без регистра и ё/е."""
    slova = [w for w in re.split(r'[^А-Яа-яЁёA-Za-z]+', str(s or '')) if len(w) > 1]
    if not slova:
        return ''
    fam = max(slova, key=len).lower().replace('ё', 'е')
    ini = ''.join(sorted(w[0].lower().replace('ё', 'е') for w in slova
                         if w.lower() != fam)[:1])
    return fam + ini


def skачать(imya):
    url = os.environ.get('DROP_URL', '').rstrip('/')
    tok = os.environ.get('DROP_TOKEN', '')
    if not url or not tok:
        return b''
    rq = urllib.request.Request('%s/%s' % (url, imya), headers={'X-Drop-Token': tok})
    try:
        with urllib.request.urlopen(rq, timeout=120) as r:
            return r.read()
    except Exception as e:  # noqa: BLE001
        print('  не скачался %s: %s' % (imya, str(e)[:50]))
        return b''


# 1) Что уже в потоке: пары (ИНН, ядро ФИО).
proydeno = set()
inn_v_potoke = set()
if os.path.exists(POTOK):
    for s in io.open(POTOK, encoding='utf-8', errors='replace'):
        try:
            z = json.loads(s)
        except Exception:  # noqa: BLE001
            continue
        inn = str(z.get('inn') or z.get('ИНН') or '')
        fio = z.get('fio') or z.get('chelovek') or z.get('person') or ''
        if not fio:
            for k in ('lyudi', 'kontakty', 'naydeno'):
                v = z.get(k)
                if isinstance(v, list):
                    for it in v:
                        if isinstance(it, dict):
                            f = it.get('fio') or it.get('chelovek') or ''
                            if f:
                                proydeno.add((inn, yadro_fio(f)))
        if inn:
            inn_v_potoke.add(inn)
        if fio:
            proydeno.add((inn, yadro_fio(fio)))
print('в потоке: пар ИНН+ФИО %d, разных ИНН %d' % (len(proydeno), len(inn_v_potoke)))

# 2) Вход от 2-й сессии: сколько пар и сколько из них НЕ пройдено.
svod = {}
for imya in VHOD_IMENA:
    syroy = skачать(imya)
    if not syroy:
        svod[imya] = 'не скачался'
        continue
    tekst = syroy.decode('utf-8-sig', 'replace')
    r = csv.DictReader(io.StringIO(tekst), delimiter=';' if tekst[:400].count(';') >
                       tekst[:400].count(',') else ',')
    vsego = novyh = 0
    novyh_inn = set()
    for row in r:
        low = {k.lower().strip(): v for k, v in row.items() if k}
        inn = ''
        for k in ('inn', 'инн'):
            if low.get(k):
                inn = re.sub(r'\D', '', low[k])
                break
        fio = ''
        for k in ('chelovek', 'фио', 'fio', 'name', 'имя', 'person', 'dolzhnostnoe_lico'):
            if low.get(k):
                fio = low[k]
                break
        if not fio:
            continue
        vsego += 1
        klyuch = (inn, yadro_fio(fio))
        if klyuch not in proydeno and (inn, yadro_fio(fio)) not in proydeno:
            novyh += 1
            if inn:
                novyh_inn.add(inn)
    svod[imya] = {'строк_с_ФИО': vsego, 'НЕ пройдено': novyh,
                  'новых ИНН': len(novyh_inn)}
    print('  %-42s строк %-6d НЕ пройдено %-6d новых ИНН %d'
          % (imya, vsego, novyh, len(novyh_inn)))

itog_novyh = sum(v['НЕ пройдено'] for v in svod.values() if isinstance(v, dict))
print('ИТОГ ' + json.dumps({'всего НЕ пройдено пар': itog_novyh,
                            'по файлам': svod}, ensure_ascii=False))

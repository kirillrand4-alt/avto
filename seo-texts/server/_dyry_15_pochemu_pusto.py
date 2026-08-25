# -*- coding: utf-8 -*-
"""Почему паспорт пуст: чужой сайт или мусор в тексте?

Два замера:
 1) verified у пустых карточек против карточек с фактами (подтверждён ли сайт ИНН);
 2) доля CSS/JS-мусора в тексте, который реально уходит модели (_stranicy),
    у пустых против непустых.
Только чтение.
"""
import json
import random
import re
import sqlite3
import sys

sys.path.insert(0, r'C:\sender\server')
RO = 'file:C:/sender/enrich.db?mode=ro'
import site_facts as SF  # noqa: E402

FAKT = ['продукция', 'упаковка_фасовка', 'сырьё', 'мощности', 'контроль_качества',
        'экспорт', 'оборудование_линии', 'клиенты', 'год_основания',
        'география_поставок', 'масштаб', 'энергохозяйство', 'расширение', 'газы',
        'новости']


def nepusto(v):
    return v not in (None, '', [], {}) and not (isinstance(v, str) and not v.strip())


c = sqlite3.connect(RO, uri=True, timeout=60)
ver = {str(r[0]): (r[1] or '') for r in c.execute(
    "select inn, coalesce(verified,'') from companies")}
pustye, polnye = [], []
for inn, fj in c.execute("select inn, coalesce(facts_json,'') from site_facts "
                         "where coalesce(facts_json,'')<>''"):
    try:
        d = json.loads(fj)
    except Exception:  # noqa: BLE001
        continue
    (pustye if sum(1 for k in FAKT if nepusto(d.get(k))) == 0 else polnye).append(str(inn))
c.close()
print('пустых карточек %d, карточек с фактами %d' % (len(pustye), len(polnye)))


def raspr(spisok):
    o = {}
    for i in spisok:
        k = ver.get(i, '(нет в companies)') or '(verified пуст)'
        o[k] = o.get(k, 0) + 1
    n = max(1, len(spisok))
    return {k: '%d (%.0f%%)' % (v, 100.0 * v / n)
            for k, v in sorted(o.items(), key=lambda x: -x[1])[:6]}


print('verified у ПУСТЫХ:', json.dumps(raspr(pustye), ensure_ascii=False))
print('verified у ПОЛНЫХ:', json.dumps(raspr(polnye), ensure_ascii=False))

# --- CSS/JS-мусор в тексте, который уходит модели ---
CSS = re.compile(r'[.#@]?[\w \-\[\]="\':,>()*+~^$|]{0,80}\{[^{}]{15,}\}')
JS = re.compile(r'(function\s*\(|var\s+\w+\s*=|document\.|window\.|\$\(|=>\s*\{)')
random.seed(11)


def zamer(spisok, n=260):
    vyb = random.sample(spisok, min(n, len(spisok)))
    doli, pust, itog = [], 0, []
    for i in vyb:
        try:
            st = SF._stranicy(i)
        except Exception:  # noqa: BLE001
            continue
        t = ' '.join(x for _u, x in st)
        if not t:
            pust += 1
            continue
        css = sum(len(m.group(0)) for m in CSS.finditer(t))
        doli.append(css / len(t))
        itog.append({'inn': i, 'znakov': len(t), 'dolya_css': round(css / len(t), 3),
                     'js': len(JS.findall(t))})
    doli.sort()
    med = doli[len(doli) // 2] if doli else 0
    sred = sum(doli) / max(1, len(doli))
    bolshe30 = sum(1 for d in doli if d > 0.3)
    return {'компаний': len(doli), 'без_текста': pust,
            'медиана_доли_CSS': round(med, 3), 'средняя': round(sred, 3),
            'у_скольких_CSS>30%': '%d (%.0f%%)' % (bolshe30, 100.0 * bolshe30 / max(1, len(doli)))}, itog


rp, dp = zamer(pustye)
rf, df = zamer(polnye)
print('CSS-мусор у ПУСТЫХ:', json.dumps(rp, ensure_ascii=False))
print('CSS-мусор у ПОЛНЫХ:', json.dumps(rf, ensure_ascii=False))
print('самые замусоренные пустые:', json.dumps(
    sorted(dp, key=lambda x: -x['dolya_css'])[:10], ensure_ascii=False))

with open(r'C:\sender\_tmp\dyra2_pochemu.json', 'w', encoding='utf-8') as f:
    json.dump({'verified_pustye': raspr(pustye), 'verified_polnye': raspr(polnye),
               'css_pustye': rp, 'css_polnye': rf, 'zamer_pustyh': dp,
               'zamer_polnyh': df}, f, ensure_ascii=False)
    import os
    f.flush()
    os.fsync(f.fileno())
print('записан dyra2_pochemu.json')

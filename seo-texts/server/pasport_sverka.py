# -*- coding: utf-8 -*-
r"""Сверка паспорта со страницами: каждый факт обязан находиться на сайте.

Владелец 14.08: «главное не размыть качество». Новые ключи и новые источники
увеличивают заполненность — и ровно так же легко увеличивают враньё, потому что
модель, которой нечего сказать, начинает обобщать. Единственная защита, которая
не зависит от нашего оптимизма, — проверять каждую строку паспорта по тексту
скачанных страниц.

Как считаем. Строка ПОДТВЕРЖДЕНА, если она встречается на странице дословно
(после нормализации регистра и пробелов) либо все её значимые слова стоят в одном
окне в 300 знаков — это ловит перестановку слов и склонение, но не выдумку.
Строка НЕ ПОДТВЕРЖДЕНА — кандидат в лозунг или в галлюцинацию, и по каждому ключу
мы видим долю таких.

    python pasport_sverka.py [сколько] [--svezhie]
"""
import gzip
import json
import os
import re
import sqlite3
import sys

KESH = os.environ.get('PAGECACHE_DIR', r'C:\seostat\drop\pagecache')
BD = os.environ.get('ENRICH_DB', r'C:\sender\enrich.db')
КЛЮЧИ = ('продукция', 'сырьё', 'мощности', 'контроль_качества', 'упаковка_фасовка',
         'экспорт', 'оборудование_линии', 'клиенты', 'география_поставок', 'масштаб',
         'энергохозяйство', 'газы', 'год_основания')
# слова короче четырёх букв в сверке не участвуют: «и», «для», «по» есть везде
_СЛОВО = re.compile(r'[а-яёa-z0-9]{4,}')
# ОКОНЧАНИЯ. Паспорт пишет «Тюменская область», сайт — «поставляем в тюменской,
# новосибирской областях». Дословного вхождения нет, факт при этом честный: замер
# 16.08 дал по географии 0,73 подтверждения, и половина провалов оказалась вот
# этим падежом, а не выдумкой. Сравниваем основы: у русского слова отсекаем до
# трёх букв с конца, оставляя не меньше трёх: «край» на сайте живёт как «крае».
# Короткая основа не даёт ложных зачётов сама по себе — в окне обязаны стоять ВСЕ
# слова фразы, и «Республика Казахстан» по улице «2-я Казахстанская» не проходит.
_ХВОСТЫ = ('ами', 'ями', 'ого', 'ему', 'ому', 'ыми', 'ими', 'ая', 'яя', 'ое', 'ее',
           'ой', 'ей', 'ий', 'ый', 'ом', 'ем', 'ах', 'ях', 'ов', 'ев', 'ий', 'ые',
           'ие', 'ух', 'юю', 'ую', 'а', 'я', 'е', 'и', 'ы', 'о', 'у', 'ю', 'й', 'ь')


def _osnova(w):
    for х in _ХВОСТЫ:
        if len(w) - len(х) >= 3 and w.endswith(х):
            return w[:-len(х)]
    return w


def _tekst(inn):
    p = os.path.join(KESH, '%s.json.gz' % inn)
    if not os.path.exists(p):
        return ''
    try:
        d = json.loads(gzip.open(p, 'rb').read().decode('utf-8', 'replace'))
    except Exception:  # noqa: BLE001
        return ''
    куски = []
    for pg in (d.get('pages') or []):
        h = pg.get('html') or ''
        h = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', h, flags=re.S | re.I)
        куски.append(re.sub(r'<[^>]+>', ' ', h))
    t = ' '.join(куски).lower().replace('ё', 'е')
    for a, b in (('&nbsp;', ' '), ('&amp;', '&'), ('&quot;', '"'),
                 ('&laquo;', '«'), ('&raquo;', '»')):
        t = t.replace(a, b)
    return re.sub(r'\s+', ' ', t)


def _podtverzhdena(fraza, tekst):
    """Дословно или все значимые слова в одном окне — иначе не подтверждена."""
    f = re.sub(r'\s+', ' ', str(fraza or '')).strip().lower().replace('ё', 'е')
    if not f:
        return True                      # пустое не врёт
    if f in tekst:
        return True
    слова = _СЛОВО.findall(f)
    if not слова:
        return f in tekst
    # сперва как есть, затем по основам: падеж на сайте — не повод считать факт
    # выдуманным, а вот отсутствие основы на страницах — повод
    for основы in (слова, [_osnova(w) for w in слова]):
        # ищем окно вокруг самого редкого слова: так проверка не зависит от порядка
        редкое = min(основы, key=lambda w: tekst.count(w))
        if tekst.count(редкое) == 0:
            continue
        поз = 0
        while True:
            i = tekst.find(редкое, поз)
            if i < 0:
                break
            окно = tekst[max(0, i - 300):i + 300]
            if all(w in окно for w in основы):
                return True
            поз = i + 1
    return False


def сверить(skolko=100, svezhie=False):
    c = sqlite3.connect('file:%s?mode=ro' % BD.replace('\\', '/'), uri=True)
    c.row_factory = sqlite3.Row
    порядок = 'desc' if svezhie else 'asc'
    строки = list(c.execute("select inn, facts_json from site_facts "
                            "where coalesce(facts_json,'')<>'' "
                            'order by ts %s limit ?' % порядок, (skolko,)))
    c.close()
    итог = {'паспортов': 0, 'фактов': 0, 'подтверждено': 0, 'по_ключам': {}, 'примеры': []}
    for r in строки:
        try:
            d = json.loads(r['facts_json'])
        except Exception:  # noqa: BLE001
            continue
        t = _tekst(str(r['inn']))
        if not t:
            continue
        итог['паспортов'] += 1
        for k in КЛЮЧИ:
            v = d.get(k)
            фразы = v if isinstance(v, list) else ([v] if isinstance(v, str) and v else [])
            for ф in фразы:
                if not isinstance(ф, str):
                    continue
                ок = _podtverzhdena(ф, t)
                итог['фактов'] += 1
                итог['подтверждено'] += 1 if ок else 0
                б = итог['по_ключам'].setdefault(k, {'всего': 0, 'подтв': 0})
                б['всего'] += 1
                б['подтв'] += 1 if ок else 0
                if not ок and len(итог['примеры']) < 12:
                    итог['примеры'].append({'инн': str(r['inn']), 'ключ': k,
                                            'факт': ф[:90]})
    for k, б in итог['по_ключам'].items():
        б['доля'] = round(б['подтв'] / max(1, б['всего']), 2)
    итог['доля_подтверждённых'] = round(итог['подтверждено'] / max(1, итог['фактов']), 3)
    return итог


if __name__ == '__main__':
    n = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 100
    print(json.dumps(сверить(n, '--svezhie' in sys.argv), ensure_ascii=False)[:1500])

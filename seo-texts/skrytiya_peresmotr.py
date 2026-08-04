# -*- coding: utf-8 -*-
"""Пересмотр скрытий: предприятие спрятано «центробежность не доказана», а соседний факт её доказывает.

ОТКУДА ВЗЯЛОСЬ. Владелец спросил про два ИНН — 1003018230 и 7017156263: в какой карточке
написано, что машина центробежная. Полез смотреть и нашёл своё же упущение: у обоих в
`hidden_item` стоит скрытие с причиной «центробежность не доказана», хотя у того же ИНН есть
другие факты, где она доказана прямо — у 7017156263 шесть заключений ЭПБ и четыре процедуры
ЭТП ГПБ, у 1003018230 пять карточек закупок.

ПОЧЕМУ ЭТО СИСТЕМНАЯ ОШИБКА, А НЕ ДВА СЛУЧАЯ. Скрытие ставится по ОДНОЙ карточке, а прячет
ПРЕДПРИЯТИЕ целиком. Пока факты копились по одному, это работало; после того как каналы
слились (реестр ЭПБ, закупки, ЭТП, вложения ЕИС), у предприятия стало по десятку карточек, и
решение, принятое по слабейшей из них, продолжает прятать все остальные. Провенанс у нас
накапливается — значит и пересматривать надо накопленное, а не карточку, на которой в тот
день остановились.

ЧТО ДЕЛАЕТ. Ничего не отменяет сам. Печатает и выгружает список к пересмотру: ИНН, причина
скрытия, кто и когда скрыл, и РЯДОМ — факты того же ИНН, где центробежность доказана, с их
источниками и числом. Решение отменять или нет принимает человек, потому что причина скрытия
могла быть и другой («не наш профиль», «ликвидировано»), а мы видим только текст.

Использование:
    python3 skrytiya_peresmotr.py            # отчёт
    python3 skrytiya_peresmotr.py --csv out.csv
"""
import base64
import csv
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'server'))
import run_on_server as R  # noqa: E402

# Скрытие и доказательство лежат в РАЗНЫХ базах: решения — в centro_sales.db, факты — в
# centrifugal.db. Их и сводим, иначе видно только половину картины.
SCRIPT = r'''
import sqlite3, json

sale = sqlite3.connect(r'C:\seostat\data\centro_sales.db')
# Путь передаётся параметром, а не вклеивается в SQL: префикс r'' — синтаксис Python, и
# внутри запроса sqlite видит его как часть строки и падает с syntax error.
sale.execute('attach database ? as f', (r'C:\seostat\data\centrifugal.db',))

# Скрытия, где в причине речь о недоказанной центробежности. Формулировки разные, поэтому
# ловим по корню, а не по точной строке.
# ОТБОР ПЕРЕНЕСЁН В PYTHON, И ЭТО НЕ КОСМЕТИКА. `sqlite3.lower()` знает только латиницу:
# `lower('ЦЕНТРОБЕЖНЫЙ')` возвращает `'ЦЕНТРОБЕЖНЫЙ'`, и `like '%центробежн%'` даёт ЛОЖЬ.
# LIKE регистронезависим тоже только для ASCII. То есть прежний отбор МОЛЧА пропускал всё,
# что записано прописными, и ноль читался как «таких скрытий больше нет».
#
# Замер цены ошибки по всей базе (`lower_pereschet.py`): невидимо 8 957 строк, в том числе
# 1 752 факта со словом «центробежн» в цитате и 2 063 с «воздуходувк». Здесь это значит, что
# пересмотр скрытий шёл по неполному списку — и в обе стороны сразу: и скрытий находилось
# меньше, чем есть, и доказательств у них тоже.
def soderzhit(stroka, *slova):
    """Честное сравнение с приведением регистра: Python знает кириллицу, SQLite — нет."""
    n = (stroka or '').lower()
    return any(s in n for s in slova)


# ТОЛЬКО СКРЫТИЯ ПРЕДПРИЯТИЙ, а не фактов. Проверка после починки сравнения: правило
# ловило 15 510 скрытий вида `fact` и 110 вида `company`, и я едва не объявила первые
# ошибкой. Они не ошибка. Скрытие ФАКТА — это «из этой карточки не следует, что тут
# воздушный центробежник»: хлорный компрессор у предприятия, где рядом доказан воздушный,
# прячется совершенно правильно. Ошибочно другое — скрытие ПРЕДПРИЯТИЯ по слабейшей из его
# карточек, потому что оно прячет и все остальные. Ради него инструмент и написан.
#
# Разница в 140 раз, и обе стороны выглядели одинаково правдоподобно. Правило то же, что
# сегодня уже дважды: большое число — повод проверить прибор, а не повод объявить открытие.
skr = [r for r in sale.execute(
    """select inn, kind, coalesce(value,''), coalesce(reason,''),
              coalesce(username,''), coalesce(created_at,'')
       from hidden_item where kind = 'company'""")
       if soderzhit(r[3], 'центробежн')
       and soderzhit(r[3], 'не доказан', 'не подтвержд', 'нет доказ')]

out = {'skrytiy_po_prichine': len(skr), 'k_peresmotru': [], 'ostalis': 0}
for inn, kind, value, reason, user, kogda in skr:
    # Соседние факты того же ИНН, где центробежность доказана. Считаем и источники: один и
    # тот же факт, добытый двумя каналами, весомее одного.
    # Имена колонок взяты из схемы базы, а не по памяти: в `fact` нет ни `text`, ни
    # `company_id` — предприятие лежит прямо в `inn`, а текст карточки в `quote`.
    # Центробежность доказывают два независимых поля: `equipment_type` (разобранный тип) и
    # сам текст закупки/заключения. Оба и проверяем.
    # Отбор доказательств тоже в Python и по той же причине: `fact.quote` — сырая цитата,
    # и она чаще всего записана как в источнике, то есть прописными.
    dok = [(d[0][:160], d[1], d[2], d[3]) for d in sale.execute(
        """select coalesce(c.quote,''), coalesce(c.source,''),
                  coalesce(c.equipment_type,''), coalesce(c.source_url,'')
           from f.fact c where c.inn = ?""", (inn,))
        if soderzhit(d[2], 'центробежн')
        or soderzhit(d[0], 'центробежн', 'турбокомпрессор', 'нагнетател',
                     'турбовоздуходувк')][:8]
    if not dok:
        out['ostalis'] += 1
        continue
    out['k_peresmotru'].append({
        'inn': inn, 'vid_skrytiya': kind, 'znachenie': value[:80], 'prichina': reason[:140],
        'kto': user, 'kogda': kogda,
        'dokazatelstv': len(dok),
        'istochnikov': len({d[1] for d in dok if d[1]}),
        'istochniki': ' | '.join(sorted({d[1] for d in dok if d[1]}))[:200],
        'citaty': ' /// '.join(d[0] for d in dok[:3])[:300],
    })

# ПЕЧАТЬ ПОСТРОЧНО, А НЕ ОДНИМ JSON. Раннер отдаёт `stdout_tail` — буквально хвост вывода:
# при 281 записи начало ответа обрезалось, и разбор падал на «нет открывающей скобки».
# Одна запись — одна строка с меткой REC, поэтому обрезание съедает старые записи, а не
# ломает разбор целиком. Строка ИТОГ идёт последней и в хвост попадает всегда — по ней
# видно, СКОЛЬКО записей должно было прийти, и приёмник честно скажет, скольких не хватает,
# вместо того чтобы показать усечённый список как полный.
# ПОЛНЫЙ СПИСОК УХОДИТ ФАЙЛОМ НА ОБМЕННИК, А НЕ ЧЕРЕЗ ХВОСТ ВЫВОДА. Замер: к пересмотру
# 99 предприятий, до меня доехало 12 — остальные 87 съел `stdout_tail`. Сам инструмент про
# это честно предупреждает («87 записей не доехали»), и предупреждения оказалось мало:
# в CSV попадало ровно то же усечённое, то есть список к пересмотру был неполон молча для
# всякого, кто откроет файл. Печать оставляю для глаз, а данные отдаю каналом, который
# усечения не знает.
import csv as _csv
import io as _io
import os as _os
import urllib.request as _ur

if out['k_peresmotru']:
    _polya = list(out['k_peresmotru'][0].keys())
    _b = _io.StringIO()
    _w = _csv.DictWriter(_b, fieldnames=_polya, delimiter=';', extrasaction='ignore')
    _w.writeheader()
    _w.writerows(out['k_peresmotru'])
    _telo = _b.getvalue().encode('utf-8-sig')
    _req = _ur.Request(
        _os.environ.get('DROP_URL', 'https://parsercompressor.online/drop').rstrip('/')
        + '/VAZHNOE-3s-SKRYTIYA-PREDPRIYATIY-k-peresmotru.csv',
        data=_telo, method='PUT',
        headers={'X-Drop-Token': _os.environ.get('DROP_TOKEN', ''),
                 'Content-Type': 'text/csv'})
    try:
        with _ur.urlopen(_req, timeout=180) as _r:
            out['fayl_na_drope'] = '%s, строк %d' % (_r.status, len(out['k_peresmotru']))
    except Exception as _e:
        out['fayl_na_drope'] = 'НЕ выгружено: %s' % type(_e).__name__

for z in out['k_peresmotru']:
    print('REC ' + json.dumps(z, ensure_ascii=False))
print('ИТОГ ' + json.dumps({'fayl_na_drope': out.get('fayl_na_drope', 'нечего выгружать'),
                            'skrytiy_po_prichine': out['skrytiy_po_prichine'],
                            'k_peresmotru': len(out['k_peresmotru']),
                            'ostalis': out['ostalis']}, ensure_ascii=False))
'''


def sobrat():
    dest = r'C:\sender\_ops\3s_skrytiya_peresmotr.py'
    R.submit('enrich_contacts', {'op': 'panel_file_put',
                                 'files': [{'dest': dest,
                                            'b64': base64.b64encode(SCRIPT.encode()).decode()}]},
             timeout=300)
    r = R.submit('enrich_contacts', {'op': 'panel_py', 'script': dest, 'timeout': 400},
                 timeout=600)
    d = r.get('data') or {}
    # Имя поля ответа проверяется, а не угадывается: раньше чтение несуществующего ключа
    # молча давало пустоту, и это выглядело как честный ноль.
    hvost = d.get('stdout_tail') or d.get('stderr_tail') or ''
    if not hvost:
        print('ОТВЕТ ПУСТ. Ключи ответа:', list(d), file=sys.stderr)
        return None
    zapisi, itog = [], None
    for stroka in hvost.splitlines():
        s = stroka.strip()
        if s.startswith('REC '):
            try:
                zapisi.append(json.loads(s[4:]))
            except ValueError:
                pass  # обрезанная первая строка — её и должен поймать счёт ниже
        elif s.startswith('ИТОГ '):
            itog = json.loads(s[5:])
    if itog is None:
        print('строки ИТОГ нет — задание не доработало. Хвост:', hvost[-300:], file=sys.stderr)
        return None
    # Хвост мог съесть начало: сравниваем пришедшее с обещанным и говорим об этом вслух.
    itog['k_peresmotru_spisok'] = zapisi
    itog['poteryano_v_hvoste'] = itog['k_peresmotru'] - len(zapisi)
    return itog


def main():
    d = sobrat()
    if not d:
        sys.exit(1)
    spisok = d['k_peresmotru_spisok']
    print(f'скрытий с причиной «центробежность не доказана»: {d["skrytiy_po_prichine"]}',
          file=sys.stderr)
    print(f'из них соседний факт ДОКАЗЫВАЕТ центробежность: {d["k_peresmotru"]} '
          f'(остальные {d["ostalis"]} — доказательств нет, скрытие в силе)', file=sys.stderr)
    if d['poteryano_v_hvoste']:
        # Молчать об этом нельзя: усечённый список выглядит как полный.
        print(f'ВНИМАНИЕ: {d["poteryano_v_hvoste"]} записей не доехали — их съел хвост '
              f'вывода раннера. Ниже и в CSV только {len(spisok)}.', file=sys.stderr)
    spisok.sort(key=lambda x: (-x['istochnikov'], -x['dokazatelstv']))
    for z in spisok[:15]:
        print(f'  {z["inn"]:<12} доказательств {z["dokazatelstv"]:>2}, источников '
              f'{z["istochnikov"]}: {z["istochniki"][:60]}', file=sys.stderr)
    if '--csv' in sys.argv:
        put = sys.argv[sys.argv.index('--csv') + 1]
        with open(put, 'w', encoding='utf-8-sig', newline='') as f:
            w = csv.DictWriter(f, fieldnames=list(spisok[0]), delimiter=';')
            w.writeheader()
            w.writerows(spisok)
        print(f'→ {put}', file=sys.stderr)


if __name__ == '__main__':
    main()

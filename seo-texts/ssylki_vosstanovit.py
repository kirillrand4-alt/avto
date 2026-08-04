# -*- coding: utf-8 -*-
"""Вернуть контактам ссылку на первоисточник — только там, где она ДОКАЗУЕМО та самая.

ПОЧЕМУ НЕЛЬЗЯ ПРОСТО ВЗЯТЬ ССЫЛКУ СОСЕДНЕГО ФАКТА. У 1 316 предприятий из 1 340 есть факт со
ссылкой, и соблазн подставить её велик. Но контакт пришёл НЕ ОТТУДА: адрес закупки не
доказывает, откуда взялся телефон механика. Приписать его — значит выдумать провенанс, а
выдуманный источник хуже пустого. Пустой честно говорит «не знаем»; выдуманный отправляет
человека проверять не туда и при этом выглядит доказательством. Правило владельца «источники
накапливаются» про накопление ПРОВЕРЯЕМЫХ источников, а не про заполнение пустых клеток.

Поэтому восстанавливается ровно три случая, и в каждом ссылка не угадана, а выведена:

1. ЕГРЮЛ/dadata — 1 309 контактов. Данные пришли из API, страницы у запроса не было. Но у
   части контактов ТОГО ЖЕ источника ссылка стоит, и её форма —
   `https://egrul.nalog.ru/index.html#!/search?query=<ИНН>`. Это не догадка: карточка ЕГРЮЛ по
   этому ИНН и есть то место, где директор перепроверяется. Форма берётся из базы, а не из
   головы, и подставляется только для источника «ЕГРЮЛ/dadata».

2. СШИВКА — тот же человек на том же ИНН уже имеет строку СО ссылкой. Здесь ничего не
   выдумывается вовсе: ссылка переносится с записи о том же человеке.

3. TENDER.PRO — только если у того же предприятия есть контакт того же источника со ссылкой на
   карточку компании. Ссылку на ПРОЦЕДУРУ (`/api/tender/<id>/view_public`) не переносим:
   процедура не то место, где лежит контакт.

Всё, что под эти три случая не подходит, остаётся пустым — и получает пометку, что источник
утрачен при сведении, чтобы это было видно, а не выглядело недоработкой сбора.

Использование:
    python3 ssylki_vosstanovit.py             # посчитать
    python3 ssylki_vosstanovit.py --primenit  # записать
"""
import base64
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'server'))
import run_on_server as R  # noqa: E402

SCRIPT = r'''
import collections, csv, io, json, os, re, sqlite3, sys, urllib.request

PRIMENIT = 'PRIMENIT' in sys.argv
cx = sqlite3.connect(r'C:\seostat\data\centrifugal.db')

# ОТБОР ИДЁТ В PYTHON, А НЕ В SQL, И ЭТО НЕ ПРИДИРКА. Встроенный `lower()` в SQLite приводит
# к нижнему регистру ТОЛЬКО ASCII: `lower('ЕГРЮЛ')` возвращает «ЕГРЮЛ». Поэтому шаблон
# '%егрюл%' не совпадал никогда, запрос отдавал ноль строк и выглядел честным нулём —
# «образцов просмотрено 0» при 1 396 живых контактах ЕГРЮЛ в базе. Ошибки SQL не даёт.
obrazcy = [(u,) for s0, u in cx.execute(
    "select coalesce(source,''), coalesce(source_url,'') from person")
    if 'егрюл' in s0.lower() and u][:50]
# Шаблон намеренно нежёсткий: строгий вариант с `$` и точной схемой не совпал ни с одним из
# полусотни образцов, и прогон честно сказал «форма не найдена» вместо того, чтобы подставить
# выдуманное. Причина могла быть любой — http вместо https, хвост в адресе, иная подстраница.
# Берём всё, что ведёт на egrul.nalog.ru и оканчивается запросом по ИНН, и режем по `query=`.
forma = ''
obrazec = ''
for (u,) in obrazcy:
    m = re.match(r'(https?://egrul\.nalog\.ru/\S*?query=)\d{10,12}\s*$', u or '')
    if m:
        forma, obrazec = m.group(1), u
        break
if not forma:
    print('ОБРАЗЕЦ ФОРМЫ ЕГРЮЛ НЕ НАЙДЕН — не подставляю ничего, иначе это будет догадка')

# Сшивка: тот же человек и ИНН, но у другой строки ссылка есть.
est_u_cheloveka = {}
for inn, person, url in cx.execute(
        "select coalesce(inn,''), coalesce(person,''), coalesce(source_url,'') from person "
        "where coalesce(source_url,'') <> ''"):
    est_u_cheloveka.setdefault((inn, person), url)

# Ссылка на карточку компании Тендер.Про у того же предприятия (не на процедуру).
tp_kartochka = {}
for inn, url in cx.execute(
        "select coalesce(inn,''), coalesce(source_url,'') from person "
        "where lower(coalesce(source,'')) like '%tender%' and coalesce(source_url,'') <> ''"):
    if '/api/tender/' in url:
        continue
    tp_kartochka.setdefault(inn, url)

pravki, sch = [], collections.Counter()
for rid, inn, person, src in cx.execute(
        "select rowid, coalesce(inn,''), coalesce(person,''), coalesce(source,'') "
        "from person where coalesce(source_url,'') = ''").fetchall():
    s = src.lower()
    u, pochemu = '', ''
    if (inn, person) in est_u_cheloveka:
        u = est_u_cheloveka[(inn, person)]
        pochemu = 'сшивка: тот же человек на том же ИНН уже имеет ссылку'
    elif 'егрюл' in s or 'dadata' in s:
        if forma and re.fullmatch(r'\d{10,12}', inn):
            u = forma + inn
            pochemu = 'карточка ЕГРЮЛ по ИНН — форма взята из существующих записей того же источника'
    elif 'tender' in s and inn in tp_kartochka:
        u = tp_kartochka[inn]
        pochemu = 'карточка компании Тендер.Про того же предприятия (не процедура)'
    if u:
        pravki.append({'rowid': rid, 'inn': inn, 'person': person, 'source': src[:80],
                       'url': u, 'pochemu': pochemu})
        sch[pochemu.split(':')[0].split('—')[0].strip()] += 1
    else:
        sch['НЕ ВОССТАНОВИМО: источник утрачен при сведении'] += 1

bez_ssylki = cx.execute(
    "select count(*) from person where coalesce(source_url,'')=''").fetchone()[0]
itog = {'без_ссылки_было': bez_ssylki, 'восстановимо': len(pravki),
        'по_основаниям': dict(sch), 'примeneno': False,
        'форма_егрюл': forma or '(не найдена)', 'образец_егрюл': obrazec or '',
        'образцов_просмотрено': len(obrazcy)}

if PRIMENIT and pravki:
    cx.executemany('update person set source_url = ? where rowid = ?',
                   [(z['url'], z['rowid']) for z in pravki])
    # Помечаем невосстановимое явно: пустая клетка и признанная утрата — разные вещи.
    cx.execute("update person set source = source || ' [источник утрачен при сведении]' "
               "where coalesce(source_url,'')='' "
               "and source not like '%утрачен при сведении%'")
    cx.commit()
    itog['примeneno'] = True
    itog['без_ссылки_стало'] = cx.execute(
        "select count(*) from person where coalesce(source_url,'')=''").fetchone()[0]
    b = io.StringIO()
    w = csv.DictWriter(b, delimiter=';', fieldnames=list(pravki[0]))
    w.writeheader(); w.writerows(pravki)
    telo = b.getvalue().encode('utf-8-sig')
    req = urllib.request.Request(
        os.environ.get('DROP_URL', 'https://parsercompressor.online/drop').rstrip('/')
        + '/VAZHNOE-3s-SSYLKI-VOSSTANOVLENY.csv', data=telo, method='PUT',
        headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', ''), 'Content-Type': 'text/csv'})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            itog['бэкап'] = f'{r.status}, {len(telo)} байт'
    except Exception as e:
        itog['бэкап'] = f'НЕ ВЫГРУЖЕН: {type(e).__name__}'

print('ИТОГ ' + json.dumps(itog, ensure_ascii=False))
'''


def main():
    primenit = '--primenit' in sys.argv
    dest = r'C:\sender\_ops\3s_ssylki_vosstanovit.py'
    R.submit('enrich_contacts', {'op': 'panel_file_put', 'files': [
        {'dest': dest, 'b64': base64.b64encode(SCRIPT.encode()).decode()}]}, timeout=300)
    r = R.submit('enrich_contacts', {'op': 'panel_py', 'script': dest,
                                     'argv': ['PRIMENIT'] if primenit else [],
                                     'timeout': 900}, timeout=1200)
    d = r.get('data') or {}
    hvost = d.get('stdout_tail') or d.get('stderr_tail') or ''
    for s in hvost.splitlines():
        if s.strip().startswith('ИТОГ '):
            print(json.dumps(json.loads(s.strip()[5:]), ensure_ascii=False, indent=1))
            return
    print('строки ИТОГ нет. Хвост:', hvost[-500:], file=sys.stderr)


if __name__ == '__main__':
    main()

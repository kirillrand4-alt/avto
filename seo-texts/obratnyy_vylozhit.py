# -*- coding: utf-8 -*-
"""Выложить добытое обратным ходом: файл соседям и заливка в enrich.db.

ПОЧЕМУ ЭТО ОТДЕЛЬНЫЙ ШАГ И ПОЧЕМУ СРОЧНЫЙ. Обратный ход по списку 2-й сессии добыл сотни
номеров, и они лежат в потоке `lpr-obratnyy-chuzhoy.jsonl` на сервере. Дословно из их
журнала: «Сейчас эти 156 номеров есть у вас и нет у продавца». Пока номер не в панели, он не
существует для дела — цель владельца меряется не добытым, а дозвонившимся.

ЧТО ЗДЕСЬ РЕШАЕТСЯ, КРОМЕ ПЕРЕНОСА

  * ВИД НОМЕРА НАЗЫВАЕТСЯ ЯВНО. Личный мобильный и линия приёмной — разные вещи, и
    складывать их в одну колонку значит сломать главную меру. Вид считается по последним
    десяти цифрам (девятка — мобильный) и по общему заслону: номер, на котором сидят РАЗНЫЕ
    ФАМИЛИИ, личным не бывает, сколько бы он ни выглядел мобильным.
  * ДОБАВОЧНЫЙ ОТРЕЗАЕТСЯ ДО ЗАПИСИ. Тот самый дефект, за который 2-я сессия прислала
    задание: если чистить номер от знаков вместе со словом «доб.», цифры добавочного
    прилипают и номер перестаёт набираться.
  * ПРОВЕНАНС НЕ СХЛОПЫВАЕТСЯ. В источнике записано и чей список (2-я сессия), и чей канал
    (обратный ход 3-й сессии), и адрес страницы, откуда номер снят. Правило владельца:
    источники накапливаются, а не заменяются.
  * СБОЙ — НЕ НОЛЬ. Записи с ошибкой канала не выгружаются как «телефона нет»: они не
    спрошены, и повторный прогон их переспросит.

Запуск:
    python3 obratnyy_vylozhit.py            # посчитать и выложить файл на дроп
    python3 obratnyy_vylozhit.py --v-bazu   # ещё и залить в enrich.db
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
import collections, csv, io, json, os, re, sqlite3, sys, urllib.request
sys.path.insert(0, r'C:\sender\_ops')
import _3s_nomer_dobavochnyy as D
import _3s_nomer_obshchiy as O

V_BAZU = 'V_BAZU' in sys.argv
POTOK = r'C:\sender\_ops\lpr-obratnyy-chuzhoy.jsonl'

zapisi, sboev = [], 0
if os.path.exists(POTOK):
    for ln in open(POTOK, encoding='utf-8'):
        try:
            z = json.loads(ln)
        except Exception:
            continue
        if z.get('err'):
            sboev += 1
            continue
        zapisi.append(z)

# Карта общих номеров строится по ВСЕЙ базе панели, а не по добытому куску: номер, сидящий
# на десяти предприятиях, в отдельном файле выглядит чистым.
cx = sqlite3.connect(r'C:\seostat\data\centrifugal.db')
pary = [(inn, ph, per) for inn, ph, per in cx.execute(
    "select coalesce(inn,''), coalesce(phone,''), coalesce(person,'') from person "
    "where coalesce(phone,'') <> ''")]

rows = []
sch = collections.Counter()
for z in zapisi:
    inn = str(z.get('inn') or '').strip()
    fio = (z.get('fio') or '').strip()
    kont = z.get('kontakty') or []
    if not kont:
        sch['человек пройден, контактов не нашлось'] += 1
        continue
    for k in kont:
        zn = str(k.get('znachenie') or k.get('value') or '').strip()
        if not zn:
            continue
        if '@' in zn:
            rows.append({'inn': inn, 'fio': fio, 'znachenie': zn, 'vid': 'почта',
                         'dobavochnyy': '', 'dolzhnost': (z.get('dolzhnost') or '')[:80],
                         'predpriyatie': (z.get('predpriyatie') or '')[:90],
                         'ssylka': (k.get('ssylka') or k.get('url') or '')[:200],
                         'istochnik': 'список 2-й сессии + обратный ход 3-й сессии'})
            sch['почта'] += 1
            continue
        nomer, dob, ok, poch = D.raznyat(zn)
        if not ok:
            sch['номер неразборчив: ' + poch[:40]] += 1
            continue
        pary.append((inn, nomer, fio))
        rows.append({'inn': inn, 'fio': fio, 'znachenie': nomer, 'vid': '',
                     'dobavochnyy': dob, 'dolzhnost': (z.get('dolzhnost') or '')[:80],
                     'predpriyatie': (z.get('predpriyatie') or '')[:90],
                     'ssylka': (k.get('ssylka') or k.get('url') or '')[:200],
                     'istochnik': 'список 2-й сессии + обратный ход 3-й сессии'})

# Вид номера ставится ПОСЛЕ того, как в карту попали все добытые: иначе два человека с одним
# номером из этой же пачки друг друга не увидят.
karta = O.postroit(pary)
for r in rows:
    if r['vid'] == 'почта':
        continue
    s = O.sudba(O.klyuch(r['znachenie']), karta, r['znachenie'])
    r['vid'] = s['vid_nomera']
    r['vyvod'] = s['vyvod']
    r['predpriyatiy_na_nomere'] = s['predpriyatiy_na_nomere']
    lich = s['vid_nomera'] == 'мобильный' and not s['vyvod'].startswith('ОБЩИЙ')
    sch['ЛИЧНЫЙ МОБИЛЬНЫЙ' if lich else 'номер ' + s['vid_nomera']] += 1

itog = {'записей_в_потоке': len(zapisi), 'сбоев_не_выгружено': sboev,
        'строк_к_выдаче': len(rows), 'по_видам': dict(sch.most_common()),
        'людей_с_личным_мобильным': len({r['fio'] for r in rows
                                         if r.get('vyvod', '').startswith('личным быть может')
                                         and r['vid'] == 'мобильный'}),
        'предприятий': len({r['inn'] for r in rows})}

if rows:
    polya = ['inn', 'predpriyatie', 'fio', 'dolzhnost', 'znachenie', 'vid', 'dobavochnyy',
             'vyvod', 'predpriyatiy_na_nomere', 'ssylka', 'istochnik']
    b = io.StringIO()
    w = csv.DictWriter(b, delimiter=';', fieldnames=polya, extrasaction='ignore')
    w.writeheader(); w.writerows(rows)
    telo = b.getvalue().encode('utf-8-sig')
    req = urllib.request.Request(
        os.environ.get('DROP_URL', 'https://parsercompressor.online/drop').rstrip('/')
        + '/DLYA-VSEH-3s-OBRATNYY-HOD-NOMERA.csv', data=telo, method='PUT',
        headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', ''), 'Content-Type': 'text/csv'})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            itog['файл'] = '%s, строк %d' % (r.status, len(rows))
    except Exception as e:
        itog['файл'] = 'НЕ выгружен: ' + type(e).__name__

if V_BAZU and rows:
    en = sqlite3.connect(r'C:\sender\enrich.db')
    kol = [r[1] for r in en.execute('pragma table_info(people)')]
    # Уже есть — по паре ИНН и фамилии, правило 1-й сессии. Инициалы и отчество не
    # сравниваем: одно и то же имя пишется по-разному.
    def fam(v):
        ch = re.split(r'[\s.,]+', (v or '').strip())
        return ch[0].lower().replace('ё', 'е') if ch and ch[0] else ''
    est = {(i, fam(p)) for i, p in en.execute(
        "select coalesce(inn,''), coalesce(person,'') from people")}
    est_nom = {re.sub(r'\D', '', p or '')[-10:] for (p,) in en.execute(
        "select coalesce(phone,'') from people where coalesce(phone,'') <> ''")}
    novye, propushcheno = [], 0
    for r in rows:
        if r['vid'] == 'почта':
            continue
        k = re.sub(r'\D', '', r['znachenie'])[-10:]
        if (r['inn'], fam(r['fio'])) in est and k in est_nom:
            propushcheno += 1
            continue
        est.add((r['inn'], fam(r['fio'])))
        est_nom.add(k)
        novye.append({'inn': r['inn'], 'person': r['fio'], 'post': r['dolzhnost'],
                      'phone': r['znachenie'], 'email': '',
                      'source': ('обратный ход 3-й сессии по списку 2-й сессии; '
                                 'вид номера: %s; %s%s' % (
                                     r['vid'], r.get('vyvod', '')[:70],
                                     '; добавочный ' + r['dobavochnyy']
                                     if r['dobavochnyy'] else '')),
                      'source_url': r['ssylka']})
    polya_db = [k for k in ('inn', 'person', 'post', 'phone', 'email', 'source', 'source_url')
                if k in kol]
    # У people есть УНИКАЛЬНЫЙ ключ (inn, person, post) — прямая вставка падает на первом же
    # совпадении. `insert or ignore` тут неверен: он молча выбросит НОВЫЙ номер у человека,
    # который в базе уже есть без телефона, а это ровно то, за чем мы ходили. Поэтому три
    # исхода, и ни в одном номер не теряется:
    #   строки нет            → вставляем;
    #   строка есть без номера → дописываем номер, источники складываем;
    #   строка есть с ДРУГИМ номером → номер не перетираем (чужой мог быть личным), а
    #                           дописываем в источник с подписью, чей он и откуда.
    vstavleno = dopisano = vtoroy_nomer = 0
    for n in novye:
        est_str = en.execute(
            "select rowid, coalesce(phone,''), coalesce(source,'') from people "
            "where inn = ? and person = ? and coalesce(post,'') = ?",
            (n['inn'], n['person'], n['post'])).fetchone()
        if not est_str:
            en.execute('insert into people (%s) values (%s)'
                       % (','.join(polya_db), ','.join('?' * len(polya_db))),
                       tuple(n[k] for k in polya_db))
            vstavleno += 1
            continue
        rid, ph_est, src_est = est_str
        if not ph_est.strip():
            en.execute('update people set phone = ?, source = ? where rowid = ?',
                       (n['phone'], (src_est + ' | ' + n['source'])[:1000], rid))
            dopisano += 1
        elif re.sub(r'\D', '', ph_est)[-10:] != re.sub(r'\D', '', n['phone'])[-10:]:
            en.execute('update people set source = ? where rowid = ?',
                       ((src_est + ' | ещё номер этого человека: %s (%s)'
                         % (n['phone'], n['source'][:90]))[:1000], rid))
            vtoroy_nomer += 1
    en.commit()
    itog['залито_в_enrich'] = vstavleno
    itog['дописан_номер_тому_кто_был_без_него'] = dopisano
    itog['второй_номер_записан_в_источник'] = vtoroy_nomer
    itog['пропущено_как_дубль'] = propushcheno
    itog['людей_с_телефоном_в_enrich_стало'] = en.execute(
        "select count(distinct inn) from people where coalesce(phone,'') <> ''").fetchone()[0]

print('ИТОГ ' + json.dumps(itog, ensure_ascii=False))
'''


def main():
    fajly = [{'dest': r'C:\sender\_ops\_3s_nomer_dobavochnyy.py',
              'b64': base64.b64encode(open(os.path.join(TUT, 'nomer_dobavochnyy.py'),
                                           encoding='utf-8').read().encode()).decode()},
             {'dest': r'C:\sender\_ops\_3s_nomer_obshchiy.py',
              'b64': base64.b64encode(open(os.path.join(TUT, 'nomer_obshchiy.py'),
                                           encoding='utf-8').read().encode()).decode()},
             {'dest': r'C:\sender\_ops\3s_obratnyy_vylozhit.py',
              'b64': base64.b64encode(SCRIPT.encode()).decode()}]
    R.submit('enrich_contacts', {'op': 'panel_file_put', 'files': fajly}, timeout=300)
    r = R.submit('enrich_contacts',
                 {'op': 'panel_py', 'script': r'C:\sender\_ops\3s_obratnyy_vylozhit.py',
                  'argv': ['V_BAZU'] if '--v-bazu' in sys.argv else [], 'timeout': 900},
                 timeout=1200)
    d = r.get('data') or {}
    h = d.get('stdout_tail') or ''
    for s in h.splitlines():
        if s.strip().startswith('ИТОГ '):
            print(json.dumps(json.loads(s.strip()[5:]), ensure_ascii=False, indent=1))
            return
    print('пусто:', (d.get('stderr_tail') or '')[-1200:], file=sys.stderr)


if __name__ == '__main__':
    main()

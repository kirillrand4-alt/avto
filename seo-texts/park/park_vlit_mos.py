# -*- coding: utf-8 -*-
"""Портал поставщиков Москвы: ставим ОТКРЫВАЕМУЮ ссылку и забираем контактное лицо.

Старая форма `/need/N` отдаёт 200, но в теле только шапка портала — доказательством она
не является (проверено печатью тела целиком, 1 821 знак без единой строки о закупке).
Рабочая форма найдена 3-й сессией и подтверждена у меня: `newapi/api/Need/Get?needId=`.

Что делаем:
  * новую ссылку добавляем к факту как доказательство (этап «карточка портала, JSON»);
  * старую НЕ удаляем, а помечаем — она осталась адресом источника;
  * контактное лицо из того же JSON пишем в наблюдения с провенансом.

Замер входа: 161 запись, карточку отдали 129, ФИО есть у 96, телефон у 8, почта у 4.
"""
import sqlite3, json, os, re, importlib.util, collections

D = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('pb', os.path.join(D, 'park_build.py'))
pb = importlib.util.module_from_spec(spec); spec.loader.exec_module(pb)
p = sqlite3.connect(os.path.join(D, 'park.db')); cur = p.cursor()

ssyl = fio = tel = mail = 0
pri = collections.Counter()
for ln in open(os.path.join(D, 'park_mos_api.jsonl'), encoding='utf-8', errors='replace'):
    if not ln.strip():
        continue
    x = json.loads(ln)
    novaya, staraya = x.get('novaya'), x.get('staraya')
    if not x.get('zakazchik'):
        pri[x.get('pochemu') or 'карточка не отдана'] += 1
        continue
    # все факты, у которых висит старая ссылка
    fakty = [r[0] for r in cur.execute('select distinct fakt_id from fakt_ssylka where url=?',
                                       (staraya,))]
    raz = pb.razbor_url(novaya)
    for fid in fakty:
        if raz:
            cur.execute('insert or ignore into fakt_ssylka(fakt_id,url,domen,istochnik,etap,'
                        'pervoistochnik,data_nablyudeniya,fayl) values (?,?,?,?,?,?,?,?)',
                        (fid, novaya, raz[0], raz[1],
                         'карточка портала Москвы (JSON, открывается)', raz[2], '', ''))
            ssyl += cur.rowcount
        cur.execute("""update fakt_ssylka set etap='адрес источника: страница рисуется
                       скриптом, в теле только шапка портала' where fakt_id=? and url=?""",
                    (fid, staraya))
    # контакт: ИНН берём из факта, в JSON портала его нет
    inn = None
    if fakty:
        r = cur.execute('select inn from fakt where id=?', (fakty[0],)).fetchone()
        inn = r[0] if r else None
    if not inn or not raz:
        continue
    citata = ('Портал поставщиков Москвы, заказчик %s, предмет: %s'
              % (x.get('zakazchik', ''), (x.get('predmet') or '')[:150]))[:300]
    f = (x.get('kontakt_fio') or '').strip()
    if f:
        cur.execute('insert or ignore into contact_source(inn,vid,znachenie,person,dolzhnost,'
                    'istochnik,source_url,domen,pervoistochnik,data_nablyudeniya,quote,kto) '
                    'values (?,?,?,?,?,?,?,?,?,?,?,?)',
                    (inn, 'chelovek', f[:200], f[:200], 'контактное лицо закупки',
                     raz[1], novaya, raz[0], raz[2], '', citata,
                     '1-я сессия, портал Москвы через newapi (форма найдена 3-й сессией)'))
        fio += 1
    t = re.sub(r'\D', '', x.get('kontakt_tel') or '')[-10:]
    if len(t) == 10:
        cur.execute('insert or ignore into contact_source(inn,vid,znachenie,person,dolzhnost,'
                    'istochnik,source_url,domen,pervoistochnik,data_nablyudeniya,quote,kto) '
                    'values (?,?,?,?,?,?,?,?,?,?,?,?)',
                    (inn, 'telefon', t, f[:200], 'контактное лицо закупки', raz[1], novaya,
                     raz[0], raz[2], '', citata,
                     '1-я сессия, портал Москвы через newapi (форма найдена 3-й сессией)'))
        tel += 1
    m = (x.get('kontakt_email') or '').strip()
    if '@' in m:
        cur.execute('insert or ignore into contact_source(inn,vid,znachenie,person,dolzhnost,'
                    'istochnik,source_url,domen,pervoistochnik,data_nablyudeniya,quote,kto) '
                    'values (?,?,?,?,?,?,?,?,?,?,?,?)',
                    (inn, 'email', m, f[:200], 'контактное лицо закупки', raz[1], novaya,
                     raz[0], raz[2], '', citata,
                     '1-я сессия, портал Москвы через newapi (форма найдена 3-й сессией)'))
        mail += 1
p.commit()
print('новых ссылок-доказательств: %d | ФИО: %d | телефонов: %d | почт: %d' % (ssyl, fio, tel, mail))
print('не отдали карточку:', dict(pri))
q = lambda s: cur.execute(s).fetchone()[0]
print('фактов, у которых теперь есть карточка портала:',
      q("select count(distinct fakt_id) from fakt_ssylka where url like '%newapi/api/%'"))
p.close()

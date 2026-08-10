# -*- coding: utf-8 -*-
"""Вписываем найденные конкретные заключения ЭПБ вместо ссылки на перечень.

574 факта держались на `monitor-pb.ru/conclusions?exploiter=ИНН` — это СПИСОК всех
заключений предприятия, он доказывает предприятие, но не конкретную машину. Поиск по
перечню (параметр `q`) даёт строку с номером заключения, из номера собирается адрес
`/conclusion/<номер>` — проверено, такие страницы живы и содержат эксплуатанта.

Принимаем ТОЛЬКО те сопоставления, где заводской номер факта совпал целиком с «зав. № X»
в описании объекта. Совпадение «по словам» пишем в базу как ссылку-кандидата с пометкой,
но старую ссылку на перечень не трогаем: она честнее, чем чужой документ.
"""
import sqlite3, json, os, importlib.util

D = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('pb', os.path.join(D, 'park_build.py'))
pb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pb)
p = sqlite3.connect(os.path.join(D, 'park.db'))
cur = p.cursor()

FAYL = os.path.join(D, 'park_perechen2.jsonl')
if not os.path.exists(FAYL):
    raise SystemExit('нет %s — сначала скачать результат с сервера' % FAYL)

vs = po_zav = po_slovam = ne_nashli = uzhe = 0
for ln in open(FAYL, encoding='utf-8', errors='replace'):
    if not ln.strip():
        continue
    vs += 1
    try:
        z = json.loads(ln)
    except Exception:
        continue
    if not z.get('ssylka'):
        ne_nashli += 1
        continue
    fid, url = z['fakt_id'], z['ssylka']
    est = cur.execute('select 1 from fakt_ssylka where fakt_id=? and url=?',
                      (fid, url)).fetchone()
    if est:
        uzhe += 1
        continue
    raz = pb.razbor_url(url)
    if not raz:
        continue
    tochno = bool(z.get('po_zavodskomu'))
    cur.execute('insert or ignore into fakt_ssylka(fakt_id,url,domen,istochnik,etap,'
                'pervoistochnik,data_nablyudeniya,fayl) values (?,?,?,?,?,?,?,?)',
                (fid, url, raz[0], raz[1],
                 'заключение ЭПБ, найдено по заводскому номеру' if tochno else
                 'заключение ЭПБ, КАНДИДАТ по совпадению слов (заводской номер не сверен)',
                 raz[2], '', ''))
    if tochno:
        po_zav += 1
    else:
        po_slovam += 1
p.commit()
print('разобрано записей %d' % vs)
print('  ссылка по заводскому номеру (точно) .... %d' % po_zav)
print('  кандидат по совпадению слов ............ %d' % po_slovam)
print('  заключение не найдено .................. %d' % ne_nashli)
print('  ссылка уже была ........................ %d' % uzhe)

q = lambda s: cur.execute(s).fetchone()[0]
print('\nфактов, у которых ТОЛЬКО перечень и ничего больше:',
      q("""select count(*) from fakt where id in
             (select fakt_id from fakt_ssylka where url like '%conclusions?exploiter=%')
           and id not in (select fakt_id from fakt_ssylka where url like '%/conclusion/%')"""))
p.close()

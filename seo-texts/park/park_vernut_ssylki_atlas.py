# -*- coding: utf-8 -*-
"""Возврат ПОТЕРЯННЫХ ссылок 442 фактам — из исходной базы, а не поиском заново.

История ошибки. Эти факты пришли из `atlas_copco.db` без ссылок, и я сначала полез
добывать адреса ПОИСКОМ по ЕИС: 120 попыток, найдено 0. Причина была не в поиске —
закупки Норникеля и большинства этих предприятий идут через tender.pro, tektorg и ЭТП ГПБ,
в ЕИС их нет вовсе. Прежде чем добывать заново, надо было посмотреть в исходник. Смотрю:

    в atlas_copco.db.fakty 6 128 строк, у 4 588 есть НАСТОЯЩИЙ адрес
    (ещё у 7 стоит заглушка «https://ссылки нет: организация есть в выгрузке площадки» —
     это не адрес, и хорошо, что вливание её отвергло)

Сопоставление по ПОЛНОМУ тексту факта, а не по началу: обрезка до 120 знаков давала
склейки разных закупок с одинаковым началом («Поставка запасных частей для...»), и тогда
факту достался бы адрес чужой закупки — доказательство хуже, чем его отсутствие.

Ссылок несколько — строк несколько, как требует владелец.
"""
import collections, os, re, sqlite3

D = os.path.dirname(os.path.abspath(__file__))
p = sqlite3.connect(os.path.join(D, 'park.db'))
cur = p.cursor()
a = sqlite3.connect('file:%s?mode=ro' % os.path.join(D, 'atlas_copco.db'), uri=True)

import importlib.util
spec = importlib.util.spec_from_file_location('pb', os.path.join(D, 'park_build.py'))
pb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pb)


def nor(s):
    return re.sub(r'\s+', ' ', (s or '').strip().lower())


ist = collections.defaultdict(set)
for inn, cht, ss in a.execute("select inn, chto_naydeno, ssylka from fakty"):
    if ss and ss.startswith('http') and 'ссылки нет' not in ss:
        ist[(str(inn), nor(cht))].add(ss.strip())

bez = cur.execute("""select id, inn, coalesce(chto_naydeno,'') from fakt
                     where id not in (select fakt_id from fakt_ssylka)""").fetchall()
vernuto = 0
faktov = 0
ne_razobralas = 0
domeny = collections.Counter()
for fid, inn, cht in bez:
    adresa = ist.get((str(inn), nor(cht)))
    if not adresa:
        continue
    est = False
    for u in sorted(adresa):
        raz = pb.razbor_url(u)
        if not raz:
            ne_razobralas += 1
            continue
        # пояснение кладём в `etap` — свободное поле этой таблицы; колонки `pochemu`
        # у fakt_ssylka нет (проверено pragma table_info, а не по памяти)
        cur.execute("insert or ignore into fakt_ssylka(fakt_id, url, domen, istochnik,"
                    " pervoistochnik, etap) values (?,?,?,?,?,?)",
                    (fid, u, raz[0], raz[1], raz[2],
                     'адрес восстановлен из исходной atlas_copco.db: при вливании потерялся'))
        if cur.rowcount:
            vernuto += 1
            domeny[raz[0]] += 1
            est = True
    if est:
        faktov += 1
        cur.execute("update fakt set karantin='' where id=? and karantin like '%ссылк%'", (fid,))

p.commit()
print('фактов было без ссылки ..... %d' % len(bez))
print('  адрес возвращён у ........ %d фактов, строк-ссылок %d' % (faktov, vernuto))
print('  адрес не разобрался ...... %d' % ne_razobralas)
print('  по доменам:', dict(domeny.most_common(8)))
q = lambda s: cur.execute(s).fetchone()[0]
print('\n=== ПО БАЗЕ ===')
print('  фактов без ссылки ........ %d' % q("select count(*) from fakt where id not in (select fakt_id from fakt_ssylka)"))
print('  из них в парке ........... %d' % q("select count(*) from fakt where v_parke=1 and id not in (select fakt_id from fakt_ssylka)"))
print('  всего ссылок ............. %d' % q("select count(*) from fakt_ssylka"))
p.close()

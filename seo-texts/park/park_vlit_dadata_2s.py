# -*- coding: utf-8 -*-
"""Приём выгрузки DaData/ЕГРЮЛ от 2-й сессии: статус, адрес, руководитель, ОКВЭД.

Почему это ценно отдельно от checko: ссылка ведёт на `egrul.nalog.ru` — ПЕРВОИСТОЧНИК
(ФНС), а не агрегатор. У меня в карточке предприятия пустовали «Статус ЕГРЮЛ» и
«Сотрудники»; статус закрывается отсюда, и закрывается доказуемо.

Руководитель кладётся в contact_source как наблюдение вида `chelovek` со ссылкой на
выписку — это то же правило, что для остальных контактов: без ссылки не пишем. Директор
не технический ЛПР, но для части предприятий это единственное названное лицо.

Что НЕ делаем: не перезаписываем уже известный ОКВЭД (у него свой провенанс) и не
трогаем предприятия вне парка.

Запуск: python3 park_vlit_dadata_2s.py [файл.jsonl]
"""
import collections, json, os, re, sqlite3, sys, importlib.util

D = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('pb', os.path.join(D, 'park_build.py'))
pb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pb)

FAYL = os.path.join(D, sys.argv[1] if len(sys.argv) > 1 else 'PARK-DADATA-2S.jsonl')
p = sqlite3.connect(os.path.join(D, 'park.db'))
cur = p.cursor()
park = {r[0] for r in cur.execute('select inn from predpriyatie')}
est_okved = {r[0] for r in cur.execute("select inn from finansy where coalesce(okved,'')<>''")}

pri = collections.Counter()
vs = eg = ok = ruk = 0
for ln in open(FAYL, encoding='utf-8', errors='replace'):
    if not ln.strip():
        continue
    try:
        x = json.loads(ln)
    except Exception:
        pri['строка не разобралась'] += 1
        continue
    vs += 1
    inn = str(x.get('inn') or '').strip()
    if not re.fullmatch(r'\d{10}|\d{12}', inn):
        pri['ИНН не разобран'] += 1
        continue
    if inn not in park:
        pri['предприятия нет в парке'] += 1
        continue
    if x.get('error'):
        pri['в записи ошибка источника'] += 1
        continue
    url = (x.get('ssylka') or '').strip()
    imya = (x.get('full_name') or x.get('name') or '').strip()
    status = (x.get('status') or '').strip()
    adres = (x.get('address') or '').strip()
    rukovoditel = (x.get('mgmt_name') or '').strip()
    post = (x.get('mgmt_post') or '').strip()
    okved = (x.get('okved') or '').strip()

    cur.execute("""insert into egrul(inn, imya, adres, rukovoditel, dolzhnost_ruk, status,
                                     okved, istochnik, ts)
                   values (?,?,?,?,?,?,?,?,datetime('now'))
                   on conflict(inn) do update set
                     imya=coalesce(nullif(excluded.imya,''), imya),
                     adres=coalesce(nullif(excluded.adres,''), adres),
                     rukovoditel=coalesce(nullif(excluded.rukovoditel,''), rukovoditel),
                     dolzhnost_ruk=coalesce(nullif(excluded.dolzhnost_ruk,''), dolzhnost_ruk),
                     status=coalesce(nullif(excluded.status,''), status),
                     okved=coalesce(nullif(excluded.okved,''), okved),
                     istochnik=excluded.istochnik""",
                (inn, imya, adres, rukovoditel, post, status, okved,
                 'DaData findById/party (ЕГРЮЛ), ' + url))
    eg += 1

    if okved and inn not in est_okved:
        cur.execute("insert or ignore into finansy(inn, ts) values (?, datetime('now'))", (inn,))
        cur.execute("update finansy set okved=?, okved_otkuda=? where inn=? "
                    "and coalesce(okved,'')=''",
                    (okved, 'ЕГРЮЛ через DaData (2-я сессия): ' + url, inn))
        ok += 1
        est_okved.add(inn)

    raz = pb.razbor_url(url)
    if rukovoditel and raz:
        cur.execute('insert or ignore into contact_source(inn,vid,znachenie,person,dolzhnost,'
                    'istochnik,source_url,domen,pervoistochnik,data_nablyudeniya,quote,kto)'
                    ' values (?,?,?,?,?,?,?,?,?,?,?,?)',
                    (inn, 'chelovek', rukovoditel[:200], rukovoditel[:200],
                     post[:120] or 'руководитель по ЕГРЮЛ', raz[1], url, raz[0], raz[2], '',
                     'выписка ЕГРЮЛ: %s — %s' % (post or 'руководитель', rukovoditel),
                     '2-я сессия, DaData/ЕГРЮЛ'))
        ruk += 1

p.commit()
print('строк на входе %d' % vs)
print('  реквизитов ЕГРЮЛ записано ... %d' % eg)
print('  ОКВЭД, которого не было ..... %d' % ok)
print('  руководителей со ссылкой .... %d' % ruk)
print('  пропуски:', dict(pri.most_common(6)))
q = lambda s: cur.execute(s).fetchone()[0]
print('\n=== ПО БАЗЕ ===')
print('  строк в egrul ............... %d' % q('select count(*) from egrul'))
print('  статус ЕГРЮЛ у предприятий .. %d' % q(
    "select count(*) from egrul e join predpriyatie x on x.inn=e.inn where coalesce(e.status,'')<>''"))
print('  ОКВЭД по парку .............. %d' % q(
    "select count(*) from finansy f join predpriyatie e on e.inn=f.inn where coalesce(f.okved,'')<>''"))
p.close()

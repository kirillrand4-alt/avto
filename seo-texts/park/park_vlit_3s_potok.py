# -*- coding: utf-8 -*-
"""ОДИН приёмник потоков 3-й сессии (PARK-EIS-TIK*.jsonl и park_ingest_*.jsonl).

Зачем ещё один. Приёмников уже четыре — `park_vlit_3b/3d/4/3s_eis_tik3` — и в каждом СВОЯ
копия списка типов, своя копия заслонов. Разъезд стоил нам двух дефектов: садовые
воздуходувки прошли в парк там, где копии заслона не было, а заслон «заказчик-посредник»
жил только в одном файле из четырёх. Здесь ни одного правила локально нет: тип, вид,
заслоны и форма карточки берутся из `park_build`.

Что делаем сверх присланного:
  * из поисковой ссылки достаём реестровый номер и строим адрес КАРТОЧКИ закупки
    (поиск `extendedsearch` рисуется скриптом — ни ИНН, ни предмета в теле нет,
    доказательством он не является и в базу не идёт);
  * сохраняем ВСЕ остальные её ссылки отдельными строками — правило владельца
    «ссылок несколько = строк несколько».

Запуск: python3 park_vlit_3s_potok.py <файл> [<файл> ...]
"""
import collections, importlib.util, json, os, re, sqlite3, sys, time

D = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('pb', os.path.join(D, 'park_build.py'))
pb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pb)
p = sqlite3.connect(os.path.join(D, 'park.db'))
cur = p.cursor()
INN = re.compile(r'^\d{10}$|^\d{12}$')
FAYLY = sys.argv[1:]
if not FAYLY:
    raise SystemExit('укажите файлы потока')

vs = pr = ot = 0
pri = collections.Counter()
inny, novye, ssyl = set(), set(), 0
bylo_inn = {r[0] for r in cur.execute('select distinct inn from fakt where v_parke=1')}

for fayl in FAYLY:
    imya = os.path.basename(fayl)
    for ln in open(fayl, encoding='utf-8', errors='replace'):
        if not ln.strip():
            continue
        vs += 1
        try:
            r = json.loads(ln)
        except Exception:
            pri['строка не разобралась'] += 1; ot += 1; continue
        inn = (r.get('inn') or '').strip()
        predmet = (r.get('predmet') or '').strip()
        imya_org = (r.get('zakazchik') or r.get('predpriyatie') or r.get('org_imya') or '').strip()
        istochniki = [u.strip() for u in (r.get('istochniki') or '').split('|') if u.strip()]
        # номер: либо прислан полем, либо вынимается из её же ссылки-поиска
        nomer = re.sub(r'\D', '', r.get('nomer') or '')
        if len(nomer) not in (11, 19):
            nomer = next((n for n in (pb.nomer_iz_poiska(u) for u in istochniki) if n), '')
        if not INN.match(inn):
            pri['ИНН не снят с карточки'] += 1; ot += 1; continue
        if not predmet:
            pri['пустой предмет закупки'] += 1; ot += 1; continue
        if r.get('slovo_podtverzhdeno_tekstom') is False:
            pri['слово не подтверждено текстом карточки (заслон 3-й)'] += 1; ot += 1; continue
        if pb.sadovaya(predmet):
            pri['садовый или бытовой инструмент, не наша машина'] += 1; ot += 1; continue
        if pb.posrednik(imya_org):
            pri['заказчик-посредник: машина встанет не у него'] += 1; ot += 1; continue
        tip, vid, princip = pb.razobrat_predmet(predmet)
        if not tip:
            pri['тип машины из предмета не определился'] += 1; ot += 1; continue
        kart = pb.kartochka_zakupki(nomer)
        # карточка организации-заказчика тоже доказательство ИНН, но не машины
        org_kart = (r.get('zakazchik_kartochka') or '').strip()
        prochie = [u for u in istochniki
                   if 'extendedsearch' not in u and u != kart and u != org_kart]
        if not kart and not prochie:
            pri['открываемого адреса нет: только поиск'] += 1; ot += 1; continue
        dedup = '|'.join([inn, tip, '', '', '', nomer])
        cur.execute(
            'insert or ignore into fakt(inn,nazvanie,tip,sostoyanie,marka,model,napisanie,'
            'zavodskoy_nomer,sreda,summa,data_fakta,srok_do,sila,chem_rang,chto_naydeno,'
            'pochemu,uverennost,kto,karantin,dedup,ts,v_parke,vid_fakta,princip) '
            'values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?)',
            (inn, imya_org[:200], tip,
             'закупка' if vid == 'машина' else ('сервис' if vid == 'расходник' else 'узел'),
             '', '', '', '', '', (r.get('summa') or ''), '', '',
             2, 'E: закупка, класс машины отсюда не следует', predmet[:500],
             'закупка в ЕИС; ИНН снят с карточки закупки', 'vysokaya',
             (r.get('kto') or '3-я сессия') + '; принято 1-й из ' + imya, '', dedup,
             time.strftime('%Y-%m-%d %H:%M:%S'), vid, princip))
        row = cur.execute('select id from fakt where dedup=?', (dedup,)).fetchone()
        if row:
            for u, etap in ([(kart, 'карточка закупки')] if kart else []) + \
                           ([(org_kart, 'карточка организации-заказчика')] if org_kart else []) + \
                           [(u, 'ссылка из потока 3-й сессии') for u in prochie]:
                raz = pb.razbor_url(u)
                if not raz:
                    continue
                cur.execute('insert or ignore into fakt_ssylka(fakt_id,url,domen,istochnik,'
                            'etap,pervoistochnik,data_nablyudeniya,fayl) values (?,?,?,?,?,?,?,?)',
                            (row[0], u, raz[0], raz[1], etap, raz[2], '', imya))
                ssyl += cur.rowcount
        inny.add(inn)
        if inn not in bylo_inn:
            novye.add(inn)
        pr += 1

if pr + ot != vs:
    pri['!НЕ СОШЛОСЬ'] = vs - pr - ot
cur.execute('insert into zhurnal_vlivaniya values (?,?,?,?,?,?)',
            (time.strftime('%Y-%m-%d %H:%M:%S'),
             'ПОТОК 3-й СЕССИИ (общий приёмник): ' + ', '.join(os.path.basename(f) for f in FAYLY),
             vs, pr, ot, json.dumps(dict(pri), ensure_ascii=False)))
p.commit()
q = lambda s: cur.execute(s).fetchone()[0]
print('строк на входе %d | принято %d | брак %d' % (vs, pr, ot))
for k, v in pri.most_common():
    print('    %-58s %d' % (k, v))
print('предприятий в потоке %d | новых для парка %d | новых строк ссылок %d'
      % (len(inny), len(novye), ssyl))
print()
print('=== БАЗА ПОСЛЕ ВЛИВАНИЯ ===')
print('  фактов %d | в парке %d | ИНН в парке %d | ссылок %d'
      % (q('select count(*) from fakt'), q('select count(*) from fakt where v_parke=1'),
         q('select count(distinct inn) from fakt where v_parke=1'),
         q('select count(*) from fakt_ssylka')))
p.close()

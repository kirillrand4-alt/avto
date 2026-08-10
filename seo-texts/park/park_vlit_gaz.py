# -*- coding: utf-8 -*-
"""Приём оси РАСХОДА ГАЗА в park.db.

Что это за факт: предприятие ПОКУПАЕТ или АРЕНДУЕТ азот/кислород — баллоны, жидкий,
криоцистерну, газификатор. Это НЕ владелец генератора, а наш ЦЕЛЕВОЙ ПОКУПАТЕЛЬ:
ему генератор продают вместо того, чтобы он и дальше возил баллоны.

Поэтому:
  vid_fakta = 'газ'   (ось расхода, не «эксплуатирует машину»)
  sostoyanie = 'покупает ГАЗ'
  tip = генератор кислорода / генератор азота — по тому, ЧТО он покупает;
        если в предмете и то и другое — заводим ДВА факта, а не склеиваем.

Ссылок в базе две на факт, как требует владелец: карточка закупки и поиск по номеру.
"""
import sqlite3, json, re, os, time, importlib.util, collections

D = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('pb', os.path.join(D, 'park_build.py'))
pb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pb)
p = sqlite3.connect(os.path.join(D, 'park.db'))
cur = p.cursor()
INN = re.compile(r'^\d{10}$|^\d{12}$')

def bez_probelov(t):
    return re.sub(r'\s+', '', (t or '').lower().replace('ё', 'е'))

_KISL = re.compile(r'кислород')
_AZOT = re.compile(r'азот')
# аренда баллонов/криоцистерны — тоже расход, но состояние другое
_ARENDA = re.compile(r'аренд|прокат|пользован')

def tipy(predmet):
    n = bez_probelov(predmet)
    t = []
    if _KISL.search(n): t.append('генератор кислорода')
    if _AZOT.search(n): t.append('генератор азота')
    return t or ['генератор кислорода']   # запросы были только про эти два газа

vs = pr = ot = kont_t = kont_m = 0
pri = collections.Counter()
inny = set()
fayl = os.path.join(D, 'park_gaz_inn.jsonl')
for ln in open(fayl, encoding='utf-8'):
    if not ln.strip():
        continue
    vs += 1
    r = json.loads(ln)
    inn = (r.get('inn') or '').strip()
    nomer = (r.get('nomer') or '').strip()
    predmet = (r.get('predmet') or '').strip()
    url = (r.get('url_kartochki') or '').strip()
    if not INN.match(inn):
        pri['ИНН с карточки не снялся'] += 1; ot += 1; continue
    if not url:
        pri['нет адреса карточки'] += 1; ot += 1; continue
    if not predmet:
        pri['пустой предмет закупки'] += 1; ot += 1; continue
    if r.get('nomer_na_stranice') is False:
        pri['номера закупки нет на странице — карточка чужая'] += 1; ot += 1; continue
    sost = 'арендует' if _ARENDA.search(bez_probelov(predmet)) else 'покупает ГАЗ'
    for tip in tipy(predmet):
        dedup = '|'.join([inn, tip, '', '', '', nomer])
        cur.execute(
            'insert or ignore into fakt(inn,nazvanie,tip,sostoyanie,marka,model,napisanie,'
            'zavodskoy_nomer,sreda,summa,data_fakta,srok_do,sila,chem_rang,chto_naydeno,'
            'pochemu,uverennost,kto,karantin,dedup,ts,v_parke,vid_fakta) '
            'values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?)',
            (inn, (r.get('org_imya') or r.get('zakazchik_iz_lenty') or '')[:200], tip, sost,
             '', '', '', '', 'кислород' if 'кислород' in tip else 'азот', '', '', '',
             2, 'E: закупка газа, класс машины отсюда не следует', predmet[:500],
             'ось РАСХОДА: предприятие покупает газ, значит генератора у него нет — '
             'целевой покупатель. ИНН: %s' % (r.get('inn_otkuda') or 'карточка ЕИС'),
             'vysokaya', '1-я сессия, ось расхода газа (ЕИС)', '', dedup,
             time.strftime('%Y-%m-%d %H:%M:%S'), 'газ'))
        row = cur.execute('select id from fakt where dedup=?', (dedup,)).fetchone()
        if not row:
            continue
        # ТОЛЬКО КАРТОЧКА. Раньше рядом писалась ссылка-поиск по тому же номеру —
        # она открывается, но результаты рисует скрипт: 3 622 знака, ни ИНН, ни предмета.
        # Это показывает, КАК искали, а не ЧТО нашли; 14 462 такие строки уже убраны из
        # базы, и источник больше их не создаёт.
        for u in (url,):
            raz = pb.razbor_url(u)
            if raz:
                cur.execute('insert or ignore into fakt_ssylka(fakt_id,url,domen,istochnik,etap,'
                            'pervoistochnik,data_nablyudeniya,fayl) values (?,?,?,?,?,?,?,?)',
                            (row[0], u, raz[0], raz[1],
                             'карточка закупки' if u == url else 'поиск по реестровому номеру',
                             raz[2], '', ''))
    # КОНТАКТ заказчика с той же карточки: у газового сегмента контактов почти нет,
    # а блок «Контактное лицо / Телефон / Почта» стоит на той же странице, что и ИНН.
    fio = (r.get('kontakt_fio') or '').strip()
    tel = re.sub(r'\D', '', r.get('kontakt_tel') or '')[-10:]
    mail = (r.get('kontakt_email') or '').strip()
    raz = pb.razbor_url(url)
    if raz:
        if len(tel) == 10:
            cur.execute('insert or ignore into contact_source(inn,vid,znachenie,person,dolzhnost,'
                        'istochnik,source_url,domen,pervoistochnik,data_nablyudeniya,quote,kto) '
                        'values (?,?,?,?,?,?,?,?,?,?,?,?)',
                        (inn, 'telefon', tel, fio[:200], 'контактное лицо закупки', raz[1],
                         url, raz[0], raz[2], '', ('карточка ЕИС №%s: %s' % (nomer, predmet))[:300],
                         '1-я сессия, контакт с карточки ЕИС (ось расхода газа)'))
            kont_t += 1
        if '@' in mail:
            cur.execute('insert or ignore into contact_source(inn,vid,znachenie,person,dolzhnost,'
                        'istochnik,source_url,domen,pervoistochnik,data_nablyudeniya,quote,kto) '
                        'values (?,?,?,?,?,?,?,?,?,?,?,?)',
                        (inn, 'pochta', mail, fio[:200], 'контактное лицо закупки', raz[1],
                         url, raz[0], raz[2], '', ('карточка ЕИС №%s' % nomer)[:300],
                         '1-я сессия, контакт с карточки ЕИС (ось расхода газа)'))
            kont_m += 1
    inny.add(inn)
    pr += 1

if pr + ot != vs:
    pri['!НЕ СОШЛОСЬ'] = vs - pr - ot
cur.execute('insert into zhurnal_vlivaniya values (?,?,?,?,?,?)',
            (time.strftime('%Y-%m-%d %H:%M:%S'), 'ОСЬ РАСХОДА ГАЗА: закупки ЕИС с ИНН',
             vs, pr, ot, json.dumps(dict(pri), ensure_ascii=False)))
p.commit()
q = lambda s: cur.execute(s).fetchone()[0]
print('закупок на входе %d | принято %d | брак %d %s' % (vs, pr, ot, dict(pri)))
print('предприятий-покупателей газа:', len(inny))
print('контактов с карточек: телефонов %d, почт %d' % (kont_t, kont_m))
print()
print('=== ОСЬ РАСХОДА В БАЗЕ ===')
print('  фактов vid_fakta=газ: %d на %d ИНН'
      % (q("select count(*) from fakt where vid_fakta='газ'"),
         q("select count(distinct inn) from fakt where vid_fakta='газ'")))
for r in cur.execute("select tip, sostoyanie, count(*), count(distinct inn) from fakt "
                     "where vid_fakta='газ' group by 1,2 order by 3 desc").fetchall():
    print('    %-22s %-14s фактов %5d  ИНН %4d' % (r[0], r[1], r[2], r[3]))
print()
print('  из них ИНН, которых в парке ещё НЕ БЫЛО:',
      q("""select count(*) from (select distinct inn from fakt where vid_fakta='газ'
           except select distinct inn from fakt where coalesce(vid_fakta,'')<>'газ')"""))
print('  всего ИНН в парке:', q('select count(distinct inn) from fakt where v_parke=1'))
p.close()

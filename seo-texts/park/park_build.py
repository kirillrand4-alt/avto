# -*- coding: utf-8 -*-
"""park_build.py — схема park.db и вливание atlas_copco.db + b2b_rekvizity.db + master.

Канон PARK-RESHENIYA:
  * ссылка на каждый факт и каждый контакт; ссылок несколько -> НЕСКОЛЬКО СТРОК;
  * настоящий источник выводится из ДОМЕНА ссылки, ярлык истории идёт в `etap`;
  * агрегатор (checko/list-org) не считается подтверждением — отдельный счётчик;
  * ключ дедупа факта: inn+tip+marka+model+zavodskoy_nomer+data;
  * контакт = ИНН + 10 цифр (тел) / ИНН + адрес (почта); ssylok растит, imen роняет;
  * счёт ведём ИЗ БАЗЫ, каждое вливание пишем в zhurnal_vlivaniya со сверкой.
"""
import sqlite3, re, os, sys, json, time

D = os.path.dirname(os.path.abspath(__file__))
PARK = os.path.join(D, 'park.db')
AC = os.path.join(D, 'atlas_copco.db')
B2B = os.path.join(D, 'b2b_rekvizity.db')
MASTER = os.path.join(D, 'master-base.sqlite')

SHEMA = """
CREATE TABLE IF NOT EXISTS fakt(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  inn TEXT, nazvanie TEXT,
  tip TEXT, sostoyanie TEXT,
  marka TEXT, model TEXT, napisanie TEXT, zavodskoy_nomer TEXT, sreda TEXT,
  summa TEXT, data_fakta TEXT, srok_do TEXT,
  sila INTEGER, chem_rang TEXT, rang_mashiny REAL,
  chto_naydeno TEXT, pochemu TEXT, uverennost TEXT,
  kto TEXT, karantin TEXT,
  dedup TEXT UNIQUE, ts TEXT);
CREATE INDEX IF NOT EXISTS i_f_inn ON fakt(inn);
CREATE INDEX IF NOT EXISTS i_f_sila ON fakt(sila);

CREATE TABLE IF NOT EXISTS fakt_ssylka(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  fakt_id INTEGER, url TEXT, domen TEXT,
  istochnik TEXT, etap TEXT, pervoistochnik INTEGER,
  data_nablyudeniya TEXT, fayl TEXT,
  UNIQUE(fakt_id, url, istochnik));
CREATE INDEX IF NOT EXISTS i_fs_fakt ON fakt_ssylka(fakt_id);

CREATE TABLE IF NOT EXISTS contact_source(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  inn TEXT, vid TEXT, znachenie TEXT,
  person TEXT, dolzhnost TEXT,
  istochnik TEXT, source_url TEXT, domen TEXT, pervoistochnik INTEGER,
  data_nablyudeniya TEXT, quote TEXT, kto TEXT,
  UNIQUE(inn, vid, znachenie, source_url, person));
CREATE INDEX IF NOT EXISTS i_cs_inn ON contact_source(inn);
CREATE INDEX IF NOT EXISTS i_cs_zn ON contact_source(znachenie);

CREATE TABLE IF NOT EXISTS kontakt(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  inn TEXT, vid TEXT, znachenie TEXT,
  person TEXT, dolzhnost TEXT, rol TEXT, rang INTEGER,
  ssylok INTEGER, ssylok_pervoistochnik INTEGER,
  imen INTEGER, innov INTEGER, lichnyy INTEGER, mobilnyy INTEGER,
  ts TEXT, UNIQUE(inn, vid, znachenie));
CREATE INDEX IF NOT EXISTS i_k_inn ON kontakt(inn);

CREATE TABLE IF NOT EXISTS spravochnik(
  inn TEXT PRIMARY KEY, name TEXT, okved TEXT, okved_all TEXT, region TEXT,
  address TEXT, egrul_status TEXT, director TEXT, revenue_rub TEXT,
  division TEXT, segment TEXT);

CREATE TABLE IF NOT EXISTS rekvizity(
  inn TEXT PRIMARY KEY, nazv_polnoe TEXT, kpp TEXT, ogrn TEXT, okpo TEXT,
  adres_jur TEXT, telefon TEXT, email TEXT, istochnik TEXT);

CREATE TABLE IF NOT EXISTS fakt_bez_inn(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  nazvanie TEXT, tip TEXT, sostoyanie TEXT, model TEXT, napisanie TEXT,
  chto_naydeno TEXT, url TEXT, domen TEXT, istochnik TEXT, data_fakta TEXT,
  kto TEXT, ts TEXT, UNIQUE(nazvanie, chto_naydeno, url));

CREATE TABLE IF NOT EXISTS zhurnal_vlivaniya(
  ts TEXT, chto TEXT, strok_v_istochnike INTEGER, prinyato INTEGER,
  otbrakovano INTEGER, prichina TEXT);
"""

# ---- домен -> (настоящий источник, первоисточник да/нет) -------------------
DOMEN = {
    'etpgpb.ru': ('ЭТП ГПБ', 1), 'www.tender.pro': ('Tender.pro', 1),
    'tender.pro': ('Tender.pro', 1), 'zakupki.mos.ru': ('Портал поставщиков Москвы', 1),
    'www.tektorg.ru': ('ТЭК-Торг', 1), 'tektorg.ru': ('ТЭК-Торг', 1),
    'zakupki.gov.ru': ('ЕИС', 1), 'monitor-pb.ru': ('Монитор ПБ (ЭПБ)', 1),
    'www.roseltorg.ru': ('Росэлторг', 1), 'roseltorg.ru': ('Росэлторг', 1),
    'www.rts-tender.ru': ('РТС-тендер', 1), 'fabrikant.ru': ('Фабрикант', 1),
    'b2b-center.ru': ('B2B-Center', 1), 'www.b2b-center.ru': ('B2B-Center', 1),
    # агрегаторы — НЕ подтверждение (канон P25)
    'checko.ru': ('checko (АГРЕГАТОР)', 0), 'www.list-org.com': ('list-org (АГРЕГАТОР)', 0),
    'list-org.com': ('list-org (АГРЕГАТОР)', 0), 'www.rusprofile.ru': ('rusprofile (АГРЕГАТОР)', 0),
    'rusprofile.ru': ('rusprofile (АГРЕГАТОР)', 0),
}
_RTN = re.compile(r'gosnadzor\.ru$', re.I)
_URL = re.compile(r'^https?://([a-z0-9][a-z0-9.-]*\.[a-z]{2,})(?::\d+)?(?:[/?#]|$)', re.I)


_SADOVAYA = re.compile(
    r'ранцев|лесопожарн|садов|бытов|бензинов\w*\s+воздуходувк|аккумуляторн\w*\s+воздуходувк|'
    r'воздуходувк\w*\s+(ранцев|бензинов|аккумуляторн|ручн)|уборк\w+\s+листв|снегоубор|'
    r'опрыскиват|пылесос|метл', re.I)


def sadovaya(tekst):
    """Садовый или бытовой инструмент под нашим словом — «воздуходувка ранцевая бензиновая».

    Заслон стоял ТОЛЬКО в вливалке чужого потока, а свои три его не имели: 17 садовых
    воздуходувок дожили до парка, и одна из них вышла в случайный жребий («Поставка
    воздуходувки», спортивная школа, 115 190 ₽). Теперь правило одно и лежит здесь,
    чтобы не разъезжалось по вливалкам.
    """
    return bool(_SADOVAYA.search(tekst or ''))


def razbor_url(u):
    """-> (domen, istochnik, pervoistochnik) | None если это не URL."""
    u = (u or '').strip()
    m = _URL.match(u)
    if not m:
        return None
    d = m.group(1).lower()
    if d in DOMEN:
        ist, pi = DOMEN[d]
    elif _RTN.search(d):
        ist, pi = 'Ростехнадзор', 1
    elif d.startswith('egrul.nalog.ru'):
        ist, pi = 'ЕГРЮЛ (ФНС)', 1
    else:
        ist, pi = 'сайт предприятия ' + d, 1   # свой домен — первоисточник
    return d, ist, pi


SOST = {'stoit': 'эксплуатирует', 'pokupayut': 'покупает машину',
        'prodayut': 'ПРОДАЁТ (дилер, не владелец)', 'planiruyut': 'планирует',
        'neyasno': 'неясно'}

_TO = re.compile(r'(?i)\b(ремонт|техническ\w+ обслуж|\bТО\b|запчаст|зип|фильтр|масл|'
                 r'капитальн\w+ ремонт|сервисн)')
_POKUPKA = re.compile(r'(?i)\b(поставк|приобретен|закупк\w+ компрессор|покупк)')


def sila_fakta(sostoyanie, istochniki, tekst):
    """Лесенка PARK-RESHENIYA. Возвращает (sila, chem)."""
    ist = ' '.join(istochniki)
    if 'Ростехнадзор' in ist or 'ЭПБ' in ist:
        return 1, 'надзорная запись об эксплуатации'
    if sostoyanie == 'эксплуатирует' and _TO.search(tekst or ''):
        return 2, 'закупка обслуживания (ТО/ремонт/ЗИП)'
    if sostoyanie == 'планирует':
        return 3, 'план закупки — намерение'
    if sostoyanie == 'покупает машину':
        return 5, 'закупка на покупку машины'
    if sostoyanie == 'эксплуатирует':
        return 2, 'машина названа как имеющаяся'
    return 6, 'упоминание'


def tip_po_tekstu(t):
    t = (t or '').lower()
    for w, tip in (('воздуходувк', 'воздуходувка'), ('турбокомпрессор', 'турбокомпрессор'),
                   ('турбоагрегат', 'турбоагрегат'), ('нагнетател', 'нагнетатель'),
                   ('воздухоразделит', 'ВРУ'), ('генератор азот', 'генератор азота'),
                   ('генератор кислород', 'генератор кислорода'),
                   ('азотн', 'азотная установка'), ('кислородн', 'кислородная установка'),
                   ('мкс', 'МКС'), ('компрессор', 'компрессор')):
        if w in t:
            return tip
    return ''


def main():
    novaya = not os.path.exists(PARK)
    p = sqlite3.connect(PARK)
    p.executescript(SHEMA)
    cur = p.cursor()
    log = []

    def zhurnal(chto, vsego, prin, otbr, prich):
        cur.execute('insert into zhurnal_vlivaniya values (?,?,?,?,?,?)',
                    (time.strftime('%Y-%m-%d %H:%M:%S'), chto, vsego, prin, otbr, prich))
        log.append((chto, vsego, prin, otbr, prich))

    # ---------- 1. fakty из atlas_copco -----------------------------------
    a = sqlite3.connect('file:%s?mode=ro' % AC, uri=True).cursor()
    vsego = a.execute('select count(*) from fakty').fetchone()[0]
    prin = otbr = 0
    prichiny = {}
    # заслон: ярлыки, которые НЕ источник, а этап обработки
    ETAPY = ('сводка', 'разметк', 'отсев', 'полный свод', 'мусорн', 'факты по ссылке',
             'факты без машины', 'цель:', 'имеют (', 'покупали ранее', 'среда по предприятиям',
             'воздушные центробежники')
    for r in a.execute('select inn,nazvanie,tip_fakta,chto_naydeno,model,napisanie,'
                       'istochnik,istochnik_fayl,ssylka,data_fakta,summa,uverennost,pochemu '
                       'from fakty'):
        (inn, nazv, tf, chto, model, napis, ist_yarlyk, fayl, ssylka, data, summa,
         uver, pochemu) = r
        inn = (inn or '').strip()
        raz0 = razbor_url(ssylka)
        if not re.fullmatch(r'\d{10}|\d{12}', inn):
            # НЕ выбрасываем: ИНН неизвестен, но название и ссылка есть -> на резолв
            cur.execute('insert or ignore into fakt_bez_inn(nazvanie,tip,sostoyanie,model,'
                        'napisanie,chto_naydeno,url,domen,istochnik,data_fakta,kto,ts) '
                        'values (?,?,?,?,?,?,?,?,?,?,?,?)',
                        (nazv, tip_po_tekstu(chto), SOST.get(tf, tf or ''), model, napis,
                         chto, (ssylka or '').strip(), raz0[0] if raz0 else '',
                         raz0[1] if raz0 else (ist_yarlyk or ''), data,
                         'atlas_copco.db/fakty', time.strftime('%Y-%m-%d %H:%M:%S')))
            otbr += 1
            k = 'ИНН пустой -> в fakt_bez_inn на резолв по названию'
            prichiny[k] = prichiny.get(k, 0) + 1
            continue
        raz = razbor_url(ssylka)
        sost = SOST.get(tf, tf or 'неясно')
        etap = ist_yarlyk if any(e in (ist_yarlyk or '').lower() for e in ETAPY) else ''
        if raz:
            domen, istochnik, pi = raz
        else:
            # ссылки нет — источник берём из ярлыка, но помечаем недоказанным
            domen, pi = '', 0
            istochnik = ist_yarlyk if not etap else 'ярлык этапа, источник неизвестен'
        tip = tip_po_tekstu(chto) or tip_po_tekstu(model)
        sila, chem = sila_fakta(sost, [istochnik, ist_yarlyk or ''], chto)
        # без настоящей ссылки факт не может быть силы 1-2 (требование владельца)
        karantin = ''
        if not raz:
            karantin = 'нет ссылки-доказательства'
            sila = max(sila, 6)
        marka = (napis or '').strip()
        _m = (model or '').strip()
        if _m:
            # машина опознана: два документа об одной машине — ОДИН факт, ссылки копятся
            dedup = '|'.join([inn, tip, marka, _m, '', (data or '')])
        else:
            # машина НЕ опознана: склеивать разные документы нельзя — это разные
            # наблюдения, и схлопывание давало один «факт» с 54 ссылками
            dedup = '|'.join([inn, tip, marka, '', '',
                              (ssylka or '').strip() or (chto or '')[:120]])
        cur.execute('insert or ignore into fakt(inn,nazvanie,tip,sostoyanie,marka,model,'
                    'napisanie,zavodskoy_nomer,sreda,summa,data_fakta,srok_do,sila,chem_rang,'
                    'chto_naydeno,pochemu,uverennost,kto,karantin,dedup,ts) '
                    'values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (inn, nazv, tip, sost, marka, model, napis, '', '', summa, data, '',
                     sila, chem, chto, pochemu, uver, 'atlas_copco.db/fakty', karantin,
                     dedup, time.strftime('%Y-%m-%d %H:%M:%S')))
        fid = cur.execute('select id from fakt where dedup=?', (dedup,)).fetchone()[0]
        if raz:
            cur.execute('insert or ignore into fakt_ssylka(fakt_id,url,domen,istochnik,etap,'
                        'pervoistochnik,data_nablyudeniya,fayl) values (?,?,?,?,?,?,?,?)',
                        (fid, ssylka.strip(), domen, istochnik, etap, pi, data, fayl))
        prin += 1
    zhurnal('atlas_copco.fakty', vsego, prin, otbr, json.dumps(prichiny, ensure_ascii=False))
    p.commit()

    # ---------- 2. kontakty_svod -> contact_source ------------------------
    vsego = a.execute('select count(*) from kontakty_svod').fetchone()[0]
    prin = otbr = 0
    prichiny = {}
    for r in a.execute('select inn,person,post,rol,phone,email,istochnik,source_url,ts '
                       'from kontakty_svod'):
        inn, person, post, rol, phone, email, ist, surl, ts = r
        inn = (inn or '').strip()
        if not re.fullmatch(r'\d{10}|\d{12}', inn):
            otbr += 1; prichiny['ИНН не 10/12'] = prichiny.get('ИНН не 10/12', 0) + 1
            continue
        raz = razbor_url(surl)
        if raz:
            domen, istochnik, pi = raz
        else:
            domen, istochnik, pi = '', (ist or 'источник не назван'), 0
            prichiny['ссылка не URL (проза/пусто)'] = prichiny.get('ссылка не URL (проза/пусто)', 0) + 1
        for vid, zn in (('telefon', phone), ('email', email)):
            zn = (zn or '').strip()
            if not zn:
                continue
            if vid == 'telefon':
                d = re.sub(r'\D', '', zn)
                if len(d) < 10:
                    continue
                zn = d[-10:]
            else:
                zn = zn.lower()
            cur.execute('insert or ignore into contact_source(inn,vid,znachenie,person,'
                        'dolzhnost,istochnik,source_url,domen,pervoistochnik,'
                        'data_nablyudeniya,quote,kto) values (?,?,?,?,?,?,?,?,?,?,?,?)',
                        (inn, vid, zn, (person or '').strip(), (post or '').strip(),
                         istochnik, (surl or '').strip(), domen, pi, (ts or '')[:10],
                         '', 'atlas_copco.db/kontakty_svod'))
            prin += 1
    zhurnal('atlas_copco.kontakty_svod -> contact_source', vsego, prin, otbr,
            json.dumps(prichiny, ensure_ascii=False))
    p.commit()

    # ---------- 3. свод kontakt из наблюдений -----------------------------
    cur.execute('delete from kontakt')
    cur.execute("""
      insert into kontakt(inn,vid,znachenie,person,dolzhnost,ssylok,ssylok_pervoistochnik,
                          imen,innov,lichnyy,mobilnyy,ts)
      select cs.inn, cs.vid, cs.znachenie,
             (select person from contact_source x where x.inn=cs.inn and x.vid=cs.vid
                and x.znachenie=cs.znachenie and x.person!='' order by length(x.person) desc limit 1),
             (select dolzhnost from contact_source x where x.inn=cs.inn and x.vid=cs.vid
                and x.znachenie=cs.znachenie and x.dolzhnost!='' limit 1),
             count(distinct case when cs.source_url like 'http%' then cs.source_url end),
             count(distinct case when cs.pervoistochnik=1 and cs.source_url like 'http%'
                   then cs.source_url end),
             count(distinct case when cs.person!='' then lower(cs.person) end),
             (select count(distinct y.inn) from contact_source y
                where y.vid=cs.vid and y.znachenie=cs.znachenie),
             0, 0, ?
      from contact_source cs group by cs.inn, cs.vid, cs.znachenie""",
                (time.strftime('%Y-%m-%d %H:%M:%S'),))
    # флаги по канону с тремя поправками 1-й сессии
    cur.execute("update kontakt set lichnyy = case when imen=1 and ssylok_pervoistochnik>=1 "
                "and innov=1 then 1 else 0 end")
    cur.execute("update kontakt set mobilnyy = case when vid='telefon' and "
                "substr(znachenie,1,1)='9' then 1 else 0 end")
    p.commit()

    # ---------- 4. b2b_rekvizity ------------------------------------------
    if os.path.exists(B2B):
        b = sqlite3.connect('file:%s?mode=ro' % B2B, uri=True).cursor()
        vsego = b.execute('select count(*) from b2b_rekvizity').fetchone()[0]
        prin = otbr = 0
        for r in b.execute('select inn,nazv_polnoe,kpp,ogrn,okpo,adres_jur,telefon,email '
                           'from b2b_rekvizity'):
            inn = (r[0] or '').strip()
            if not re.fullmatch(r'\d{10}|\d{12}', inn):
                otbr += 1; continue
            cur.execute('insert or replace into rekvizity values (?,?,?,?,?,?,?,?,?)',
                        (inn, r[1], r[2], r[3], r[4], r[5], r[6], r[7], 'B2B-Center'))
            prin += 1
        zhurnal('b2b_rekvizity.db', vsego, prin, otbr, '')
        p.commit()

    # ---------- 5. master-base КАК СПРАВОЧНИК (НЕ источник фактов) --------
    if os.path.exists(MASTER):
        m = sqlite3.connect('file:%s?mode=ro' % MASTER, uri=True).cursor()
        vsego = m.execute('select count(*) from master').fetchone()[0]
        prin = 0
        for r in m.execute('select inn,name,okved,okved_all,region,address,egrul_status,'
                           'director,revenue_rub,division,segment from master'):
            inn = (r[0] or '').strip()
            if not re.fullmatch(r'\d{10}|\d{12}', inn):
                continue
            cur.execute('insert or replace into spravochnik values (?,?,?,?,?,?,?,?,?,?,?)',
                        (inn,) + tuple(r[1:]))
            prin += 1
        zhurnal('master-base.sqlite -> spravochnik (НЕ факты: equipment=наш прайс)',
                vsego, prin, vsego - prin, 'колонка equipment НЕ импортирована сознательно')
        p.commit()

    # ---------- отчёт ------------------------------------------------------
    print('=== ЖУРНАЛ ВЛИВАНИЯ ===')
    for row in log:
        print('  %-52s всего=%-7s принято=%-7s брак=%s  %s' % row)
    print()
    print('=== ЧТО В БАЗЕ (счёт ИЗ БАЗЫ) ===')
    for q, t in (("select count(*) from fakt", 'фактов'),
                 ("select count(distinct inn) from fakt", 'ИНН с фактом'),
                 ("select count(*) from fakt where karantin=''", 'фактов со ссылкой'),
                 ("select count(distinct inn) from fakt where karantin=''", 'ИНН с доказанным фактом'),
                 ("select count(*) from fakt_ssylka", 'ссылок-доказательств'),
                 ("select count(*) from contact_source", 'наблюдений контакта'),
                 ("select count(*) from kontakt", 'контактов после свёртки'),
                 ("select count(distinct inn) from kontakt", 'ИНН с контактом'),
                 ("select count(*) from kontakt where lichnyy=1", 'ЛИЧНЫХ и доказанных'),
                 ("select count(*) from kontakt where lichnyy=1 and mobilnyy=1", 'ЛИЧНЫХ МОБИЛЬНЫХ'),
                 ("select count(*) from spravochnik", 'справочник предприятий'),
                 ("select count(*) from rekvizity", 'реквизитов B2B')):
        print('  %-34s %s' % (t, cur.execute(q).fetchone()[0]))
    print()
    print('=== ФАКТЫ ПО СИЛЕ ===')
    for r in cur.execute('select sila,count(*),count(distinct inn) from fakt group by 1 order by 1'):
        print('  сила %s: строк=%-6s ИНН=%s' % r)
    print('=== ПО СОСТОЯНИЮ ===')
    for r in cur.execute('select sostoyanie,count(*),count(distinct inn) from fakt group by 1 order by 2 desc'):
        print('  %-32s строк=%-6s ИНН=%s' % r)
    print('=== ИСТОЧНИКИ ССЫЛОК (настоящие, из домена) ===')
    for r in cur.execute('select istochnik,pervoistochnik,count(*) from fakt_ssylka '
                         'group by 1,2 order by 3 desc limit 15'):
        print('  %-34s первоист=%s  %s' % r)
    p.close()


if __name__ == '__main__':
    main()

# -*- coding: utf-8 -*-
"""Принимает единую базу 3-й сессии: «предприятие + номер» со ссылкой, цитатой и видом номера.

`PARK-BAZA-EDINAYA-3S.csv` — 10 541 строка, 19 колонок. Ценность в трёх полях, которых у меня
своих нет:

    vid_nomera      — ЛИЧНЫЙ МОБИЛЬНЫЙ / городской / 8-800 / приёмная / «номер у N предприятий»
    chem_dokazan    — насколько твёрдо номер привязан к человеку («номер и фамилия в одной
                      цитате» / «цитаты нет» / «номера в цитате нет»)
    citata          — сам кусок текста, где номер стоит рядом с фамилией

Она честно предупредила в описи: «579 — это сколько ПОМЕЧЕНО личным мобильным, а не сколько
доказано; твёрдо доказанных 199». Это ровно та же граница, которую я мерил снимками (92 из
251 доказаны на картинке), поэтому вид номера и степень доказанности храню РАЗДЕЛЬНО и в
панель отдаю обе — иначе «личный мобильный» будет читаться как «доказанный личный».

Контакты идут в `contact_source` со ссылкой (правило владельца: контакт без ссылки за
доказанный не выдаётся). Несколько источников она даёт через « | » — раскладываю их
ОТДЕЛЬНЫМИ строками, как она и просит в описи: склейка теряет, какое поле откуда.

Запуск: python3 park_1s_prinyat_bazu_3s.py [--pisat]
"""
import csv, os, re, sqlite3, sys, time

D = os.path.dirname(os.path.abspath(__file__))
PISAT = '--pisat' in sys.argv
FAYL = os.path.join(D, 'PARK-BAZA-EDINAYA-3S.csv')
csv.field_size_limit(10 ** 7)


def telefon(t):
    c = re.sub(r'\D', '', str(t or ''))
    if len(c) == 11 and c[0] in '78':
        return '7' + c[1:]
    return c if len(c) == 10 else ''


p = sqlite3.connect(os.path.join(D, 'park.db'), timeout=180)
c = p.cursor()
c.execute("""create table if not exists nomer_vid(
    inn text, nomer text, vid_nomera text, chem_dokazan text, prinadlezhnost text,
    chelovek text, dolzhnost text, citata text, kanalov integer, istochnikov integer,
    ts text, primary key(inn, nomer))""")
vydacha = {r[0] for r in c.execute("""select distinct inn from fakt where v_parke=1
             and coalesce(v_obzvone,0)=0 and coalesce(posrednik,0)=0""")}
bylo_cs = c.execute('select count(*) from contact_source').fetchone()[0]
est = {(r[0], r[1], r[2]) for r in
       c.execute("select inn, vid, znachenie from contact_source")}

itog = {'строк в файле': 0, 'вне выдачи': 0, 'телефон принят': 0, 'почта принята': 0,
        'вид номера записан': 0, 'без ссылки — не берём': 0}
for r in csv.DictReader(open(FAYL, encoding='utf-8-sig'), delimiter=';'):
    itog['строк в файле'] += 1
    inn = (r.get('inn') or '').strip()
    if not re.fullmatch(r'\d{10}|\d{12}', inn):
        continue
    if inn not in vydacha:
        itog['вне выдачи'] += 1
        continue
    chel = (r.get('chelovek') or '').strip()
    dolzh = (r.get('dolzhnost') or '').strip()
    # несколько источников раскладываем отдельными строками, а не склейкой через « | »
    ssylki = [u.strip() for u in (r.get('istochniki') or '').split('|') if u.strip().startswith('http')]
    nomer = telefon(r.get('nomer'))
    if nomer:
        c.execute("""insert or replace into nomer_vid values (?,?,?,?,?,?,?,?,?,?,?)""",
                  (inn, nomer, (r.get('vid_nomera') or '').strip(),
                   (r.get('chem_dokazan') or '').strip(), (r.get('prinadlezhnost') or '').strip(),
                   chel, dolzh, (r.get('citata') or '')[:600],
                   int(r.get('kanalov') or 0), int(r.get('istochnikov') or 0),
                   time.strftime('%Y-%m-%d %H:%M:%S')))
        itog['вид номера записан'] += 1
        if not ssylki:
            itog['без ссылки — не берём'] += 1
        for u in ssylki[:4]:
            if (inn, 'telefon', nomer) in est:
                break
            c.execute("""insert into contact_source(inn, vid, znachenie, person, dolzhnost,
                             istochnik, source_url, domen, pervoistochnik, data_nablyudeniya,
                             quote, kto)
                         values (?,?,?,?,?,?,?,?,?,?,?,?)""",
                      (inn, 'telefon', nomer, chel, dolzh,
                       'единая база 3-й сессии: ' + (r.get('chem_dokazan') or ''), u,
                       re.sub(r'^https?://(www\.)?([^/]+).*', r'\2', u), 0,
                       time.strftime('%Y-%m-%d'), (r.get('citata') or '')[:300], '3-я сессия'))
            itog['телефон принят'] += 1
        est.add((inn, 'telefon', nomer))
    pochta = (r.get('pochta') or '').strip().lower()
    if '@' in pochta and (inn, 'email', pochta) not in est:
        for u in ssylki[:2]:
            c.execute("""insert into contact_source(inn, vid, znachenie, person, dolzhnost,
                             istochnik, source_url, domen, pervoistochnik, data_nablyudeniya,
                             quote, kto)
                         values (?,?,?,?,?,?,?,?,?,?,?,?)""",
                      (inn, 'email', pochta, chel, dolzh,
                       'единая база 3-й сессии: ' + (r.get('vid_pochty') or ''), u,
                       re.sub(r'^https?://(www\.)?([^/]+).*', r'\2', u), 0,
                       time.strftime('%Y-%m-%d'), (r.get('citata') or '')[:300], '3-я сессия'))
            itog['почта принята'] += 1
        est.add((inn, 'email', pochta))

for k, v in itog.items():
    print('  %-28s %d' % (k, v))
if not PISAT:
    print()
    print('сухой прогон, база не тронута; писать — с ключом --pisat')
    p.rollback()
    p.close()
    raise SystemExit
c.execute('insert into zhurnal_vlivaniya values (?,?,?,?,?,?)',
          (time.strftime('%Y-%m-%d %H:%M:%S'), 'ЕДИНАЯ БАЗА 3-й СЕССИИ: контакты со ссылкой',
           itog['строк в файле'], itog['телефон принят'] + itog['почта принята'],
           itog['вне выдачи'], 'вид номера и степень доказанности хранятся раздельно'))
p.commit()
q = lambda s: c.execute(s).fetchone()[0]
print()
print('contact_source: было %d, стало %d' % (bylo_cs, q('select count(*) from contact_source')))
print('вид номера записан для %d пар (ИНН, номер)' % q('select count(*) from nomer_vid'))
for v, n in c.execute("""select vid_nomera, count(*) from nomer_vid group by 1
                          order by 2 desc limit 6"""):
    print('   %-34s %d' % ((v or '(пусто)')[:34], n))
print('из них «номер и фамилия в одной цитате»: %d'
      % q("select count(*) from nomer_vid where chem_dokazan like '%одной цитате%'"))
p.close()

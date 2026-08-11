# -*- coding: utf-8 -*-
"""Принимает сбор 2-й сессии с checko: ОКВЭД, выручку и контакты — со ссылкой на страницу.

Владелец увидел в панели, что у одного предприятия ОКВЭД подписан «checko (2-я сессия),
страница деятельности», а у остальных — «карточки обогащения», и спросил: данные от checko
есть или почему ОКВЭД не подписан. Пошёл смотреть в файлы, и оказалось — данные ЕСТЬ, лежат
на дропе, а принято из них не всё.

Что нашлось при разборе:

    PARK-OKVED-2S.jsonl ... 876 строк, 873 с кодами; в моей выдаче 726;
                            ОКВЭД, которого у меня НЕТ, — всего 2
    PARK-CHECKO-2S.jsonl .. 2961 строк; с ОКВЭД 924, из них НОВЫХ для выдачи 110;
                            телефоны у 2418, почты у 2320, сайты у 1681

**Главная причина, по которой выручка checko прошла мимо: она записана СЛОВАМИ.**

    vyruchka='15,7 млн'   vyruchka='5,9 млрд'   vyruchka='292,5 млн'

Прежний приём брал `cast(vyruchka as real)`, а SQLite превращает «5,9 млрд» в 5.0 — то есть
пять рублей вместо пяти миллиардов. Числа такого вида надо разбирать, а не приводить типом.
Здесь они переводятся в рубли явно, и в источник пишется год и адрес карточки.

Ничего не перезаписываю поверх более надёжного: ОКВЭД и выручка ставятся только там, где их
НЕТ. Контакты идут через `contact_source` со ссылкой на страницу контактов checko — по
правилу владельца контакт без ссылки доказанным не считается.
"""
import json, os, re, sqlite3, sys, time

D = os.path.dirname(os.path.abspath(__file__))
PISAT = '--pisat' in sys.argv
MNOZH = {'тыс': 1e3, 'млн': 1e6, 'млрд': 1e9, 'трлн': 1e12}


def v_rubli(s):
    """«5,9 млрд» -> 5900000000.0; «0» -> 0.0; мусор -> None."""
    t = str(s or '').strip().lower().replace('\xa0', ' ')
    if not t:
        return None
    m = re.match(r'^(-?[\d\s]+(?:[.,]\d+)?)\s*(тыс|млн|млрд|трлн)?', t)
    if not m:
        return None
    try:
        chislo = float(m.group(1).replace(' ', '').replace(',', '.'))
    except ValueError:
        return None
    return chislo * MNOZH.get(m.group(2), 1)


def telefon_chistyy(t):
    c = re.sub(r'\D', '', str(t or ''))
    if len(c) == 11 and c[0] in '78':
        return '7' + c[1:]
    return c if len(c) == 10 else ''


p = sqlite3.connect(os.path.join(D, 'park.db'), timeout=180)
c = p.cursor()
vydacha = {r[0] for r in c.execute("""select distinct inn from fakt where v_parke=1
             and coalesce(v_obzvone,0)=0 and coalesce(posrednik,0)=0""")}
est_okved = {r[0] for r in c.execute("select inn from finansy where coalesce(okved,'')<>''")}
est_vyr = {r[0] for r in c.execute("select inn from finansy where cast(vyruchka as real)>0")}
est_inn = {r[0] for r in c.execute("select inn from finansy")}
est_tel = {r[0] for r in c.execute("select distinct inn from kontakt where vid='telefon'")}
est_pochta = {r[0] for r in c.execute("select distinct inn from kontakt where vid='email'")}

itog = {'ОКВЭД добавлен': 0, 'выручка добавлена': 0, 'телефон добавлен': 0,
        'почта добавлена': 0, 'строк вне выдачи': 0}
novye_finansy = []


def zapisat_finansy(inn, okved, okved_vse, okved_src, vyr, vyr_src):
    if inn not in est_inn:
        c.execute('insert into finansy(inn, ts) values (?,?)',
                  (inn, time.strftime('%Y-%m-%d %H:%M:%S')))
        est_inn.add(inn)
    if okved and inn not in est_okved:
        c.execute('update finansy set okved=?, okved_vse=?, okved_otkuda=? where inn=?',
                  (okved, okved_vse, okved_src, inn))
        est_okved.add(inn)
        itog['ОКВЭД добавлен'] += 1
    if vyr and vyr > 0 and inn not in est_vyr:
        c.execute('update finansy set vyruchka=?, vyruchka_otkuda=? where inn=?',
                  (vyr, vyr_src, inn))
        est_vyr.add(inn)
        itog['выручка добавлена'] += 1


# 1) файл «Виды деятельности»: коды с именами и ссылка на страницу деятельности
for ln in open(os.path.join(D, 'PARK-OKVED-2S.jsonl'), encoding='utf-8', errors='replace'):
    if not ln.strip():
        continue
    r = json.loads(ln)
    inn = (r.get('inn') or '').strip()
    if inn not in vydacha:
        itog['строк вне выдачи'] += 1
        continue
    kody = r.get('okved_kody') or []
    if not kody:
        continue
    imena = r.get('okved_s_imenami') or []
    zapisat_finansy(inn, kody[0], ' | '.join(imena) or ' | '.join(kody),
                    'checko (2-я сессия), страница деятельности: ' + (r.get('ssylka') or ''),
                    None, None)

# 2) карточка компании: ОКВЭД, выручка словами, телефоны и почты
for ln in open(os.path.join(D, 'PARK-CHECKO-2S.jsonl'), encoding='utf-8', errors='replace'):
    if not ln.strip():
        continue
    r = json.loads(ln)
    inn = (r.get('inn') or '').strip()
    if inn not in vydacha:
        itog['строк вне выдачи'] += 1
        continue
    kart = (r.get('ssylka_kartochka') or r.get('kartochka') or '').strip()
    vyr = v_rubli(r.get('vyruchka'))
    zapisat_finansy(inn, (r.get('okved') or '').strip(), (r.get('okved_all') or '').strip(),
                    'checko (2-я сессия), карточка: ' + kart,
                    vyr, 'checko (2-я сессия), %s: %s' % (r.get('vyruchka_god') or '', kart))
    ssylka_k = (r.get('ssylka_kontakty') or kart).strip()
    if not ssylka_k:
        continue
    if inn not in est_tel:
        for t in (r.get('telefony') or [])[:3]:
            nomer = telefon_chistyy(t)
            if not nomer:
                continue
            c.execute("""insert into contact_source(inn, vid, znachenie, istochnik, source_url,
                             domen, pervoistochnik, data_nablyudeniya, kto)
                         values (?,?,?,?,?,?,?,?,?)""",
                      (inn, 'telefon', nomer, 'checko.ru, раздел «Контакты»', ssylka_k,
                       'checko.ru', 0, time.strftime('%Y-%m-%d'), '2-я сессия, checko'))
            itog['телефон добавлен'] += 1
        est_tel.add(inn)
    if inn not in est_pochta:
        for e in (r.get('pochty') or [])[:3]:
            e = str(e).strip().lower()
            if '@' not in e:
                continue
            c.execute("""insert into contact_source(inn, vid, znachenie, istochnik, source_url,
                             domen, pervoistochnik, data_nablyudeniya, kto)
                         values (?,?,?,?,?,?,?,?,?)""",
                      (inn, 'email', e, 'checko.ru, раздел «Контакты»', ssylka_k,
                       'checko.ru', 0, time.strftime('%Y-%m-%d'), '2-я сессия, checko'))
            itog['почта добавлена'] += 1
        est_pochta.add(inn)

for k, v in itog.items():
    print('  %-24s %d' % (k, v))
if not PISAT:
    print()
    print('сухой прогон, база не тронута; писать — с ключом --pisat')
    p.rollback()
    p.close()
    raise SystemExit
c.execute('insert into zhurnal_vlivaniya values (?,?,?,?,?,?)',
          (time.strftime('%Y-%m-%d %H:%M:%S'), 'CHECKO (2-я сессия): ОКВЭД, выручка, контакты',
           itog['строк вне выдачи'] + sum(v for k, v in itog.items() if k != 'строк вне выдачи'),
           itog['ОКВЭД добавлен'] + itog['выручка добавлена'], itog['строк вне выдачи'],
           'выручка разбиралась из «5,9 млрд»; ничего не перезаписывалось поверх готового'))
p.commit()
q = lambda s: c.execute(s).fetchone()[0]
print()
print('ПОСЛЕ: с ОКВЭД %d | с выручкой %d | строк в contact_source %d'
      % (q("select count(*) from finansy where coalesce(okved,'')<>''"),
         q("select count(*) from finansy where cast(vyruchka as real)>0"),
         q("select count(*) from contact_source")))
p.close()

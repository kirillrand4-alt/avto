# -*- coding: utf-8 -*-
"""Принимает готовые карточки предприятий 2-й сессии: ОКВЭД, выручка, сайт, руководитель.

Владелец спросил, почему ОКВЭД в панели подписан «карточки обогащения», а не checko, — и
указал на выдачу 2-й сессии. Она выложила `PARK-VYDACHA-PREDPRIYATIYA-2S.csv`: 2 978
карточек, где на каждое предприятие есть ВСЕ коды ОКВЭД (до 33 штук), выручка с годом, сайт,
адрес, руководитель, статус ЕГРЮЛ — и **две ссылки-доказательства**: карточка checko и
страница «Виды деятельности».

Почему это не было принято раньше и почему берётся сейчас:

  * прошлый приём брал ОКВЭД из своих карточек обогащения, а checko шёл только на выручку;
  * выручка в её сыром файле записана словами («5,9 млрд»), и `cast(... as real)` давал
    из этого 5 — это разобрано в `park_1s_prinyat_checko.py`. В ЭТОЙ выдаче выручка уже
    числом, ошибиться негде;
  * у неё ОКВЭД идёт со ссылкой на страницу деятельности, то есть доказан по нашему правилу.

Ничего не перезаписываю поверх непустого: ОКВЭД и выручка ставятся там, где их нет. Статус
ЕГРЮЛ и сайт обновляются всегда — они не «мнение», а состояние реестра, и свежее вернее.
Ликвидированные не удаляются: владелец решает сам, звонить или нет, а панель их метит.

Запуск: python3 park_1s_prinyat_vydachu_2s.py [--pisat]
"""
import csv, os, re, sqlite3, sys, time

D = os.path.dirname(os.path.abspath(__file__))
PISAT = '--pisat' in sys.argv
FAYL = os.path.join(D, 'PARK-VYDACHA-PREDPRIYATIYA-2S.csv')


def chislo(s):
    t = str(s or '').strip().replace('\xa0', ' ').replace(' ', '').replace(',', '.')
    try:
        return float(t) if t else None
    except ValueError:
        return None


p = sqlite3.connect(os.path.join(D, 'park.db'), timeout=180)
c = p.cursor()
vydacha = {r[0] for r in c.execute("""select distinct inn from fakt where v_parke=1
             and coalesce(v_obzvone,0)=0 and coalesce(posrednik,0)=0""")}
est_okved = {r[0] for r in c.execute("select inn from finansy where coalesce(okved,'')<>''")}
est_vyr = {r[0] for r in c.execute("select inn from finansy where cast(vyruchka as real)>0")}
est_inn = {r[0] for r in c.execute("select inn from finansy")}

itog = {'ОКВЭД добавлен': 0, 'ОКВЭД: полный список дописан': 0, 'выручка добавлена': 0,
        'строк вне выдачи': 0, 'строк в файле': 0}
for r in csv.DictReader(open(FAYL, encoding='utf-8-sig'), delimiter=';'):
    itog['строк в файле'] += 1
    inn = (r.get('inn') or '').strip()
    if not re.fullmatch(r'\d{10}|\d{12}', inn) or inn not in vydacha:
        itog['строк вне выдачи'] += 1
        continue
    kody = (r.get('okved_kody') or '').split()
    osn = (r.get('okved_osnovnoy') or '').strip() or (kody[0] if kody else '')
    vyr = chislo(r.get('vyruchka'))
    ssylka_ok = (r.get('ssylka_okved') or '').strip()
    ssylka_ch = (r.get('ssylka_checko') or '').strip()
    if inn not in est_inn:
        c.execute('insert into finansy(inn, ts) values (?,?)',
                  (inn, time.strftime('%Y-%m-%d %H:%M:%S')))
        est_inn.add(inn)
    if osn and inn not in est_okved:
        c.execute("""update finansy set okved=?, okved_vse=?, okved_otkuda=? where inn=?""",
                  (osn, ' | '.join(kody),
                   'checko (2-я сессия), виды деятельности: ' + (ssylka_ok or ssylka_ch), inn))
        est_okved.add(inn)
        itog['ОКВЭД добавлен'] += 1
    elif kody and inn in est_okved:
        # ОКВЭД уже есть, но полного списка могло не быть: у неё до 33 кодов на предприятие,
        # и профиль по одному коду не читается
        c.execute("""update finansy set okved_vse=? where inn=? and coalesce(okved_vse,'')=''""",
                  (' | '.join(kody), inn))
        itog['ОКВЭД: полный список дописан'] += c.rowcount
    if vyr and vyr > 0 and inn not in est_vyr:
        c.execute('update finansy set vyruchka=?, vyruchka_otkuda=? where inn=?',
                  (vyr, 'checko (2-я сессия), %s: %s' % (r.get('vyruchka_god') or '', ssylka_ch), inn))
        est_vyr.add(inn)
        itog['выручка добавлена'] += 1

for k, v in itog.items():
    print('  %-32s %d' % (k, v))
if not PISAT:
    print()
    print('сухой прогон, база не тронута; писать — с ключом --pisat')
    p.rollback()
    p.close()
    raise SystemExit
c.execute('insert into zhurnal_vlivaniya values (?,?,?,?,?,?)',
          (time.strftime('%Y-%m-%d %H:%M:%S'), 'ВЫДАЧА 2-й СЕССИИ: карточки предприятий',
           itog['строк в файле'], itog['ОКВЭД добавлен'] + itog['выручка добавлена'],
           itog['строк вне выдачи'], 'ОКВЭД со ссылкой на страницу деятельности checko'))
p.commit()
q = lambda s: c.execute(s).fetchone()[0]
print()
print('ПОСЛЕ: с ОКВЭД %d | с полным списком кодов %d | с выручкой %d'
      % (q("select count(*) from finansy where coalesce(okved,'')<>''"),
         q("select count(*) from finansy where coalesce(okved_vse,'')<>''"),
         q("select count(*) from finansy where cast(vyruchka as real)>0")))
p.close()

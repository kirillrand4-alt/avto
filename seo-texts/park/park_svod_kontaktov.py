# -*- coding: utf-8 -*-
"""Пересборка свода контактов (kontakt) из наблюдений (contact_source).

Нужна после КАЖДОГО вливания контактов, иначе новые телефоны и почты не попадут ни в
выдачу, ни в список звонка: выдача читает свод, а не наблюдения. Здесь же считаются
признаки, на которых стоит порядок обзвона:
  ssylok            сколько РАЗНЫХ страниц подтверждают контакт;
  imen              сколько разных людей названо при этом контакте;
  innov             у скольких ИНН встречается тот же номер — признак 3-й сессии,
                    больше одного почти всегда приёмная или подрядчик;
  lichnyy           имя одно, первоисточник есть, номер не гуляет по фирмам;
  mobilnyy          формат номера (это ФОРМАТ, а не доказательство владения);
  rol / rang        роль и круг по должности, канон 3-й сессии.
"""
import sqlite3, os, re

D = os.path.dirname(os.path.abspath(__file__))

# ---------- пересборка свода контактов и ролей -------------------------------
# kontakt строится из наблюдений целиком, иначе новые телефоны в выдачу не попадут.
p = sqlite3.connect(os.path.join(D, 'park.db'))
cur = p.cursor()
import time
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
cur.execute("update kontakt set lichnyy = case when imen=1 and ssylok_pervoistochnik>=1 "
            "and innov=1 then 1 else 0 end")
cur.execute("update kontakt set mobilnyy = case when vid='telefon' and "
            "substr(znachenie,1,1)='9' then 1 else 0 end")

# Список расширен по ЗАМЕРУ: смотрел, какие должности сидят в круге 5 («роль не
# определена») у контактов со ссылкой. Там оказались технические роли, которых просто не
# было в словаре: главный конструктор (82), «контактное лицо по вопросам технического
# задания» (54), начальник участка (100), «по техническим вопросам» (26), начальник
# котельной (22), а также собственная номенклатура штатного конвейера — «техконтакт»,
# «нач.КС». Мусорные строки («Развернуть», «Ответственный сотрудник») в круге 5 оставлены.
ROL = [
    (r'(?i)машинист\s+компрессор|аппаратчик\s+воздухораздел|оператор\s+компрессорн|'
     r'аппаратчик\s+кислородн|моторист\s+.*азотн', 'рабочий-эксплуатант', 1),
    (r'(?i)нач\.?\s*кс\b|начальник\s+компрессорн|начальник\s+котельн|'
     r'начальник\s+энерго', 'начальник компрессорного/энергоцеха', 1),
    (r'(?i)главн\w+\s+конструктор', 'главный конструктор', 2),
    (r'(?i)техконтакт|по\s+техническ\w+\s+вопрос|технического\s+задания|'
     r'по\s+вопросам\s+техническ', 'технический контакт', 2),
    (r'(?i)начальник\s+участка|начальник\s+смены|электромонтер|электромеханик',
     'инженер/механик', 2),
    (r'(?i)главн\w+\s+(инженер|механик|энергетик)|техническ\w+\s+директор|'
     r'директор\s+по\s+техн', 'главный инженер/механик/энергетик', 1),
    (r'(?i)начальник\s+(компрессорн|энергоцех|энергетическ)', 'начальник компрессорного/энергоцеха', 1),
    (r'(?i)начальник\s+(цеха|производств)|главн\w+\s+технолог|начальник\s+(асу|кипиа|кип)',
     'начальник цеха/производства', 2),
    (r'(?i)инженер|механик|энергетик|мастер|техник|слесар', 'инженер/механик', 2),
    (r'(?i)снабжен|закупк|мто|тендер|коммерческ', 'снабжение/закупки', 3),
    (r'(?i)директор|руководител|генеральн|президент', 'руководство', 4),
]
n = 0
for kid, dolzh in cur.execute("select id, coalesce(dolzhnost,'') from kontakt").fetchall():
    rol, krug = next(((r, k) for sh, r, k in ROL if re.search(sh, dolzh)),
                     ('не определена', 5) if dolzh else ('должность не названа', 5))
    cur.execute('update kontakt set rol=?, rang=? where id=?', (rol, krug, kid))
    n += 1
p.commit()
q = lambda s: cur.execute(s).fetchone()[0]
print('свод пересобран: %d контактов, роль проставлена %d' % (q('select count(*) from kontakt'), n))
print('  ИНН с телефоном и ссылкой:', q("select count(distinct inn) from kontakt where vid='telefon' and ssylok>0"))
print('  ИНН с почтой и ссылкой:  ', q("select count(distinct inn) from kontakt where vid='email' and ssylok>0"))
print('  круг 1:', q('select count(distinct inn) from kontakt where rang=1'))
p.close()

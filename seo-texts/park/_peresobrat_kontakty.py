# -*- coding: utf-8 -*-
"""Пересобирает свод kontakt из наблюдений contact_source — тем же запросом, что park_build.

Нужно после приёма контактов checko: наблюдения легли в contact_source, но панель читает
свод `kontakt`, и без пересборки новые телефоны до продавца не доходят.
"""
import sqlite3, time
p = sqlite3.connect('park.db', timeout=180)
cur = p.cursor()
bylo = cur.execute('select count(*) from kontakt').fetchone()[0]
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
p.commit()
stalo = cur.execute('select count(*) from kontakt').fetchone()[0]
print('контактов было %d, стало %d (прибыло %d)' % (bylo, stalo, stalo - bylo))
print('  со ссылкой ....... %d' % cur.execute('select count(*) from kontakt where ssylok>0').fetchone()[0])
p.close()

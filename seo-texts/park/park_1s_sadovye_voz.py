# -*- coding: utf-8 -*-
"""Садовые и ранцевые «воздуходувки» — вон из парка. Тот же заслон, что я ставил чужому потоку.

Первая ссылка случайного жребия: «Поставка воздуходувки», заказчик СПОРТИВНАЯ ШКОЛА ГОРОДА
ЯЛУТОРОВСКА, цена 115 190 ₽ — это садовый инструмент, а не промышленная газодувка. Заслон
на ранцевые и садовые я применял к потоку 3-й сессии, а СВОЮ базу не проверил.

Отсекаю только по ПРЯМЫМ признакам в тексте (ранцевая, лесопожарная, садовая, бензиновая,
аккумуляторная, уборка листвы). Придуманную было проверку «заказчик — школа или парк»
не применяю: она сработала на «ОмскВодоканал» и «ОФ Коксовая», то есть ловит подстроки, а
не смысл. Плохой заслон хуже отсутствующего — про эти строки честно скажу «не проверено».

Факты не удаляются: ставим `vid_fakta='НЕТ'` и `v_parke=0`, причина — в `pochemu`.
Возврат возможен, как и по остальным исключениям.
"""
import os, re, sqlite3

D = os.path.dirname(os.path.abspath(__file__))
p = sqlite3.connect(os.path.join(D, 'park.db'))
c = p.cursor()
SADOVAYA = re.compile(r'ранцев|лесопожарн|садов|бензинов|аккумуляторн|'
                      r'воздуходувк\w*\s+ручн|уборк\w+\s+листв|метл|пылесос', re.I)
PRICHINA = ('НЕ НАША МАШИНА: садовая или ранцевая воздуходувка (прямой признак в тексте), '
            'а не промышленная газодувка — заслон 1-й сессии по следам жребия')
celi = [(fid, inn) for fid, inn, txt in c.execute(
            "select id, inn, coalesce(chto_naydeno,'') from fakt"
            " where v_parke=1 and tip='воздуходувка'").fetchall()
        if SADOVAYA.search(txt)]
for fid, _ in celi:
    c.execute("update fakt set v_parke=0, vid_fakta='НЕТ', pochemu = "
              "case when coalesce(pochemu,'')='' then ? else pochemu || ' | ' || ? end "
              "where id=?", (PRICHINA, PRICHINA, fid))
p.commit()
print('исключено фактов: %d на %d предприятиях' % (len(celi), len({i for _, i in celi})))
q = lambda s: c.execute(s).fetchone()[0]
print('в парке фактов: %d | предприятий: %d' % (
    q('select count(*) from fakt where v_parke=1'),
    q('select count(distinct inn) from fakt where v_parke=1')))
p.close()

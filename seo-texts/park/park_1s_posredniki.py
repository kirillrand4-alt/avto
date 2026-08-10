# -*- coding: utf-8 -*-
"""Убираю из выдачи уполномоченные органы: машина встанет не у них.

Как нашлось. Разбирал снимки доказательств по видам адреса и увидел разницу: на карточке
223-ФЗ ИНН заказчика виден в 99 % случаев (1 552 из 1 575), а на карточке 44-ФЗ — в 78 %
(1 130 из 1 448). Пошёл смотреть, кто эти 44-ФЗ без ИНН, и в первых же четырёх пробах:

    2434000818  АДМИНИСТРАЦИЯ СЕВЕРО-ЕНИСЕЙСКОГО ОКРУГА
    3015009178  АДМИНИСТРАЦИЯ ГОРОДА АСТРАХАНЬ
    1001338940  ГКУ РК ЦЕНТР ОРГАНИЗАЦИИ ЗАКУПОК РЕСПУБЛИКИ КАРЕЛИЯ

Это те, кто РАЗМЕЩАЕТ закупку, а не те, у кого стоит машина: компрессор поедет в школу или
котельную, а продавец по такой строке позвонит в администрацию. Заслон `posrednik()` у меня
появился только в новом приёмнике потоков — всё, что влилось раньше, прошло без него.

Разделитель взят не на глаз: **надзорная запись ЭПБ выдаётся ЭКСПЛУАТАНТУ**. Если у ИНН есть
хоть одно заключение на monitor-pb, машина действительно его, и трогать нельзя. Проверил всех
73: заключений нет НИ У ОДНОГО, все держатся только на закупках.

Как убираю: колонкой `posrednik=1`, как и с обзвоном. Факты, ссылки и контакты остаются на
месте — если у такого ИНН однажды появится ЭПБ, он вернётся в выдачу сам.
"""
import os, re, sqlite3, time

D = os.path.dirname(os.path.abspath(__file__))
p = sqlite3.connect(os.path.join(D, 'park.db'))
c = p.cursor()
RX = re.compile(
    r'^администраци|^адм\b|центр\w*\s+организации\s+закупок|центр\w*\s+закупок|'
    r'комитет\w*\s+по\s+(регулированию|закупк)|'
    r'(управлени|департамент)\w*\s+(по\s+)?(закупк|государственн\w*\s+заказ)|'
    r'министерств\w*\s+по\s+регулированию|агентств\w*\s+(государственн|по\s+госзаказ)|'
    r'дирекци\w*\s+(по\s+)?закупок', re.I)

if 'posrednik' not in [r[1] for r in c.execute('pragma table_info(fakt)')]:
    c.execute('alter table fakt add column posrednik integer default 0')
c.execute('update fakt set posrednik=0')

rows = c.execute("""select f.inn, max(coalesce(f.nazvanie,'')) from fakt f
                    where f.v_parke=1 group by f.inn""").fetchall()
kandidaty = [(i, n) for i, n in rows if RX.search(n.lower())]
pometit, ostavit = [], []
for inn, imya in kandidaty:
    epb = c.execute("""select count(*) from fakt f join fakt_ssylka s on s.fakt_id=f.id
                       where f.inn=? and s.url like '%monitor-pb.ru/conclusion/%'""",
                    (inn,)).fetchone()[0]
    (ostavit if epb else pometit).append((inn, imya, epb))

tronuto = 0
for i in range(0, len(pometit), 400):
    pack = [x[0] for x in pometit[i:i + 400]]
    c.execute('update fakt set posrednik=1 where v_parke=1 and inn in (%s)'
              % ','.join('?' * len(pack)), pack)
    tronuto += c.rowcount
c.execute('insert into zhurnal_vlivaniya values (?,?,?,?,?,?)',
          (time.strftime('%Y-%m-%d %H:%M:%S'), 'ПОСРЕДНИКИ: уполномоченные органы вне выдачи',
           len(kandidaty), len(pometit), len(ostavit),
           'оставлены те, у кого есть надзорная запись ЭПБ (она выдаётся эксплуатанту)'))
p.commit()
q = lambda s: c.execute(s).fetchone()[0]
print('кандидатов по названию ......... %d' % len(kandidaty))
print('  помечено посредниками ........ %d предприятий, %d фактов' % (len(pometit), tronuto))
print('  оставлено (есть ЭПБ) ......... %d' % len(ostavit))
print('выдача была %d -> стала %d предприятий'
      % (q('select count(distinct inn) from fakt where v_parke=1 and coalesce(v_obzvone,0)=0'),
         q('''select count(distinct inn) from fakt where v_parke=1 and coalesce(v_obzvone,0)=0
              and coalesce(posrednik,0)=0''')))
for r in c.execute("""select inn, max(nazvanie), count(*) from fakt where posrednik=1
                      group by inn order by count(*) desc limit 6"""):
    print('    %s %-52s фактов %d' % (r[0], r[1][:52], r[2]))
p.close()

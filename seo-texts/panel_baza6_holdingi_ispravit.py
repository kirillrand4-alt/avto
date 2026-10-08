# -*- coding: utf-8 -*-
"""Холдинги Базы 6: только честные связи (владелец 08.10: «откуда ты взял эти компании?»).

В MLK Group стояли «Молоко Дона» и «Милково»: своего сайта у них нет, агент файла 6 приписал их
к холдингу (цитата-доказательство о них не говорит, а «Милково» – это бренд MLK, а не завод в
Вязниках) и выдал им номер офиса холдинга; группа по этому номеру подтверждала агента сама собой.
Новое правило (meyer_baza6_v_json.py): подтверждённая связь – общий номер на сайтах самих
компаний; мнение агента связывает только компании, которые обе в панели, с пометкой «не
подтверждено»; компания вне панели – только при подтверждённой связи. Назначения не меняются:
группы только сужаются, все члены каждой новой группы уже у одного продавца (проверяется)."""
import io, json, os, re, sqlite3, sys, time
KOREN = r'C:\centro2'
KAT = os.path.join(KOREN, 'data', 'meyer_baza1.db')
SALES = os.path.join(KOREN, 'data', 'centro_sales_meyer1.db')
D = json.load(io.open(r'C:\seostat\drop\drop-storage\meyer-baza6-holdingi.json', encoding='utf-8'))
B = os.path.join(KOREN, '_bekap', time.strftime('baza6-holdingi-%Y%m%d-%H%M%S'))
os.makedirs(B, exist_ok=True)
k = sqlite3.connect(KAT)
dst = sqlite3.connect(os.path.join(B, 'meyer_baza1.db'))
k.backup(dst)
dst.close()
s = sqlite3.connect('file:%s?mode=ro' % SALES, uri=True)
naz = dict(s.execute('select inn, username from company_assignment'))
v_paneli = {r[0] for r in k.execute('select inn from company')}
plohih = 0
for gid, g in D['gruppy'].items():
    u = {naz.get(ch['inn']) for ch in g['chleny'] if ch['inn'] in v_paneli}
    if len(u) > 1:
        plohih += 1
        print('ПЛОХО: группа %s у разных продавцов %s' % (gid, u))
staroe = k.execute("select count(*), count(distinct gruppa) from holding_chlen where gruppa not like 'g4-%' and gruppa not like 'g2-%'").fetchone()
k.execute("delete from holding_chlen where gruppa not like 'g4-%' and gruppa not like 'g2-%'")
for gid, g in D['gruppy'].items():
    for ch in g['chleny']:
        k.execute('insert into holding_chlen values (?,?,?,?,?,?,?,?)', (gid, ch['inn'], ch['nazvanie'], ch['region'],
                  ch['segment'], ch['vyruchka_rub'], int(ch['v_vybore']), ch['svyaz']))
n = 0
for c in D['kompanii']:
    r = k.execute("update company set holding=?, holding_gruppa=? where inn=? and bazy like '%База 6%' "
                  "and (coalesce(holding,'')<>? or coalesce(holding_gruppa,'')<>?)",
                  (c['holding'], c['holding_gruppa'], c['inn'], c['holding'], c['holding_gruppa']))
    n += r.rowcount
k.commit()
novoe = k.execute("select count(*), count(distinct gruppa) from holding_chlen where gruppa not like 'g4-%' and gruppa not like 'g2-%'").fetchone()
print('состав холдингов: было %d строк в %d группах, стало %d в %d; карточек обновлено %d' % (staroe + novoe + (n,)))
ostalis = [r[0] for r in k.execute("select nazvanie from holding_chlen where inn in ('6124003936','3303010571')")]
print('«Молоко Дона» и «Милково» в составе: %s' % (ostalis or 'нет'))
print('MLK:', [tuple(r) for r in k.execute("select nazvanie, svyaz from holding_chlen where gruppa='g1608010251'")])
print('ПЛОХИХ: %d' % plohih)

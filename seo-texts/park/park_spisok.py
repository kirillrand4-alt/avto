# -*- coding: utf-8 -*-
"""СПИСОК ДЛЯ ЗВОНКА — одна строка = один звонок, и в ней ДВЕ ссылки: на человека и
на машину. Без обеих строка в список не идёт: продавцу нечем ответить на вопрос
«откуда у вас мои данные».

Пишется заново после того, как 3-я сессия нашла дефект в прежней выгрузке: колонка
`mobilnyy` там показывала 0 у номеров, которые в базе помечены как мобильные (признак
жил в соседней колонке с другим правилом). Здесь каждая колонка берётся из `kontakt`
явно и названа по смыслу — «что это значит» написано в шапке PARK-SPISOK-KOLONKI.md.

Порядок — правило владельца: сначала те, у кого машина дороже, и контакт с лучшей
технической ролью. То есть ключ сортировки: ранг машины вниз, круг роли вверх.

Признак `nomer_u_neskolkih` взят у 3-й сессии: один и тот же номер у нескольких ИНН —
это приёмная/подрядчик, а не личный телефон человека.
"""
import sqlite3, csv, os, re

D = os.path.dirname(os.path.abspath(__file__))
p = sqlite3.connect('file:%s?mode=ro' % os.path.join(D, 'park.db'), uri=True)
OUT = os.path.join(D, 'PARK-SPISOK-DLYA-ZVONKA-1S.csv')

POLYA = ['inn', 'predpriyatie', 'chelovek', 'dolzhnost', 'rol', 'krug', 'nomer',
         'vid_nomera', 'lichnyy_nomer_cheloveka', 'nomer_u_neskolkih_predpriyatiy',
         'prinadlezhnost', 'mashina', 'model', 'rang_mashiny', 'chem_rang',
         'sila_fakta', 'os', 'ssylok_na_kontakt', 'ssylka_chelovek', 'ssylka_mashina']

# --- имя предприятия: справочник обзвона, иначе самое частое название в фактах -------
IMYA = """coalesce(
    (select nullif(s.name_obzvon,'') from spravochnik s where s.inn=k.inn),
    (select nullif(e.imya,'') from egrul e where e.inn=k.inn),
    (select nullif(i.imya,'') from imya_eis i where i.inn=k.inn),
    (select x.nazvanie from fakt x where x.inn=k.inn and x.nazvanie<>''
       group by x.nazvanie order by count(*) desc, length(x.nazvanie) desc limit 1), '')"""

SQL = """
select k.inn, %s, k.person, k.dolzhnost, k.rol, k.rang, k.znachenie,
       k.mobilnyy, k.lichnyy, k.innov, k.ssylok
  from kontakt k
 where k.vid='telefon' and k.ssylok>0 and coalesce(k.person,'')<>''
   and exists (select 1 from fakt f where f.inn=k.inn and f.v_parke=1)
   -- ликвидированным и банкротам не звонят: 40 таких нашлось по ЕГРЮЛ
   and coalesce((select e.status from egrul e where e.inn=k.inn),'') not in
       ('LIQUIDATED','BANKRUPT','LIQUIDATING')
""" % IMYA

# ссылка НА ЧЕЛОВЕКА: та, где номер реально виден рядом с человеком
SSYL_CHEL = """select source_url from contact_source
   where inn=? and znachenie=? and coalesce(source_url,'')<>''
   order by pervoistochnik desc, length(coalesce(quote,'')) desc limit 1"""
# ссылка НА МАШИНУ: самый сильный факт предприятия, у которого ссылка доказывает поштучно
SSYL_MASH = """select f.tip, f.model, f.rang_mashiny, f.chem_rang, f.sila, f.vid_fakta,
        (select s.url from fakt_ssylka s where s.fakt_id=f.id
          order by s.pervoistochnik desc, s.id limit 1)
   from fakt f where f.inn=? and f.v_parke=1
  order by f.rang_mashiny desc, f.sila asc limit 1"""


def vid_nomera(n):
    c = re.sub(r'\D', '', n or '')
    return 'мобильный' if re.match(r'^[78]?9\d{9}$', c) else 'городской'


prin = {}
for inn, nom, per, vidn, vyv in p.execute(
        'select inn,nomer,person,vid_nomera,vyvod from prinadlezhnost'):
    prin[(inn, re.sub(r'\D', '', nom or '')[-10:])] = vyv

stroki = []
bez_chel = bez_mash = 0
for (inn, imya, per, dolzh, rol, krug, nom, mob, lich, innov, ssylok) in p.execute(SQL):
    sc = p.execute(SSYL_CHEL, (inn, nom)).fetchone()
    sm = p.execute(SSYL_MASH, (inn,)).fetchone()
    if not sc or not sc[0]:
        bez_chel += 1
        continue
    if not sm or not sm[6]:
        bez_mash += 1
        continue
    tip, model, rang, chem, sila, vidf, url_m = sm
    stroki.append({
        'inn': inn, 'predpriyatie': imya, 'chelovek': per, 'dolzhnost': dolzh or '',
        'rol': rol or '', 'krug': krug if krug is not None else '',
        'nomer': nom, 'vid_nomera': vid_nomera(nom),
        'lichnyy_nomer_cheloveka': 1 if lich else 0,
        'nomer_u_neskolkih_predpriyatiy': innov if (innov or 0) > 1 else 0,
        'prinadlezhnost': prin.get((inn, re.sub(r'\D', '', nom)[-10:]),
                                   'принадлежность отдельно не проверялась'),
        'mashina': tip or '', 'model': model or '', 'rang_mashiny': rang if rang else '',
        'chem_rang': chem or '', 'sila_fakta': sila if sila is not None else '',
        'os': {'газ': 'расход газа', 'машина': 'парк машин', 'узел': 'парк машин',
               'расходник': 'парк машин'}.get(vidf, vidf or ''),
        'ssylok_na_kontakt': ssylok, 'ssylka_chelovek': sc[0], 'ssylka_mashina': url_m})

# правило владельца: машина дороже — выше; при равной машине выше лучшая тех. роль
stroki.sort(key=lambda r: (-(r['rang_mashiny'] or 0), r['krug'] if r['krug'] != '' else 9,
                           -r['lichnyy_nomer_cheloveka'], r['inn']))
with open(OUT, 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.DictWriter(f, fieldnames=POLYA, delimiter=';')
    w.writeheader()
    w.writerows(stroki)

inn = {r['inn'] for r in stroki}
print('строк: %d | предприятий: %d' % (len(stroki), len(inn)))
print('  отсеяно: без ссылки на человека %d | без доказанной машины %d' % (bez_chel, bez_mash))
print('  мобильных: %d | личных номеров человека: %d | номер у нескольких ИНН: %d'
      % (sum(1 for r in stroki if r['vid_nomera'] == 'мобильный'),
         sum(1 for r in stroki if r['lichnyy_nomer_cheloveka']),
         sum(1 for r in stroki if r['nomer_u_neskolkih_predpriyatiy'])))
import collections
print('  по кругу роли:', dict(collections.Counter(r['krug'] for r in stroki).most_common(6)))
print('  по оси:', dict(collections.Counter(r['os'] for r in stroki).most_common(6)))
p.close()

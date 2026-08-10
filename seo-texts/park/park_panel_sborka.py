# -*- coding: utf-8 -*-
"""Сборка компактной базы панели park_panel.db из полной park.db.

Зачем отдельная база: полная park.db весит 338 МБ (в ней тексты карточек и все ссылки),
панели из этого нужны две таблицы и 25 колонок — получается 11 МБ, которые не жалко
класть на сервер каждый тик.

Выручка и ОКВЭД сшиваются из ЧЕТЫРЁХ источников по приоритету, и у каждого числа
записывается, откуда оно взято (колонки `vyruchka_otkuda`, `okved_otkuda`) — иначе
в панели будет число без провенанса, а правило владельца требует доказуемости.

Порядок источников (сверху надёжнее):
    1. finansy       — реквизиты checko/dadata, снятые с провенансом
    2. spravochnik   — база обзвона (161 761 юрлицо, поле revenue_rub)
    3. egrul         — ОКВЭД из выписки, выручки там нет

Запуск: python3 park_panel_sborka.py   (перезаписывает park_panel.db целиком)
"""
import os, sqlite3

D = os.path.dirname(os.path.abspath(__file__))
ISH = os.path.join(D, 'park.db')
CEL = os.path.join(D, 'park_panel.db')

if os.path.exists(CEL):
    os.remove(CEL)
p = sqlite3.connect(CEL)
p.execute("attach database ? as ish", ('file:%s?mode=ro' % ISH,))
p.execute("""create table predpriyatie(
    inn text primary key, nazvanie text, region text, okved text, okved_otkuda text,
    okved_vse text,
    vyruchka real, vyruchka_otkuda text, ssch integer, status_egrul text, os text,
    dokazano text, rang_mashiny real, chem_rang text, sila integer, tipy text, marki text,
    faktov integer, ssylok integer, chelovek text, dolzhnost text, krug integer,
    telefon text, pochta text, ssylka_mashina text, ssylka_chelovek text)""")
# ФАКТЫ ЦЕЛИКОМ. Владелец, глядя на карточку КАМАЗа: «а где все факты про машины то?
# как понять что это не выдуманное». Он был прав: в карточке стоял список моделей
# («К345921 | ТВ801.4 | ВП50/8М…») и ОДНА ссылка — да ещё вакансия hh.ru. В базе при этом
# 13 фактов и 85 ссылок, у каждой модели свой тендер с адресом. Теперь панель возит
# факты и ВСЕ их ссылки, чтобы каждую строку можно было открыть и прочитать.
p.execute("""create table fakt(
    id integer primary key, inn text, tip text, marka text, model text, sostoyanie text,
    vid_fakta text, data_fakta text, sila integer, zavodskoy_nomer text,
    chto_naydeno text, chem_rang text, snimok text, snimok_inn integer, snimok_tip integer)""")
p.execute("""create table fakt_ssylka(
    fakt_id integer, url text, istochnik text, pervoistochnik integer)""")
p.execute("""insert into fakt select f.id, f.inn, f.tip, coalesce(f.marka,''),
    coalesce(f.model,''), coalesce(f.sostoyanie,''), coalesce(f.vid_fakta,''),
    coalesce(f.data_fakta,''), f.sila, coalesce(f.zavodskoy_nomer,''),
    substr(coalesce(f.chto_naydeno,''),1,400), substr(coalesce(f.chem_rang,''),1,200),
    -- СНИМОК ДОКАЗАТЕЛЬСТВА: имя файла в статике панели. Просьба владельца — чтобы было
    -- видно, что на том конце ссылки, не открывая её.
    (select d.snimok from ish.dokaz_snimok d where d.fakt_id=f.id),
    (select d.inn_na_stranice from ish.dokaz_snimok d where d.fakt_id=f.id),
    (select d.tip_na_stranice from ish.dokaz_snimok d where d.fakt_id=f.id)
    -- posrednik=1 — уполномоченные органы (департаменты госзаказа, центры закупок,
    -- администрации): закупку размещают они, а машина встаёт у подведомственного.
    -- Их 75, и ни у одного нет надзорной записи ЭПБ, которая выдаётся эксплуатанту.
    from ish.fakt f where f.v_parke=1 and coalesce(f.v_obzvone,0)=0
      and coalesce(f.posrednik,0)=0""")
p.execute("""insert into fakt_ssylka select s.fakt_id, s.url, coalesce(s.istochnik,''),
    coalesce(s.pervoistochnik,0) from ish.fakt_ssylka s
    where s.fakt_id in (select id from fakt)""")
p.execute("""create table kontakt(
    inn text, vid text, znachenie text, person text, dolzhnost text, rol text,
    krug integer, lichnyy integer, mobilnyy integer, ssylok integer, ssylka text)""")

p.execute("""insert into predpriyatie
select e.inn,
       coalesce(nullif(e.nazvanie,''), f.imya, s.name, g.imya),
       coalesce(nullif(e.region,''), f.region, s.region),
       coalesce(nullif(f.okved,''), nullif(e.okved,''), nullif(s.okved,''), g.okved),
       case when coalesce(f.okved,'')<>''  then coalesce(f.okved_otkuda,'реквизиты')
            when coalesce(e.okved,'')<>''  then 'парк'
            when coalesce(s.okved,'')<>''  then 'база обзвона'
            when coalesce(g.okved,'')<>''  then 'ЕГРЮЛ'
            else '' end,
       -- полный список кодов (у предприятия их бывает семь и больше): по одному
       -- коду профиль не читается, а в карточке он нужен свёрнутым списком
       coalesce(nullif(f.okved_vse,''), s.okved_all),
       -- ВЫРУЧКА ТОЛЬКО ПОЛОЖИТЕЛЬНАЯ И ТОЛЬКО ЧИСЛОМ.
       -- Здесь был дефект, найденный пробой панели: `predpriyatie.vyruchka` в park.db
       -- имеет тип TEXT, а в SQLite ЛЮБОЙ текст больше любого числа, поэтому '0.0' > 0
       -- давало истину, и 589 предприятий с нулём попадали в «с выручкой». Панель
       -- показывала 1 827 вместо 1 238. Отсюда cast(... as real) и отсечка > 0:
       -- ноль — это «данных нет», а не «выручка нулевая».
       coalesce(nullif(cast(f.vyruchka as real), 0),
                nullif(cast(e.vyruchka as real), 0),
                nullif(cast(s.revenue_rub as real), 0)),
       case when cast(f.vyruchka as real) > 0 then coalesce(f.vyruchka_otkuda,'реквизиты')
            when cast(e.vyruchka as real) > 0 then 'парк'
            when cast(s.revenue_rub as real) > 0 then 'база обзвона'
            else '' end,
       f.ssch,
       coalesce(nullif(e.status_egrul,''), g.status, s.egrul_status),
       e.os, e.dokazano, e.rang_mashiny, e.sostoyaniya, e.sila_luchshaya,
       e.tipy, e.marki, e.faktov, e.ssylok,
       e.chelovek, e.dolzhnost, e.krug, coalesce(nullif(e.telefon,''), e.mobilnyy),
       e.pochta, e.ssylka_luchshaya, e.ssylka_luchshaya
from ish.predpriyatie e
left join ish.finansy f     on f.inn = e.inn
left join ish.spravochnik s on s.inn = e.inn
left join ish.egrul g       on g.inn = e.inn""")

p.execute("""insert into kontakt
select k.inn, k.vid, k.znachenie, k.person, k.dolzhnost, k.rol, k.rang,
       k.lichnyy, k.mobilnyy, k.ssylok, ''
from ish.kontakt k
where k.inn in (select inn from ish.predpriyatie)""")

# ссылка на КАЖДЫЙ контакт: первое наблюдение с открываемым адресом
p.execute("""update kontakt set ssylka = (
    select cs.source_url from ish.contact_source cs
    where cs.inn = kontakt.inn and cs.znachenie = kontakt.znachenie
      and cs.source_url like 'http%' limit 1)""")

p.execute("create index i_vyr on predpriyatie(vyruchka desc)")
p.execute("create index i_okv on predpriyatie(okved)")
p.execute("create index i_rang on predpriyatie(rang_mashiny desc)")
p.execute("create index i_kont on kontakt(inn)")
p.execute("create index i_fakt on fakt(inn)")
p.execute("create index i_fs on fakt_ssylka(fakt_id)")
p.commit()

q = lambda s: p.execute(s).fetchone()[0]
print('предприятий ......... %d' % q("select count(*) from predpriyatie"))
print('  с выручкой ........ %d' % q("select count(*) from predpriyatie where vyruchka>0"))
print('  с ОКВЭД ........... %d' % q("select count(*) from predpriyatie where coalesce(okved,'')<>''"))
print('  с техконтактом .... %d' % q("select count(*) from predpriyatie where krug<=2"))
print('фактов .............. %d' % q("select count(*) from fakt"))
print('  ссылок на факты ... %d' % q("select count(*) from fakt_ssylka"))
print('  со снимком ........ %d' % q("select count(*) from fakt where coalesce(snimok,'')<>''"))
print('  фактов без ссылки . %d' % q("select count(*) from fakt where id not in (select fakt_id from fakt_ssylka)"))
print('контактов ........... %d' % q("select count(*) from kontakt"))
print('  со ссылкой ........ %d' % q("select count(*) from kontakt where ssylka like 'http%'"))
for r in p.execute("select vyruchka_otkuda, count(*) from predpriyatie where vyruchka>0"
                   " group by 1 order by 2 desc"):
    print('  выручка из %-28s %d' % (r[0], r[1]))
p.close()
print('размер файла: %.1f МБ' % (os.path.getsize(CEL) / 1048576))

# -*- coding: utf-8 -*-
"""ЧИСЛА ДЛЯ ЖУРНАЛА — печатает готовый блок, который вставляется как есть.

Заведено после ВТОРОГО повтора одной и той же ошибки: в записях 54 и 59 я написал
числа фактов и ссылок, сложив базу прошлого тика с «принято» из отчёта вливания,
вместо того чтобы спросить базу. Оба раза расхождение вскрылось на следующем тике:

    запись 54: писал 78 462 факта — в базе было 76 868 (разница 1 594)
    запись 59: писал 79 585 фактов и 118 704 ссылки — в базе 78 894 и 115 623

Причина одна: `insert or ignore` молча не создаёт факт, у которого ключ уже есть, и
«принято» из прогона — это сколько строк прошло заслоны, а не сколько записей появилось.

Правило теперь механическое: в журнал идёт ТОЛЬКО вывод этого скрипта.
"""
import sqlite3, os, time

D = os.path.dirname(os.path.abspath(__file__))
p = sqlite3.connect('file:%s?mode=ro' % os.path.join(D, 'park.db'), uri=True)
q = lambda s: p.execute(s).fetchone()[0]
V = '(select distinct inn from fakt where v_parke=1)'


def kont(w):
    return q('select count(*) from (select distinct k.inn from kontakt k '
             'where k.inn in %s and %s)' % (V, w))


print('```')
print('измерено %s UTC запросом к park.db' % time.strftime('%H:%M', time.gmtime()))
print('фактов %d | в парке %d | предприятий %d | ссылок %d | без ссылки %d'
      % (q('select count(*) from fakt'), q('select count(*) from fakt where v_parke=1'),
         q('select count(distinct inn) from fakt where v_parke=1'),
         q('select count(*) from fakt_ssylka'),
         q('select count(*) from fakt where id not in (select fakt_id from fakt_ssylka)')))
print('исключено %d | возвращено встречной проверкой %d'
      % (q("select count(*) from fakt where vid_fakta='НЕТ'"),
         q('select count(*) from pravka_isklyucheniya')))
print('контакты по ПАРКУ: любой %d | телефон %d | почта %d | техконтакт %d | без контакта %d'
      % (kont("k.vid in ('telefon','email') and k.ssylok>0"),
         kont("k.vid='telefon' and k.ssylok>0"), kont("k.vid='email' and k.ssylok>0"),
         kont('k.rang<=2 and k.ssylok>0'),
         q('select count(distinct inn) from fakt where v_parke=1')
         - kont("k.vid in ('telefon','email') and k.ssylok>0")))
print('финансы: выручка %d | ОКВЭД %d'
      % (q('select count(*) from finansy where vyruchka is not null'),
         q("select count(*) from finansy where coalesce(okved,'')<>''")))
print('ранг: A(сумма) %d | B(кВт/м3) %d | C(серия) %d | только тип %d'
      % (q("select count(*) from fakt where chem_rang like '%A: сумма%'"),
         q("select count(*) from fakt where chem_rang like '%B:%'"),
         q("select count(*) from fakt where chem_rang like '%C: серия%'"),
         q('select count(*) from fakt where v_parke=1 and rang_mashiny=2')))
# ВЫДАЧА СЧИТАЕТСЯ ПО ФАКТАМ, а не по таблице `predpriyatie`. Та таблица — снимок последней
# пересборки (`park_vydacha.py`), и между вливанием и пересборкой она врёт: 10.08 в 16:56
# показывала 5 140, тогда как фактическая выдача была уже 5 282. Это ровно то, за что я
# ловил соседей — число из прошлого прогона вместо числа из хранилища.
print('выдача %d предприятий (по фактам: в парке и не показан в обзвоне)'
      % q('select count(distinct inn) from fakt where v_parke=1 and coalesce(v_obzvone,0)=0'))
print('  в последней пересборке выдачи было %d | без открываемого доказательства %d'
      % (q('select count(*) from predpriyatie'),
         q("select count(*) from predpriyatie where dokazano like 'ДОКАЗАТЕЛЬСТВО%'")))
print('  фактов без единой СИЛЬНОЙ ссылки %d у %d предприятий'
      % (q('''select count(*) from fakt f where f.v_parke=1 and coalesce(f.v_obzvone,0)=0
             and exists(select 1 from fakt_ssylka s where s.fakt_id=f.id)
             and not exists(select 1 from fakt_ssylka s where s.fakt_id=f.id
                and s.url not like '%conclusions?exploiter=%' and s.url not like '%epz/organization/%'
                and s.url not like '%etpgpb.ru%' and s.url not like '%hh.ru%')'''),
         q('''select count(distinct f.inn) from fakt f where f.v_parke=1 and coalesce(f.v_obzvone,0)=0
             and exists(select 1 from fakt_ssylka s where s.fakt_id=f.id)
             and not exists(select 1 from fakt_ssylka s where s.fakt_id=f.id
                and s.url not like '%conclusions?exploiter=%' and s.url not like '%epz/organization/%'
                and s.url not like '%etpgpb.ru%' and s.url not like '%hh.ru%')''')))
print('```')
p.close()

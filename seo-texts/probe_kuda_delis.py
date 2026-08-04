# -*- coding: utf-8 -*-
"""Куда делись 200 компаний из панели: считаем по подписям скрытий, а не по памяти.

ПОЧЕМУ ЭТО ВЕРОЯТНО МОЯ РАБОТА. 03.08 я скрыла 882 предприятия и 19 248 отдельных фактов с
причинами «центробежность не доказана» и «суд моделей: нет». Все скрытия легли под подписью
`admin`. Если панель показывает пользователю всё, кроме скрытого ЛЮБЫМ пользователем, то мои
решения убрали компании и у user1, и у user2 — они этого не выбирали и не видели причины.

Считаю четыре вещи, и порознь:
  * сколько компаний в базе всего;
  * сколько скрыто и КЕМ подписано;
  * сколько увидит каждый пользователь, если панель фильтрует по своей подписи, и сколько —
    если по общей;
  * когда именно скрывали, по часам, чтобы совпасть с «было 200, стало меньше».
Разница между двумя способами фильтра и есть ответ на вопрос «куда делось».
"""
import json
import sqlite3

cx = sqlite3.connect(r'C:\seostat\data\centro_sales.db')
cx.execute('attach database ? as f', (r'C:\seostat\data\centrifugal.db',))
o = {}
o['компаний_в_базе'] = cx.execute('select count(*) from f.company').fetchone()[0]
o['скрытий_company_всего'] = cx.execute(
    "select count(*) from hidden_item where kind='company'").fetchone()[0]
o['скрытых_ИНН_company'] = cx.execute(
    "select count(distinct inn) from hidden_item where kind='company'").fetchone()[0]
o['скрытия_company_по_подписи'] = dict(cx.execute(
    "select coalesce(nullif(trim(username),''),'(без подписи)'), count(*) "
    "from hidden_item where kind='company' group by 1 order by 2 desc").fetchall())
o['скрытия_company_по_часам'] = cx.execute(
    "select substr(coalesce(created_at,''),1,13), count(*) from hidden_item "
    "where kind='company' group by 1 order by 1").fetchall()
o['причины_company'] = cx.execute(
    "select substr(coalesce(reason,''),1,70), count(*) from hidden_item where kind='company' "
    "group by 1 order by 2 desc limit 8").fetchall()

# Сколько увидит каждый, если фильтр по своей подписи, и сколько — если общий.
for kto in ('admin', 'user1', 'user2'):
    svoi = cx.execute(
        "select count(distinct inn) from hidden_item where kind='company' and username=?",
        (kto,)).fetchone()[0]
    o[f'{kto}: скрыл_сам'] = svoi
o['видно_если_фильтр_общий'] = o['компаний_в_базе'] - o['скрытых_ИНН_company']
o['видно_если_фильтр_по_своей_подписи_user2'] = (
    o['компаний_в_базе'] - o.get('user2: скрыл_сам', 0))

# Скрытия фактов тоже убирают компанию из очереди, если у неё не осталось видимых фактов.
o['компаний_без_единого_видимого_факта'] = cx.execute("""
    select count(*) from (
      select c.inn from f.company c
      join f.fact t on t.inn = c.inn
      where not exists (select 1 from hidden_item h
                        where h.kind='company' and h.inn = c.inn)
      group by c.inn
      having sum(case when exists (select 1 from hidden_item h2
                                   where h2.kind='fact' and h2.inn = t.inn
                                     and h2.value = cast(t.id as text))
                      then 0 else 1 end) = 0)""").fetchone()[0]
print(json.dumps(o, ensure_ascii=False, indent=1))

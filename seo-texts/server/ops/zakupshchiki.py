# -*- coding: utf-8 -*-
"""Где лежат контакты закупщиков/снабженцев: по таблицам enrich и панели — сколько, с именем ли,
писали ли им, заведены ли в панель."""
import collections, re, sqlite3
e = sqlite3.connect("file:C:\\sender\\enrich.db?mode=ro", uri=True, timeout=30)
s = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True, timeout=30)
ЗАК = re.compile(r"снабж|закуп|тендер|мтс|омтс|procure|purchas|zakup|snab|tender", re.I)
в_панели = {r[0].lower() for r in s.execute("SELECT email FROM recipients")}
писали = {r[0].lower() for r in s.execute("SELECT DISTINCT email FROM send_log WHERE outcome='sent'")}
def отчёт(имя, строки):
    сч = collections.Counter(); инн = set()
    for inn, em, person, роль in строки:
        em = (em or "").lower()
        if not em or not (ЗАК.search(роль or "") or ЗАК.search(em.split("@")[0])): continue
        инн.add(inn); сч["адресов"] += 1
        сч["с именем"] += bool((person or "").strip())
        сч["в панели"] += em in в_панели
        сч["писали"] += em in писали
    print("%-28s компаний %5d | %s" % (имя, len(инн), dict(сч)))
отчёт("enrich.emails (role)", e.execute("SELECT inn, email, person, COALESCE(role,'')||' '||COALESCE(zahod_rol,'') FROM emails"))
отчёт("enrich.people", e.execute("SELECT inn, email, person, COALESCE(post,'')||' '||COALESCE(role,'') FROM people"))
отчёт("enrich.eis_arch (ЕИС)", e.execute("SELECT inn, email, person, COALESCE(post,'')||' '||COALESCE(role,'') FROM eis_arch"))
отчёт("enrich.imena", e.execute("SELECT inn, email, person, COALESCE(post,'')||' '||COALESCE(role,'') FROM imena"))
отчёт("enrich.vne_bazy_emails", e.execute("SELECT inn, email, person, COALESCE(role,'') FROM vne_bazy_emails"))
print("роли в emails:", e.execute("SELECT role, COUNT(*) FROM emails GROUP BY 1 ORDER BY 2 DESC LIMIT 12").fetchall())
print("группы в панели с «закуп»/«снаб»:", [r for r in s.execute("SELECT DISTINCT source FROM recipients") if re.search("закуп|снаб|zakup|snab|eis|еис|tender", str(r[0]), re.I)][:10])

# -*- coding: utf-8 -*-
"""Остаток «по имени» по направлениям: контакты с подтверждённым именем (enrich.emails imya_ok=1
и enrich.imena mozhno_po_imeni=1), лучший на компанию, после исключений (отвечали, стоп, мёртв,
адрес < 15 дней, уже в «КЦ по имени»). Плюс сколько КЦ-кандидатов ждут окна 15 дней."""
import collections, re, sqlite3
s = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True, timeout=30)
e = sqlite3.connect("file:C:\\sender\\enrich.db?mode=ro", uri=True, timeout=30)
o = sqlite3.connect("file:C:\\sender\\obzvon-index.db?mode=ro", uri=True, timeout=30)
напр = {}
for inn, d in o.execute("SELECT inn, division FROM obzvon"):
    d = str(d or "").lower(); напр[str(inn)] = "оба" if "kc" in d and "meyer" in d else ("КЦ" if "kc" in d else ("Meyer" if "meyer" in d else "?"))
ответ = {str(r[0]) for r in s.execute("SELECT DISTINCT r.inn FROM events e JOIN recipients r ON r.id=e.recipient_id WHERE e.event_type IN ('reply','complaint','unsubscribe')")}
стоп = {v.lower() for _, v in s.execute("SELECT scope, value FROM suppression")}
мёртв = {r[0].lower() for r in s.execute("SELECT email FROM addr_probe WHERE verdict IN ('нет ящика','нет MX','неясно','отказ пробе')")}
адр15 = {r[0].lower() for r in s.execute("SELECT DISTINCT email FROM send_log WHERE outcome='sent' AND ts>=datetime('now','-15 days')")}
в_камп = {str(r[0]) for r in s.execute("SELECT cr.inn FROM confirm_reviews cr JOIN campaigns c ON c.id=cr.campaign_id WHERE c.name='КЦ по имени 06.11'")}
писали = {str(r[0]) for r in s.execute("SELECT DISTINCT inn FROM send_log WHERE outcome='sent' AND inn IS NOT NULL")}
годно = collections.defaultdict(dict); ждут = collections.Counter()
строки = list(e.execute("SELECT inn, email, person FROM emails WHERE imya_ok='1' AND person IS NOT NULL AND email IS NOT NULL")) + \
         list(e.execute("SELECT inn, email, person FROM imena WHERE mozhno_po_imeni=1 AND email IS NOT NULL"))
for inn, em, p in строки:
    inn, em = str(inn), (em or "").lower()
    if inn in ответ or em in стоп or inn in стоп or em in мёртв or inn in в_камп: continue
    н = напр.get(inn, "?")
    if em in адр15: ждут[н] += 1; continue
    годно[н][inn] = em
for н in ("КЦ", "Meyer", "оба", "?"):
    v = годно.get(н, {})
    print("%-6s компаний с именем: %5d | из них ещё не писали вовсе: %5d | адресов ждут окна 15 дней: %d" % (н, len(v), sum(1 for i in v if i not in писали), ждут[н]))

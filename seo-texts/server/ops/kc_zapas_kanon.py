# -*- coding: utf-8 -*-
"""Запас под канон КЦ «по имени» (заход «ноябрь–декабрь, бюджеты», РЖД/Алроса/Северсталь; gen_imennye_kc / gen_9000_kc).
Владелец 17.11: «партию лучше брать вот эту, с перепроверкой что компания в принципе подходит по направлениям».
Ступени от базы обзвона КЦ: КЦ ещё не писал (по ИНН, ни одного отправленного письма КЦ) → нет ответа/жалобы →
вердикт направления (kompaniya_verdikt) → ОКВЭД 05–43/49–52 и не больница/школа/ТД (как в gen_9000_kc) →
есть почта (enrich.emails / recipients / obzvon), не мёртвая и не в стопе. Только чтение."""
import re, sqlite3
from collections import Counter
ц = lambda x: "".join(c for c in str(x or "") if c.isdigit())
s = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True, timeout=30)
e = sqlite3.connect("file:C:\\sender\\enrich.db?mode=ro", uri=True, timeout=30)
o = sqlite3.connect("file:C:\\sender\\obzvon-index.db?mode=ro", uri=True, timeout=30)
кам = {i: н for i, н in s.execute("SELECT id, name FROM campaigns")}
кц_к = {i for i, н in кам.items() if re.search(r"(?i)кц|компрессор|\bkc\b", н or "") and not re.search(r"(?i)meyer|мейер|фса|рентген|сепарат", н or "")}
писал = {ц(i) for i, к in s.execute("SELECT r.inn, m.campaign_id FROM messages m JOIN recipients r ON r.id=m.recipient_id WHERE m.status IN ('sent','sending','scheduled','pending_review')") if к in кц_к}
ответ = {ц(r[0]) for r in s.execute("SELECT DISTINCT r.inn FROM events e JOIN recipients r ON r.id=e.recipient_id WHERE e.event_type IN ('reply','complaint','unsubscribe')")}
стоп = {v.lower() for _, v in s.execute("SELECT scope, value FROM suppression")}
мёртв = {r[0].lower() for r in s.execute("SELECT email FROM addr_probe WHERE verdict IN ('нет ящика','нет MX')")} | \
        {r[0].lower() for r in o.execute("SELECT email FROM email_probe WHERE verdict IN ('нет ящика','нет MX')")}
вер = {ц(i): (р or "", н or "") for i, р, н in o.execute("SELECT inn, rusprom, napr FROM kompaniya_verdikt")}
почта = {}
for i, em in e.execute("SELECT inn, lower(email) FROM emails WHERE email LIKE '%@%'"): почта.setdefault(ц(i), set()).add(em)
for i, em in s.execute("SELECT inn, lower(email) FROM recipients WHERE email LIKE '%@%'"): почта.setdefault(ц(i), set()).add(em)
ПЛОХ_ИМЯ = re.compile(r"(?i)больниц|ЦРБ|поликлиник|медицин|клиник|санатор|школ|детск\w* сад|университет|колледж|торгов\w* дом|^ТД |\bТД\b")
ст = Counter(); вердикты = Counter(); итог = Counter()
for inn, div, ок, имя, eb, es in o.execute("SELECT inn, division, okved_main, name_short, emails_base, emails_site FROM obzvon"):
    if "kc" not in str(div or "").lower(): continue
    inn = ц(inn); ст["1. база обзвона КЦ"] += 1
    if inn in писал: continue
    ст["2. КЦ ещё не писал"] += 1
    if inn in ответ: continue
    ст["3. без ответа/жалобы/отписки"] += 1
    р, н = вер.get(inn, ("", ""))
    кл = ("нет вердикта" if not (р or н) else "%s / %s" % (р or "-", н or "-")); вердикты[кл] += 1
    if р == "не покупатель" or н in ("никуда", "не кц", "мейер"): continue
    ст["4. направление не против КЦ"] += 1
    м = re.match(r"(\d{2})", str(ок or ""))
    if not м or not (5 <= int(м.group(1)) <= 43 or 49 <= int(м.group(1)) <= 52) or ПЛОХ_ИМЯ.search(str(имя or "")): continue
    ст["5. ОКВЭД КЦ (05–43, 49–52)"] += 1
    адр = set(почта.get(inn, set())) | {x.strip().lower() for x in re.split(r"[,;\s]+", "%s %s" % (eb or "", es or "")) if "@" in x}
    адр = {a for a in адр if a not in мёртв and a not in стоп and a.split("@")[-1] not in стоп}
    if not адр: continue
    ст["6. есть живая почта"] += 1
    итог["вердикт «покупатель / кц»" if (р == "покупатель" and н == "кц") else ("вердикт «кц» без оценки покупателя" if н == "кц" else ("покупатель, направление не указано" if р == "покупатель" else "вердикта нет"))] += 1
for к_, v in sorted(ст.items()): print("%-36s %d" % (к_, v))
print("вердикты на ступени 3:", dict(вердикты.most_common(10)))
print("на ступени 6 по вердикту:", dict(итог))

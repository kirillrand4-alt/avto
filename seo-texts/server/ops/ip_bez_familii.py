# -*- coding: utf-8 -*-
"""Письма КЦ на подтверждении для ИП с фамилией в теме/вопросе (владелец 16.10:
«ИП он странно обзывает», «сам исправь»): тема «…на производстве «Фамилия»» ->
«…на вашем производстве», в тексте «для «Фамилии»» -> «для вашего производства».
Правка в edited_subject/edited_body карточки, старое — в _ops/ip-bez-familii.jsonl.
Без --primenit — показать."""
import io, json, re, sqlite3, sys, time
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
ряды = c.execute("SELECT cr.id, r.company_name, COALESCE(cr.edited_subject, cr.subject), COALESCE(cr.edited_body, cr.body) "
                 "FROM confirm_reviews cr JOIN recipients r ON r.id=cr.recipient_id "
                 "WHERE cr.status='pending' AND cr.campaign_id IN (15,16) AND r.company_name LIKE 'ИП %'").fetchall()
изм = []
for rid, name, s, b in ряды:
    фам = name.split()[1] if len(name.split()) > 1 else ""
    if not фам or фам[:4].lower() not in (s + b).lower():
        continue
    основа = re.escape(фам[:max(4, len(фам) - 2)])
    s2 = re.sub(r"(?i)на производстве\s+«" + основа + r"\w*»", "на вашем производстве", s)
    s2 = re.sub(r"(?i)\s+в\s+«" + основа + r"\w*»", "", s2)
    b2 = re.sub(r"(?i)для\s+«" + основа + r"\w*»", "для вашего производства", b)
    b2 = re.sub(r"(?i)\s+(в|у)\s+«" + основа + r"\w*»", "", b2)
    b2 = re.sub(r"(?i)«" + основа + r"\w*»", "вашей компании", b2)
    if (s2, b2) != (s, b):
        изм.append((rid, name, s, b, s2, b2))
print("ИП на подтверждении:", len(ряды), "| к правке:", len(изм))
for rid, name, s, b, s2, b2 in изм[:4]:
    print("\n#%d %s\n  было: %s\n  стало: %s" % (rid, name, s, s2))
    for стр in b2.split("\n"):
        if "вашего производства" in стр or "вашей компании" in стр: print("  текст:", стр[:160])
if "--primenit" in sys.argv:
    т = time.strftime("%Y-%m-%dT%H:%M:%S")
    with c, io.open(r"C:\sender\_ops\ip-bez-familii.jsonl", "a", encoding="utf-8") as ж:
        for rid, name, s, b, s2, b2 in изм:
            ж.write(json.dumps({"id": rid, "subject": s, "body": b}, ensure_ascii=False) + "\n")
            c.execute("UPDATE confirm_reviews SET edited_subject=?, edited_body=?, updated_at=? WHERE id=? AND status='pending'", (s2, b2, т, rid))
    print("исправлено:", len(изм))

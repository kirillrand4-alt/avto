# -*- coding: utf-8 -*-
"""Кампания 22: сколько писем с обращением по имени; у писем без имени — известно ли имя где-то ещё
(enrich.emails: колонки с ФИО/именем; панель карточки). Только чтение."""
import json, re, sqlite3
from collections import Counter
c = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True)
ce = sqlite3.connect("file:C:\\sender\\enrich.db?mode=ro", uri=True)
кол = [r[1] for r in ce.execute("PRAGMA table_info(emails)")]
имк = [k for k in кол if re.search(r"fio|name|имя|person", k, re.I)]
print("колонки имени в enrich.emails:", имк)
сч = Counter()
for em, тело, pj, st in c.execute("SELECT lower(email), COALESCE(edited_body, body), panel_json, status FROM confirm_reviews WHERE campaign_id=22 AND status IN ('pending','approved')"):
    первая = (тело or "").split("!")[0]
    if not первая.strip().startswith("Добрый день"): сч["с именем"] += 1; continue
    сч["без имени"] += 1
    есть = None
    if имк:
        р = ce.execute("SELECT %s FROM emails WHERE lower(email)=?" % ",".join(имк), (em,)).fetchone()
        if р and any((x or "").strip() for x in р): есть = "enrich"
    if not есть:
        д = json.loads(pj or "{}")
        for к in (д.get("contacts") or д.get("emails") or []):
            if isinstance(к, dict) and (к.get("email") or "").lower() == em and (к.get("fio") or к.get("name") or "").strip(): есть = "панель"
    сч["без имени, но имя известно (%s)" % есть if есть else "без имени, имени нигде нет"] += 1
print(dict(сч))

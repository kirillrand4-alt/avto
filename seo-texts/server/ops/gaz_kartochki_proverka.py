# -*- coding: utf-8 -*-
"""Проверка карточек газовой кампании «КЦ газ 11.11»: статусы, ящики, дубли ИНН/адреса, механика текста, 3 примера.
Только чтение."""
import json, re, sqlite3
from collections import Counter
c = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True, timeout=60)
к = c.execute("SELECT id FROM campaigns WHERE name='КЦ газ 11.11'").fetchone()[0]
р = c.execute("SELECT id, status, inn, lower(email), subject, body, panel_json, message_id FROM confirm_reviews WHERE campaign_id=?", (к,)).fetchall()
print("кампания", к, "| карточек", len(р), "| статусы", dict(Counter(x[1] for x in р)))
print("ящики:", dict(Counter(json.loads(x[6] or "{}").get("mailbox_id") for x in р).most_common(30)))
print("дубли ИНН:", sum(1 for v in Counter(x[2] for x in р).values() if v > 1), "| дубли адреса:", sum(1 for v in Counter(x[3] for x in р).values() if v > 1))
ст = Counter(m[0] for m in c.execute("SELECT m.status FROM messages m JOIN confirm_reviews cr ON cr.message_id=m.id WHERE cr.campaign_id=?", (к,)))
print("статусы сообщений:", dict(ст))
беды = Counter()
for x in р:
    т = x[5] or ""
    if "—" in т: беды["длинное тире"] += 1
    if re.search(r"\d", т.replace("ноябре–декабре", "").replace("ближайшие 4 месяца", "")): беды["цифра"] += 1
    if т.count("\n\n") != 3: беды["абзацев не 4"] += 1
    if re.search(r"переход на собствен|без баллон|на площадке", т): беды["старый оборот"] += 1
    if "ИМЯ_ОТПРАВИТЕЛЯ" in т: беды["метка имени"] += 1
    if not т.startswith(("Добрый день!",)) and ", добрый день!" not in т.split("\n")[0]: беды["приветствие"] += 1
    im = re.match(r"(\S+)[ ,].*?Меня зовут (\S+),", т)
    if im and im.group(1).strip(",") == im.group(2): беды["тёзка"] += 1
print("механика текста:", dict(беды) or "чисто")
print("по имени:", sum(1 for x in р if ", добрый день!" in (x[5] or "").split("\n")[0]), "| без имени:", sum(1 for x in р if (x[5] or "").startswith("Добрый день!")))
for x in р[:3]:
    print("\n=== #%d | %s | %s\nТема: %s\n%s" % (x[0], x[3], json.loads(x[6]).get("mailbox_id"), x[4], x[5]))

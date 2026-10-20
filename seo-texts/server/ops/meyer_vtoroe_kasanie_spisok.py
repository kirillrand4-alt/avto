# -*- coding: utf-8 -*-
"""Второе касание Meyer — список (владелец 20.10: «давай»). Только чтение,
пишет _ops/meyer-vtoroe-kasanie.json.

Берём компании (ИНН), которым писали Meyer и которые:
  * не ответили (ни лида, ни ответа/автоответа);
  * последнее письмо Meyer этой компании — старше 30 дней (правило повтора
    30 дней тем же направлением, владелец 20.10);
  * имеют следующий адрес по лесенке ролей (lead_scoring._rol_ball): ему ещё не
    писали, не в стоп-листе, не «не для письма», проба «есть» или «принимает всё».
Текст — копия последнего письма Meyer компании; обращение по имени заменяем на
«Добрый день!» (или имя нового контакта, если оно известно). Письма, где текст
обращается к роли прошлого адресата («вам как …»), помечаем отдельно."""
import io
import json
import re
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timedelta

sys.path.insert(0, r"C:\sender\server")
try:
    from lead_scoring import _rol_ball
except Exception:  # noqa: BLE001
    def _rol_ball(_р):
        return 4

c = sqlite3.connect(r"C:\sender\sender.db")
e = sqlite3.connect(r"C:\sender\enrich.db")
граница = (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S")
кам = {r[0]: r[1] for r in c.execute("SELECT id, name FROM campaigns")}
meyer_cid = {k for k, v in кам.items() if "meyer" in str(v).lower() or "мейер" in str(v).lower()}
кол_m = {r[1] for r in c.execute("PRAGMA table_info(messages)")}
тело_поле = "body_rendered" if "body_rendered" in кол_m else "body"
тема_поле = "subject_rendered" if "subject_rendered" in кол_m else "subject"

посл = {}
писем_meyer = Counter()
for inn, ts, mid, su, bo, mb, cid, em in c.execute(
        "SELECT r.inn, m.sent_at, m.id, m.%s, m.%s, m.mailbox_id, m.campaign_id, lower(r.email) FROM messages m "
        "JOIN recipients r ON r.id=m.recipient_id WHERE m.status='sent' AND r.inn IS NOT NULL AND r.inn!='' "
        "AND m.campaign_id IN (%s) ORDER BY m.sent_at" % (тема_поле, тело_поле, ",".join(map(str, meyer_cid)))):
    писем_meyer[str(inn)] += 1
    посл[str(inn)] = {"ts": str(ts), "mid": mid, "тема": su, "тело": bo, "ящик": mb, "кампания": cid, "был_адрес": em}
ответ = {str(r[0]) for r in c.execute("SELECT DISTINCT inn FROM leads WHERE inn IS NOT NULL")}
ответ |= {str(r[0]) for r in c.execute(
    "SELECT DISTINCT r.inn FROM events ev JOIN recipients r ON r.id=ev.recipient_id "
    "WHERE ev.event_type IN ('reply','reply_auto') AND r.inn IS NOT NULL")}
писали_адр = {str(r[0]).lower() for r in c.execute("SELECT email FROM send_log")}
писали_адр |= {str(r[0]).lower() for r in c.execute(
    "SELECT r.email FROM messages m JOIN recipients r ON r.id=m.recipient_id WHERE m.status NOT IN ('skipped','failed')")}
стоп = {str(r[0]).lower() for r in c.execute("SELECT value FROM suppression")}
стоп_инн = {"".join(ch for ch in str(r[0]) if ch.isdigit()) for r in c.execute("SELECT value FROM suppression")}
проба = {str(r[0]).lower(): str(r[1] or "") for r in c.execute("SELECT email, verdict FROM addr_probe")}
for r in e.execute("SELECT lower(email), probe_verdict FROM emails WHERE probe_verdict IS NOT NULL"):
    проба.setdefault(r[0], str(r[1] or ""))
кол_e = [r[1] for r in e.execute("PRAGMA table_info(emails)")]
имя_поле = next((k for k in ("fio", "name", "contact_name", "person") if k in кол_e), None)

ПЛОХОЙ_ЯЩИК = re.compile(r"(?i)privacy|abuse|noreply|no-reply|postmaster|webmaster|^hr|^job|^rabota|^resume|^kadr|^buh|^bux|"
                         r"^account|^press|^pr$|^media|^marketing|^reklama|^news|^support|^help|^admin")
ПУБЛИЧНЫЕ = {"mail.ru", "bk.ru", "list.ru", "inbox.ru", "yandex.ru", "ya.ru", "gmail.com", "rambler.ru", "yandex.com"}
сч = Counter()
итог = []
роли = Counter()
пробы = Counter()
РОЛЬ_ПРОШЛОГО = re.compile(r"(?i)вам как|как руководител|как главн|как специалист|как снабжен|как технолог")
for inn, п in посл.items():
    if inn in ответ:
        сч["ответили"] += 1
        continue
    if п["ts"] > граница:
        сч["письмо Meyer моложе 30 дней"] += 1
        continue
    if inn in стоп_инн:
        сч["ИНН в стоп-листе"] += 1
        continue
    # Второе касание — только тем, кому Meyer писал ОДИН раз: у кого уже было
    # два письма (кампания «Второе касание» сентября), это было бы третье.
    if писем_meyer[inn] >= 2:
        сч["Meyer писал уже 2+ раза"] += 1
        continue
    сайт = ""
    try:
        сайт = str((e.execute("SELECT site FROM companies WHERE inn=?", (inn,)).fetchone() or [""])[0] or "")
    except Exception:  # noqa: BLE001
        pass
    свои_домены = {п["был_адрес"].split("@")[-1], re.sub(r"^www\.", "", сайт.lower().split("//")[-1].split("/")[0])} - {""}
    канд = []
    for row in e.execute("SELECT lower(email), role%s FROM emails WHERE inn=?" % ((", " + имя_поле) if имя_поле else ""), (inn,)):
        адр, роль = row[0], str(row[1] or "")
        if "не для письма" in роль.lower() or _rol_ball(роль) <= 1:
            continue
        if адр in писали_адр or адр in стоп:
            continue
        # Мусорные адреса: ИНН вместо имени ящика, служебные ящики, «Прочее».
        лок, дом = адр.split("@")[0], адр.split("@")[-1]
        if лок.isdigit() or ПЛОХОЙ_ЯЩИК.search(лок) or роль.strip().lower().startswith("прочее"):
            continue
        # Чужой домен (не домен прошлого адреса и не сайт компании) — только
        # публичные почтовики пропускаем: там у компаний бывают свои ящики.
        if дом not in свои_домены and дом not in ПУБЛИЧНЫЕ:
            continue
        в = проба.get(адр, "")
        if в not in ("есть", "принимает всё"):
            continue
        канд.append((-_rol_ball(роль), 0 if в == "есть" else 1, адр, роль, в, (row[2] if имя_поле else None)))
    if not канд:
        сч["нет живого следующего адреса"] += 1
        continue
    канд.sort()
    _б, _п, адр, роль, в, имя = канд[0]
    тело = str(п["тело"] or "").split("\n\nС уважением,")[0]
    имя_ок = str(имя or "").strip().split()
    обращение = "Добрый день, %s!" % имя_ок[1] if len(имя_ок) >= 2 else "Добрый день!"
    тело_нов, n = re.subn(r"^Добрый день,[^\n!]*!", обращение, тело, count=1)
    итог.append({"inn": inn, "кому": адр, "роль": роль, "проба": в, "был_адрес": п["был_адрес"],
                 "исх_письмо": п["mid"], "исх_ящик": п["ящик"], "исх_кампания": п["кампания"], "исх_дата": п["ts"][:10],
                 "тема": п["тема"], "тело": тело_нов, "обращение_заменено": bool(n),
                 "роль_прошлого_в_тексте": bool(РОЛЬ_ПРОШЛОГО.search(тело))})
    роли[(роль.split("|")[0].strip() or "без роли")[:40]] += 1
    пробы[в] += 1
    сч["в списке"] += 1
json.dump(итог, io.open(r"C:\sender\_ops\meyer-vtoroe-kasanie.json", "w", encoding="utf-8"), ensure_ascii=False)
print("компаний Meyer, которым писали:", len(посл))
for k, v in сч.most_common():
    print("  %-34s %5d" % (k, v))
print("проба выбранного адреса:", dict(пробы))
print("обращение по имени заменено:", sum(1 for x in итог if x["обращение_заменено"]),
      "| текст обращается к роли прошлого адресата:", sum(1 for x in итог if x["роль_прошлого_в_тексте"]))
print("по кампаниям исходного письма:", Counter(кам.get(x["исх_кампания"]) for x in итог).most_common())
print("роли выбранных адресов:")
for k, v in роли.most_common(15):
    print("  %5d  %s" % (v, k))
for x in итог[:3]:
    print("\n---- %s -> %s (%s, %s), было %s\nТема: %s\n%s" % (x["inn"], x["кому"], x["роль"][:40], x["проба"], x["был_адрес"], x["тема"], x["тело"][:500]))

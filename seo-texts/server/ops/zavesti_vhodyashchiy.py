# -*- coding: utf-8 -*-
"""Завести в ленту лидов входящее письмо, которое панель не подхватила (из _ops/otvety-v-yashchikah.json),
БЕЗ привязки к чужой компании по общему домену (mail.ru и т.п.): создаётся отдельный получатель без ИНН.
    zavesti_vhodyashchiy.py <адрес_отправителя> <направление kc|meyer> [hot|warm] [--katit]"""
import io, json, sys
from datetime import datetime, timezone
sys.path.insert(0, r"C:\sender")
from sender.config import Config        # noqa: E402
from sender.store import Store          # noqa: E402
from sender.leaddesk import LeadDesk    # noqa: E402
адр, напр = sys.argv[1].lower(), sys.argv[2]
вид = sys.argv[3] if len(sys.argv) > 3 and not sys.argv[3].startswith("--") else "warm"
x = next((z for z in json.load(io.open(r"C:\sender\_ops\otvety-v-yashchikah.json", encoding="utf-8")) if z["от"] == адр), None)
if not x: sys.exit("нет такого отправителя в otvety-v-yashchikah.json")
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db")); к = store._conn
есть = к.execute("SELECT id, company_name, inn FROM recipients WHERE lower(email)=?", (адр,)).fetchone()
имя = "Входящий: " + (x.get("имя") or адр)
print("письмо:", x["ящик"], x["папка"], x["дата"], "| тема:", x["тема"], "| получатель в базе:", есть)
if "--katit" not in sys.argv: sys.exit("сухой прогон; заведение — --katit")
if есть: rid = есть[0]
else:
    сейчас = datetime.now(timezone.utc).isoformat()
    with store._lock:
        rid = к.execute("INSERT INTO recipients (email, company_name, inn, segment, domain, tz, contact_name, source, extra_json, created_at, updated_at) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?)", (адр, имя, None, напр, адр.split("@")[-1], "Europe/Moscow", x.get("имя") or None,
                        "vhodyashchiy-imap", json.dumps({"target_division": напр}, ensure_ascii=False), сейчас, сейчас)).lastrowid
        к.commit()
lid = LeadDesk(cfg, store).push_warm_lead(store.get_recipient(int(rid)), x["msgid"] or ("imap:%s" % адр),
        "[%s] [ящик %s, %s] %s" % (вид, x["ящик"], "спам" if x["папка"] != "INBOX" else "входящие", x["тема"]), otvetil=адр, v_bitrix=False)
print("лид #%s заведён (получатель %s)" % (lid, rid))

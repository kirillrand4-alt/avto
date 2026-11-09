# -*- coding: utf-8 -*-
"""Владелец 09.11 «давай нормально и с привязкой к истории»: входящие, которые сборщик положил
событием «other» без получателя, привязываем к получателю и делаем ответом (тогда письмо видно
в «Переписке» карточки), и заводим/дополняем лид штатным LeadDesk.push_warm_lead.
    privyazat_vhodyashchie.py <id_события> <адрес_получателя_в_базе> [lead_id_дополнить] [--katit]
Метка лида — как у сборщика: [отказ] / [hot, тел …] (определяется по тексту, телефон — из тела)."""
import json, re, sys
sys.path.insert(0, r"C:\sender")
from sender.config import Config        # noqa: E402
from sender.store import Store          # noqa: E402
from sender.leaddesk import LeadDesk    # noqa: E402
ев, адр = int(sys.argv[1]), sys.argv[2].lower()
лид_доп = next((int(a) for a in sys.argv[3:] if a.isdigit()), None)
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db")); к = store._conn
e = к.execute("SELECT id, event_type, recipient_id, detail_json, mailbox_id FROM events WHERE id=?", (ев,)).fetchone()
rid = (к.execute("SELECT id FROM recipients WHERE lower(email)=?", (адр,)).fetchone() or [None])[0]
д = json.loads(e[3] or "{}"); сн = str(д.get("snippet") or "")
от = re.search(r"[\w.+-]+@[\w.-]+", str((д.get("headers") or {}).get("from") or д.get("from") or "")) if isinstance(д.get("headers"), dict) else None
от = от.group(0).lower() if от else None
от = next((a.split("=",1)[1].lower() for a in sys.argv if a.startswith("ot=")), от)
тел = re.search(r"(?:\+7|8|7)[\s(-]*\d{3}[\s)-]*\d{3}[\s-]*\d{2}[\s-]*\d{2}", сн)
тел = re.sub(r"\D", "", тел.group(0)) if тел else None
if тел and len(тел) == 11: тел = "+7" + тел[1:]
отказ = bool(re.search(r"(?i)не явля\w+|не имеем потребност|нет потребност|не интерес|не требуется|уже име\w+", сн))
метка = "[отказ]" if отказ else ("[hot, тел %s]" % тел if тел else "[hot]")
print("событие", e[:3], e[4], "| получатель", адр, rid, "| от", от, "| метка", метка, "| длина текста", len(сн))
if not rid: sys.exit("получатель не найден")
if "--katit" not in sys.argv: sys.exit("сухой прогон; применение — --katit")
with store._lock:
    к.execute("UPDATE events SET recipient_id=?, event_type='reply' WHERE id=? AND recipient_id IS NULL", (rid, ев)); к.commit()
if лид_доп:
    with store._lock:
        к.execute("UPDATE leads SET need=?, phone=COALESCE(?, phone), recipient_id=? WHERE id=?", (сн, тел, rid, лид_доп)); к.commit()
    print("лид #%d дополнен текстом письма%s" % (лид_доп, ", телефон " + тел if тел else ""))
else:
    lid = LeadDesk(cfg, store).push_warm_lead(store.get_recipient(int(rid)), "ev:%d" % ев, ("%s %s" % (метка, сн))[:900],
                                               otvetil=от, v_bitrix=False)
    print("лид #%s" % lid)

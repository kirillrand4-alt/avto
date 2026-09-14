# -*- coding: utf-8 -*-
"""Почему ответ Медведовского не стал лидом: событие, привязка, ветка.

Письмо в ящике ЕСТЬ и помечено прочитанным (значит сборщик его качал —
он ставит \\Seen сам). Смотрим: завелось ли событие reply, к кому оно
привязано, совпадает ли rfc_message_id нашего письма с In-Reply-To ответа,
и что говорит классификатор про этот текст.
"""
import sys
sys.path.insert(0, r"C:\sender")
from sender.store import Store                                  # noqa: E402

ПОЧТА = "krimck1600@mail.ru"
НАШ_MSGID = "<178851149701.405776.4491435817064420394@zernosort.ru>"
ТЕЛО = "День добрый.\nПришлите предложение по оборудованию."
ТЕМА = "Re: Вопрос по контролю включений в «Медведовский ЗПП»"

store = Store(r"C:\sender\sender.db")
вых = []
with store._lock:
    c = store._conn
    пол = c.execute("SELECT id, email, company_name, inn FROM recipients "
                    " WHERE email=?", (ПОЧТА,)).fetchone()
    вых.append("получатель: %s" % (dict(пол) if пол else "НЕ НАЙДЕН"))
    rid = пол["id"] if пол else None

    м = c.execute("SELECT id, rfc_message_id, thread_id, status, sent_at, "
                  "       mailbox_id, campaign_id FROM messages WHERE id=14957"
                  ).fetchone()
    вых.append("")
    вых.append("--- наше письмо 14957 ---")
    if м:
        for k in м.keys():
            вых.append("   %-16s %s" % (k, м[k]))
        совпало = (str(м["rfc_message_id"] or "").strip() == НАШ_MSGID.strip())
        вых.append("   rfc_message_id == Message-ID из ящика: %s"
                   % ("ДА" if совпало else "НЕТ"))

    кол = [x[1] for x in c.execute("PRAGMA table_info(events)")]
    вр = next((x for x in ("event_ts", "created_at", "ts") if x in кол), None)
    тп = next((x for x in ("event_type", "type") if x in кол), None)
    вых.append("")
    вых.append("--- все события по получателю %s ---" % rid)
    if rid:
        for р in c.execute("SELECT id, %s t, %s k, message_id, mailbox_id, "
                           "       dedup_key FROM events WHERE recipient_id=? "
                           " ORDER BY id" % (вр, тп), (rid,)):
            вых.append("   #%-7s %s %-12s письмо=%-7s ящик=%-28s %s"
                       % (р["id"], str(р["t"])[:19], р["k"],
                          str(р["message_id"]), str(р["mailbox_id"])[:28],
                          str(р["dedup_key"])[:28]))

    вых.append("")
    вых.append("--- колонки events ---")
    вых.append("   " + ", ".join(кол))
    дет = next((x for x in ("detail", "detail_json", "payload", "meta")
                if x in кол), None)
    вых.append("")
    вых.append("--- события, где в %s мелькает адрес клиента ---" % дет)
    n = 0
    for р in (c.execute("SELECT id, %s t, %s k, recipient_id, mailbox_id "
                        "  FROM events WHERE %s LIKE ? ORDER BY id"
                        % (вр, тп, дет), ("%krimck1600%",)) if дет else []):
        n += 1
        вых.append("   #%-7s %s %-12s получатель=%s ящик=%s"
                   % (р["id"], str(р["t"])[:19], р["k"], р["recipient_id"],
                      str(р["mailbox_id"])[:30]))
    if not n:
        вых.append("   НЕТ НИ ОДНОГО — сборщик это письмо в базу не записал")

    вых.append("")
    вых.append("--- события reply/reply_auto 04.09 по всем ящикам ---")
    for р in c.execute("SELECT id, %s t, %s k, recipient_id, mailbox_id "
                       "  FROM events WHERE %s IN ('reply','reply_auto') "
                       "   AND substr(%s,1,10)='2026-09-04' ORDER BY %s"
                       % (вр, тп, тп, вр, вр)):
        вых.append("   #%-7s %s %-12s получатель=%-7s ящик=%s"
                   % (р["id"], str(р["t"])[11:19], р["k"], р["recipient_id"],
                      str(р["mailbox_id"])[:34]))

# что скажет классификатор про этот текст
вых.append("")
вых.append("--- классификатор ответа на этом тексте ---")
try:
    from sender.reply_classify import classify_reply                # noqa: E402
    с = classify_reply(ТЕМА, ТЕЛО, {"Subject": ТЕМА, "From": ПОЧТА})
    вых.append("   вид=%s  телефон=%s  %s"
               % (getattr(с, "kind", "?"), getattr(с, "phone", None),
                  str(getattr(с, "__dict__", ""))[:200]))
except Exception as ex:                                         # noqa: BLE001
    вых.append("   не отработал: %s" % str(ex)[:140])

print("\n".join(вых))
print("")
print("=" * 74)
print("=== ПОЧЕМУ ОТВЕТ НЕ СТАЛ ЛИДОМ ===")

# -*- coding: utf-8 -*-
"""Ключ дедупа imap:{uidvalidity}:{uid}:{kind} — не занят ли он уже.

Письмо Медведовского лежит в INBOX ящика i.boyarkin@zernosort.ru под uid=32,
помечено прочитанным, события в базе нет. Сборщик ставит \\Seen ТОЛЬКО после
успешной обработки, а обработка молча выходит, если append_event сказал
«такое уже было». Проверяем: есть ли событие с ключом на этот uid.
"""
import io, os, re, sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.store import Store                                  # noqa: E402

ЯЩИК = "i.boyarkin@zernosort.ru"
store = Store(r"C:\sender\sender.db")
вых = []
with store._lock:
    c = store._conn
    вых.append("--- события ящика %s с ключом на uid 32 ---" % ЯЩИК)
    n = 0
    for р in c.execute(
            "SELECT id, dedup_key, event_type, event_ts, recipient_id, rfc_msgid "
            "  FROM events WHERE mailbox_id=? AND dedup_key LIKE 'imap:%'"
            "   AND dedup_key LIKE '%:32:%' ORDER BY id", (ЯЩИК,)):
        n += 1
        вых.append("   #%-7s %-30s %-12s %s получатель=%s"
                   % (р["id"], р["dedup_key"], р["event_type"],
                      str(р["event_ts"])[:19], р["recipient_id"]))
    if not n:
        вых.append("   нет ни одного")

    вых.append("")
    вых.append("--- какие uidvalidity встречаются у этого ящика ---")
    ув = Counter()
    for р in c.execute("SELECT dedup_key FROM events WHERE mailbox_id=? "
                       "  AND dedup_key LIKE 'imap:%'", (ЯЩИК,)):
        м = re.match(r"imap:(\d+):(\d+):", str(р["dedup_key"]))
        if м:
            ув[м.group(1)] += 1
    for к, в in ув.most_common():
        вых.append("   uidvalidity=%-14s событий: %d" % (к, в))

    вых.append("")
    вых.append("--- последние 12 imap-событий ящика (какие uid брали) ---")
    for р in c.execute(
            "SELECT id, dedup_key, event_type, event_ts FROM events "
            " WHERE mailbox_id=? AND dedup_key LIKE 'imap:%' "
            " ORDER BY id DESC LIMIT 12", (ЯЩИК,)):
        вых.append("   #%-7s %-30s %-12s %s"
                   % (р["id"], р["dedup_key"], р["event_type"],
                      str(р["event_ts"])[:19]))

# лог сборщика за 04.09 целиком (файл может быть больше 3 МБ — читаем весь)
п = r"C:\sender\logs\inbox_poll.log"
вых.append("")
if os.path.exists(п):
    вых.append("лог: %.1f МБ" % (os.path.getsize(п) / 1048576.0))
    инт, боярк = [], []
    with io.open(п, "rb") as f:
        for сыр in f:
            с = сыр.decode("utf-8", errors="replace").rstrip()
            if "2026-09-04" in с:
                инт.append(с)
                if "boyarkin" in с:
                    боярк.append(с)
    вых.append("строк за 2026-09-04: %d, из них про boyarkin: %d"
               % (len(инт), len(боярк)))
    for с in инт[:6]:
        вых.append("   | " + с[:160])
    if len(инт) > 12:
        вых.append("   ...")
    for с in инт[-6:]:
        вых.append("   | " + с[:160])
else:
    вых.append("лога нет: %s" % п)

print("\n".join(вых))
print("")
print("=" * 74)
print("=== КЛЮЧ ДЕДУПА НА UID 32 ===")

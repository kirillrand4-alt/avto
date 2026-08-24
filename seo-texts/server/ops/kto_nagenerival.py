# -*- coding: utf-8 -*-
"""Кто создал 225 карточек за последний час: партия, направление, ящики."""
import sqlite3

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
print("=== PENDING, СОЗДАННЫЕ С 13:00 ===")
for р in c.execute(
        "SELECT cr.campaign_id, COUNT(*) n, MIN(cr.created_at) a, MAX(cr.created_at) b "
        "  FROM confirm_reviews cr WHERE cr.status='pending' "
        "   AND cr.created_at >= '2026-08-24T13' GROUP BY cr.campaign_id"):
    print("  кампания %-4s %5d  с %s по %s"
          % (р["campaign_id"], р["n"], str(р["a"])[11:19], str(р["b"])[11:19]))

print("\n=== ПРИМЕРЫ ===")
for р in c.execute(
        "SELECT cr.id, cr.campaign_id, cr.created_at, cr.subject, r.email, "
        "       m.mailbox_id FROM confirm_reviews cr "
        "  JOIN recipients r ON r.id=cr.recipient_id "
        "  LEFT JOIN messages m ON m.id=cr.message_id "
        " WHERE cr.status='pending' AND cr.created_at >= '2026-08-24T13' "
        " ORDER BY cr.id DESC LIMIT 10"):
    print("  #%-6s камп.%-3s %s %-28s | %s"
          % (р["id"], р["campaign_id"], str(р["created_at"])[11:19],
             str(р["email"])[:28], str(р["subject"])[:44]))

print("\n=== ЖИВЫЕ ПРОЦЕССЫ PYTHON ===")
import subprocess
из = subprocess.run(
    ["powershell", "-NoProfile", "-Command",
     "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
     "Select-Object ProcessId,CreationDate,CommandLine | ConvertTo-Csv "
     "-NoTypeInformation"], capture_output=True, text=True, timeout=120)
for строка in (из.stdout or "").splitlines()[1:]:
    print("  " + строка.strip()[:200])

print("\n=== ЖУРНАЛ ПАРТИИ: ПОСЛЕДНИЕ ЗАПИСИ ПО ВРЕМЕНИ ФАЙЛА ===")
import io, json, os, time
п = r"C:\sender\_ops\gen-partiya-935.jsonl"
print("  обновлён %.1f мин назад" % ((time.time() - os.path.getmtime(п)) / 60.0))
строки = io.open(п, encoding="utf-8").readlines()[-4:]
for с in строки:
    try:
        з = json.loads(с)
        print("  %s | %s | этап=%s ок=%s review_id=%s"
              % (str(з.get("имя"))[:34], з.get("направление"),
                 з.get("этап"), з.get("ок"), з.get("review_id")))
    except Exception:  # noqa: BLE001
        pass

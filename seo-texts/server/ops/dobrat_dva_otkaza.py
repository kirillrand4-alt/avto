# -*- coding: utf-8 -*-
"""Завести карточки двум отказам, потерянным до правки, и сверить панель.

24.08 два живых ответа не дошли до ленты: «Сталь Технологии» (получатель
2998) и «Агрокомбинат Тамбовкрахмал» (7861). Оба классифицированы как
not_interested, а тогдашний код на этом делал голый return — карточка не
заводилась вовсе.

Правка соседней сессии это чинит для НОВЫХ ответов. Задним числом она не
сработает, поэтому эти две карточки заводим руками — тем же путём и с
теми же пометками, что делает код: снippet с меткой [отказ], адрес
ответившего из события, в Битрикс не отправляем.

Сначала сверяем время: если файл правился ПОЗЖЕ старта панели, панель
работает на старом коде и новые отказы всё ещё теряются.

    python zapusk_svoego_skripta.py ops/dobrat_dva_otkaza.py          # проверка
    python zapusk_svoego_skripta.py ops/dobrat_dva_otkaza.py zavesti  # завести
"""
import json
import os
import sqlite3
import subprocess
import sys
import time

sys.path.insert(0, r"C:\sender\sender")
sys.path.insert(0, r"C:\sender")

ЗАВЕСТИ = "zavesti" in sys.argv[1:]
ПОТЕРЯННЫЕ = (2998, 7861)

путь = r"C:\sender\sender\imap_watcher.py"
изменён = os.path.getmtime(путь)
print("imap_watcher.py изменён в %s"
      % time.strftime("%H:%M:%S", time.localtime(изменён)))
try:
    cmd = ('powershell -NoProfile -ExecutionPolicy Bypass -Command '
           '"$p=Get-CimInstance Win32_Service -Filter \\"Name=\'SenderPanel\'\\"; '
           '$q=Get-CimInstance Win32_Process -Filter (\'ProcessId=\'+$p.ProcessId); '
           '[int]($q.CreationDate | Get-Date -UFormat %s)"')
    p = subprocess.run(cmd, shell=True, capture_output=True, timeout=60)
    старт = int(((p.stdout or b"").decode("cp866", "replace").strip() or 0))
    print("панель стартовала в %s"
          % (time.strftime("%H:%M:%S", time.localtime(старт)) if старт else "?"))
    if старт and изменён > старт:
        print("  ВНИМАНИЕ: файл правился ПОСЛЕ старта панели — нужен "
              "Restart-Service SenderPanel -Force, иначе отказы теряются дальше")
    elif старт:
        print("  панель поднята уже с этой правкой — новые отказы попадут в ленту")
except Exception as e:                                         # noqa: BLE001
    print("  время старта панели не снялось:", str(e)[:90])

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row

print("\n=== ЧТО ЗАВОДИМ ===")
работа = []
for пол in ПОТЕРЯННЫЕ:
    ряд = c.execute(
        "SELECT detail_json, event_ts FROM events WHERE recipient_id=? "
        "  AND event_type='reply' ORDER BY id DESC LIMIT 1", (пол,)).fetchone()
    кто = c.execute("SELECT id, email, company_name, inn FROM recipients "
                    "WHERE id=?", (пол,)).fetchone()
    есть = c.execute("SELECT COUNT(*) FROM leads WHERE recipient_id=?",
                     (пол,)).fetchone()[0]
    if not ряд or not кто:
        print("  получатель %s: события или карточки нет — пропускаю" % пол)
        continue
    try:
        д = json.loads(ряд["detail_json"] or "{}")
    except Exception:                                          # noqa: BLE001
        д = {}
    работа.append((пол, кто, д, ряд["event_ts"]))
    print("  %-6s %-30s | лидов уже %s | ответил %s"
          % (пол, str(кто["company_name"] or "")[:30], есть,
             str(д.get("from_addr") or "?")[:34]))
    print("        «%s»" % str(д.get("snippet") or "")[:110].replace("\n", " "))

if not ЗАВЕСТИ:
    print("\nпроверка: ничего не заведено. Для записи добавь аргумент zavesti")
    raise SystemExit(0)

from sender.config import Config                               # noqa: E402
from sender.store import Store                                 # noqa: E402
from sender.leaddesk import LeadDesk                           # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
десk = LeadDesk(store, cfg)

print("\n=== ЗАВОЖУ ===")
for пол, кто, д, когда in работа:
    получатель = store.get_recipient(пол)
    if получатель is None:
        print("  %s: получателя нет в базе" % пол)
        continue
    сниппет = ("[отказ] %s" % str(д.get("snippet") or ""))[:900]
    try:
        ид = десk.push_warm_lead(
            получатель, str(д.get("thread_id") or "dobor-%s" % пол), сниппет,
            otvetil=д.get("from_addr"), v_bitrix=False)
        print("  %-6s %-30s -> лид %s"
              % (пол, str(кто["company_name"] or "")[:30], ид))
    except TypeError:
        ид = десk.push_warm_lead(
            получатель, str(д.get("thread_id") or "dobor-%s" % пол), сниппет)
        print("  %-6s заведён по старой сигнатуре -> лид %s" % (пол, ид))
    except Exception as e:                                     # noqa: BLE001
        print("  %-6s НЕ заведён: %s: %s" % (пол, type(e).__name__, str(e)[:90]))

print("\n=== ЛИДЫ ЗА СЕГОДНЯ ПОСЛЕ ДОБОРА ===")
for р in c.execute(
        "SELECT id, email, recipient_id, status, created_at FROM leads "
        " WHERE substr(created_at,1,10)=date('now') ORDER BY id DESC"):
    print("  #%-4s %-32s пол.%-6s %s"
          % (р["id"], str(р["email"])[:32], р["recipient_id"], р["status"]))

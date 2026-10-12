# -*- coding: utf-8 -*-
"""Перезапуск генерации 500 на новых правилах + спасение брака.

Старый процесс загрузил код ДО правок (лимит «контроль качества», линза
покупателя, сохранение черновика брака) и продолжал бы терять письма.
Останавливаем его и запускаем новый на:
  * остаток партии — кому письма ещё не делали;
  * спасаемый брак — всё, кроме «НЕ ПОКУПАТЕЛЬ» (верный отказ: сами
    производят такое оборудование), но лесопилки спасаем: линза теперь
    знает, что щепа и опил — наш поток.

Запуск: perezapusk_500.py [--primenit]
"""
import io
import json
import re
import sqlite3
import subprocess
import sys
import time

ПРИМЕНИТЬ = "--primenit" in sys.argv
КАМП = 14
ЛЕС = "Лес и деревообработка"

c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
журнал = {}
for р in c.execute("SELECT recipient_id, status, rounds_json FROM ai_letter_log "
                   "WHERE campaign_id=? ORDER BY id", (КАМП,)):
    журнал.setdefault(р["recipient_id"], []).append(dict(р))
ок = {rid for rid, з in журнал.items() if any(x["status"] == "ok" for x in з)}
отрасль = {р["id"]: р["segment"] for р in c.execute(
    "SELECT id, segment FROM recipients WHERE id IN (%s)"
    % ",".join(str(int(x)) for x in журнал) )} if журнал else {}

спасти, верный_отказ = [], []
лесопилок = 0
for rid, записи in журнал.items():
    if rid in ок:
        continue
    текст = json.dumps([x["rounds_json"] for x in записи], ensure_ascii=False)
    # Лесопилку ловим по смыслу отказа, а не по отрасли: отраслевая метка
    # книги у неё бывает другой, а отбита она именно за «нет потока».
    лесопилка = (отрасль.get(rid) == ЛЕС or re.search(
        r"(?i)лесопил|древес|щеп|опил|пиломатер|деревообраб", текст))
    if "НЕ ПОКУПАТЕЛЬ" in текст and not лесопилка:
        верный_отказ.append(rid)
    else:
        спасти.append(rid)
        if "НЕ ПОКУПАТЕЛЬ" in текст:
            лесопилок += 1

список = json.load(io.open(r"C:\sender\_ops\partiya-500.json", encoding="utf-8"))
инн_уже = set()
for р in c.execute("SELECT DISTINCT r.inn FROM ai_letter_log l JOIN recipients r "
                   "ON r.id=l.recipient_id WHERE l.campaign_id=?", (КАМП,)):
    инн_уже.add(р["inn"])
остаток = []
for rid in список:
    if rid in журнал:
        continue
    р = c.execute("SELECT inn FROM recipients WHERE id=?", (rid,)).fetchone()
    if р and р["inn"] in инн_уже:
        continue
    остаток.append(rid)

print("в журнале кампании: %d получателей, готово %d" % (len(журнал), len(ок)))
print("спасаем из брака: %d (из них по отказу «не покупатель» — лесопилки: %d)"
      % (len(спасти), лесопилок))
print("верный отказ «не покупатель», не трогаем: %d" % len(верный_отказ))
print("остаток партии: %d" % len(остаток))
новый = спасти + остаток

pid = io.open(r"C:\sender\_ops\gen500.pid").read().strip()
вывод = subprocess.run(["tasklist", "/FI", "PID eq %s" % pid],
                       capture_output=True, text=True).stdout
print("старый работник %s жив: %s" % (pid, pid in вывод))
if not ПРИМЕНИТЬ:
    print("=== ПЕРЕЗАПУСК: СУХОЙ ПРОГОН, в новый прогон %d ===" % len(новый))
    sys.exit(0)

if pid in вывод:
    subprocess.run(["taskkill", "/PID", pid, "/T", "/F"], capture_output=True)
    time.sleep(3)
путь = r"C:\sender\_ops\partiya-500-dop.json"
json.dump(новый, io.open(путь, "w", encoding="utf-8"))
лог = io.open(r"C:\sender\_ops\gen500.log", "a", encoding="utf-8")
лог.write("\n==== ПЕРЕЗАПУСК %s: спасаем %d, остаток %d ====\n"
          % (time.strftime("%H:%M:%S"), len(спасти), len(остаток)))
лог.flush()
п = subprocess.Popen(
    [sys.executable, r"C:\sender\server\ops\generaciya_500.py", str(КАМП), путь],
    cwd=r"C:\sender", stdout=лог, stderr=лог,
    creationflags=0x00000008 | 0x00000200)
io.open(r"C:\sender\_ops\gen500.pid", "w").write(str(п.pid))
time.sleep(8)
print("новый работник pid %d, жив: %s" % (п.pid, п.poll() is None))
print("=== ПЕРЕЗАПУСК: ПРИМЕНЁН, в прогоне %d ===" % len(новый))

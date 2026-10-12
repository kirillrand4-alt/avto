# -*- coding: utf-8 -*-
"""Обновить в стоп-листе ИНН с активными сделками: снять старые, залить новые.

Владелец 12.10 прислал выгрузку MEYER-7 и велел заменить, а не дополнить:
прежние записи «идёт сделка» снять, новые 3179 залить. Записи от баунсов
не трогаем — их в стоп-листе по ИНН нет вовсе, баунсы живут в scope=email.

Не трогаем и записи про конкурентов и неподходящий профиль: это причины
сильнее и дольше сделки. Если ИНН из файла уже закрыт как конкурент, его
пометку НЕ понижаем до «идёт сделка».

Снятое пишем на сервер строками JSON с fsync — вернуть можно будет
одной командой.

argv: --primenit чтобы записать (без него только показать).
"""
import io
import json
import os
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
from sender.store import Store                                  # noqa: E402

СПИСОК = r"C:\sender\server\ops\inny_sdelki_2026-10-12.json"
ПРИМЕНИТЬ = "--primenit" in sys.argv
ПРИЧИНА = "deal_in_progress"
ИСТОЧНИК = "активная сделка MEYER-7, выгрузка 12.10"
ОТБОР = ("(reason = 'deal_in_progress' "
         " OR (reason = 'manual' AND COALESCE(source,'') LIKE '%сделка%'))")

новые = json.load(io.open(СПИСОК, encoding="utf-8"))["все"]
новые = [str(x) for x in новые if str(x).isdigit() and len(str(x)) in (10, 12)]
новые = list(dict.fromkeys(новые))
print("ИНН в выгрузке: %d" % len(новые))

store = Store(r"C:\sender\sender.db")
with store._lock:
    c = store._conn
    снять = c.execute(
        "SELECT id, scope, value, reason, source, created_at, expires_at "
        "  FROM suppression WHERE scope='inn' AND %s ORDER BY id" % ОТБОР
    ).fetchall()
    прочие = {str(р["value"]).strip() for р in c.execute(
        "SELECT value FROM suppression WHERE scope='inn' AND NOT %s" % ОТБОР)}
    всего_до = c.execute(
        "SELECT COUNT(*) FROM suppression WHERE scope='inn'").fetchone()[0]

уже_не_трогаем = [и for и in новые if и in прочие]
к_заливке = [и for и in новые if и not in прочие]
print("")
print("--- что будет сделано ---")
print("   снять записей «идёт сделка»:        %6d" % len(снять))
print("   залить новых ИНН:                   %6d" % len(к_заливке))
print("   пропустить (закрыты другой причиной): %4d" % len(уже_не_трогаем))
print("   записей scope=inn сейчас:           %6d" % всего_до)
print("   станет:                             %6d"
      % (всего_до - len(снять) + len(к_заливке)))

if not ПРИМЕНИТЬ:
    print("")
    print("=" * 74)
    print("=== ПОКАЗ БЕЗ ЗАПИСИ (нужен --primenit) ===")
    raise SystemExit(0)

# 1. бэкап снимаемого — на сервер, с fsync
папка = r"C:\sender\_ops"
os.makedirs(папка, exist_ok=True)
бэкап = os.path.join(папка, "stop-inn-sdelki-snyato-%d.jsonl" % int(time.time()))
with io.open(бэкап, "w", encoding="utf-8") as f:
    for р in снять:
        f.write(json.dumps({k: р[k] for k in р.keys()}, ensure_ascii=False) + "\n")
    f.flush()
    os.fsync(f.fileno())
print("")
print("   бэкап снятого: %s (%d строк)" % (бэкап, len(снять)))

сейчас = datetime.now(timezone.utc).isoformat()
with store._lock, store.transaction() as conn:
    conn.executemany(
        "INSERT INTO consent_log (recipient_id, email, action, basis, source, "
        "  campaign_id, detail_json, created_at) VALUES (?,?,?,?,?,?,?,?)",
        [(None, str(р["value"]).strip().lower(), "suppression_removed",
          "operator_decision", "remove:обновление активных сделок 12.10", None,
          json.dumps({"reason": "замена списка активных сделок",
                      "scope": р["scope"], "value": р["value"],
                      "was_reason": р["reason"], "was_source": р["source"]},
                     ensure_ascii=False), сейчас) for р in снять])
    conn.executemany("DELETE FROM suppression WHERE id=?",
                     [(р["id"],) for р in снять])
    conn.executemany(
        "INSERT INTO suppression (scope, value, reason, source, campaign_id, "
        "  created_at, expires_at) VALUES ('inn',?,?,?,NULL,?,NULL) "
        " ON CONFLICT(scope, value) DO UPDATE SET reason=excluded.reason, "
        "  source=excluded.source, created_at=excluded.created_at",
        [(и, ПРИЧИНА, ИСТОЧНИК, сейчас) for и in к_заливке])

with store._lock:
    c = store._conn
    всего_после = c.execute(
        "SELECT COUNT(*) FROM suppression WHERE scope='inn'").fetchone()[0]
    print("")
    print("--- стало по причинам ---")
    for р in c.execute("SELECT COALESCE(reason,'(пусто)') r, COUNT(*) n "
                       "  FROM suppression WHERE scope='inn' "
                       " GROUP BY 1 ORDER BY 2 DESC"):
        print("   %-24s %6d" % (str(р["r"])[:24], р["n"]))

print("")
print("=" * 74)
print("=== АКТИВНЫЕ СДЕЛКИ В СТОП-ЛИСТЕ ОБНОВЛЕНЫ ===")
print("   было записей scope=inn: %d, стало: %d" % (всего_до, всего_после))
print("   снято: %d, залито: %d, пропущено: %d"
      % (len(снять), len(к_заливке), len(уже_не_трогаем)))
print("   бэкап: %s" % бэкап)

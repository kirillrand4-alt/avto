# -*- coding: utf-8 -*-
"""Убрать из партии компании, чей адрес не подтверждён живым.

Владелец 17.08: «неясно, нет ящика, нет MX и отказ пробе - сними», и на
уточнение «сами компании». То есть в партии остаются только те, чей ящик
сервер подтвердил: вердикты «есть» и «принимает всё».

Группа у получателя хранится в двух местах сразу - в поле segment и в
списке extra_json.gruppy. Убирать надо из обоих, иначе компания останется
в отборе через второе.

Обратимо: каждая снятая компания пишется строкой в журнал с её вердиктом,
и вернуть её - это дописать группу назад. Отдельно снимаем письма таких
компаний из очереди: адрес не подтверждён, слать по нему нечего.

Стоп-лист НЕ трогаем. «Неясно» и «отказ пробе» - это утверждение про нашу
пробу, а не про адрес; хоронить по ним контакт нельзя, они просто выходят
из этой партии.

Сухой прогон; писать - argv[1] == "primenit".
"""
import io
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
from sender.config import Config                               # noqa: E402
from sender.store import Store                                 # noqa: E402

ПРИМЕНИТЬ = len(sys.argv) > 1 and sys.argv[1] == "primenit"
ГРУППА = "Партия 935"
ЖУРНАЛ = r"C:\sender\_ops\partiya-snyatye-nezhivye.jsonl"
ЖИВЫЕ = ("есть", "принимает всё")
ПРИЧИНА = "адрес не подтверждён пробой: {}"

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

with store._lock:
    вердикт = {e: (v, a) for e, v, a in store._conn.execute(
        "SELECT lower(email), verdict, COALESCE(answer,'') FROM addr_probe")}

группы = store.recipient_groups().get("по_id") or {}
в_группе = sorted(rid for rid, gr in группы.items() if ГРУППА in gr)
print(f"в группе {len(в_группе)} строк")

снять, счёт = [], Counter()
for rid in в_группе:
    rec = store.get_recipient(rid)
    if not rec:
        continue
    email = str(getattr(rec, "email", "") or "").strip().lower()
    в, ответ = вердикт.get(email, ("вердикта нет", ""))
    if в in ЖИВЫЕ:
        счёт[f"оставляем: {в}"] += 1
        continue
    счёт[f"СНИМАЕМ: {в}"] += 1
    снять.append((rid, rec, email, в, ответ))

for k, n in счёт.most_common():
    print(f"  {k:<28} {n}")
print(f"\nк снятию компаний: {len(снять)}")

# письма этих компаний
инн_снятых = {"".join(c for c in str(getattr(r, "inn", "") or "")
                     if c.isdigit()) for _, r, _, _, _ in снять}
письма = []
for ст in ("pending", "approved"):
    for r in (store.confirm_list(status=ст, limit=100000) or []):
        if str(r.get("inn") or "") in инн_снятых:
            письма.append(r)
print(f"их писем в очереди: {len(письма)}")

if not ПРИМЕНИТЬ:
    print("\nсухой прогон: ничего не менял")
    raise SystemExit(0)

сейчас = datetime.now(timezone.utc).isoformat()
снято = 0
with io.open(ЖУРНАЛ, "a", encoding="utf-8") as ж:
    for rid, rec, email, в, ответ in снять:
        with store._lock:
            row = store._conn.execute(
                "SELECT COALESCE(segment,''), COALESCE(extra_json,'') "
                "FROM recipients WHERE id=?", (rid,)).fetchone()
        сегмент, сырое = (row or ("", ""))
        новый_сегмент = "" if str(сегмент).strip() == ГРУППА else сегмент
        try:
            extra = json.loads(сырое) if сырое else {}
        except Exception:                                      # noqa: BLE001
            extra = {}
        было_групп = list(extra.get("gruppy") or [])
        extra["gruppy"] = [g for g in было_групп if str(g).strip() != ГРУППА]
        with store.transaction() as conn:
            conn.execute(
                "UPDATE recipients SET segment=?, extra_json=?, updated_at=? "
                "WHERE id=?",
                (новый_сегмент, json.dumps(extra, ensure_ascii=False),
                 сейчас, rid))
        ж.write(json.dumps({
            "recipient_id": rid, "email": email, "вердикт": в,
            "ответ": str(ответ)[:150],
            "инн": "".join(c for c in str(getattr(rec, "inn", "") or "")
                           if c.isdigit()),
            "имя": str(getattr(rec, "company_name", "") or "")[:70],
            "было_segment": сегмент, "было_gruppy": было_групп,
            "ts": сейчас}, ensure_ascii=False) + "\n")
        снято += 1
    ж.flush()
    os.fsync(ж.fileno())
print(f"снято компаний из партии: {снято}")

снято_писем = Counter()
for r in письма:
    rid = int(r["id"])
    почему = ПРИЧИНА.format(
        вердикт.get(str(r.get("email") or "").lower(), ("?",))[0])
    if str(r.get("status")) == "pending":
        ок = store.confirm_decide(rid, status="skipped",
                                  decided_by="проба адресов", reason=почему)
        снято_писем["pending снято" if ок else "pending не снялось"] += 1
        continue
    with store.transaction() as conn:
        conn.execute(
            "UPDATE confirm_reviews SET status='skipped', reason=?, "
            "decided_by=?, decided_at=?, updated_at=? WHERE id=?",
            (почему, "проба адресов", сейчас, сейчас, rid))
        mid = r.get("message_id")
        if mid is not None:
            c2 = conn.execute(
                "UPDATE messages SET status='skipped', last_error=?, "
                "updated_at=? WHERE id=? AND status NOT IN "
                "('sent','skipped','failed')",
                (f"confirm:skipped:{почему}", сейчас, int(mid)))
            снято_писем["approved снято" if c2.rowcount
                        else "approved снят, письмо уже ОТПРАВЛЕНО"] += 1
        else:
            снято_писем["approved снято (без message_id)"] += 1
for k, n in снято_писем.most_common():
    print(f"  {k:<38} {n}")
print(f"журнал снятия: {ЖУРНАЛ}")

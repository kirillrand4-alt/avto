# -*- coding: utf-8 -*-
"""Кто на самом деле назначает направление письма: замер, а не рассуждение.

Вопрос владельца по письму #1280 (судостроительный завод получил письмо
Meyer): «почему направление не из карточки бралось?». В панели у письма
стоит letter_division='meyer', причина 'explicit', а в карточке
division='kc+meyer'.

Цепочка в коде такая. ai_quota._request сначала смотрит карту
segment_division (сегмент получателя -> направление), и ТОЛЬКО если она
молчит, берёт направление карточки. Дальше ai_letter.target_division видит
уже готовое поле и отвечает 'explicit' - то есть 'explicit' здесь означает
«решил конвейер до генерации», а не «решил оператор руками».

Значит виноват один из двух: либо сегмент получателя отображён в meyer,
либо карточка составная ('kc+meyer' даёт None и не решает ничего).
Печатаем оба входа для конкретных писем и по всей группе разом.

    python zapusk_svoego_skripta.py ops/partiya_otkuda_napravlenie.py 1280 1285
"""
import io
import json
import os
import sys
import urllib.request
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.ai_letter import norm_division                    # noqa: E402
from sender.ai_quota import build_ai_quota                    # noqa: E402
from sender.config import Config                              # noqa: E402
from sender.store import Store                                # noqa: E402

ГРУППА = "Партия 935"
ИМЯ = "OTKUDA-NAPRAVLENIE.md"
ОТЧЁТ = r"C:\sender\_ops" + "\\" + ИМЯ
ОТ = int(sys.argv[1]) if len(sys.argv) > 1 else 1280
ДО = int(sys.argv[2]) if len(sys.argv) > 2 else 1285

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)

С = []


def п(s=""):
    С.append(s)


карта = q._segment_division()
п("# Откуда берётся направление письма")
п()
п("## Карта segment_division (сегмент -> направление)")
п()
п("Она СИЛЬНЕЕ карточки: партия это осознанное решение оператора, "
  "о чём пишем.")
п()
for k, v in sorted(карта.items()):
    п(f"- `{k}` -> **{v}**")
if not карта:
    п("- карта пуста")
п()

# --- конкретные письма ---------------------------------------------------- #
п(f"## Письма #{ОТ}-#{ДО}: два входа решения")
п()
with store._lock:
    строки = list(store._conn.execute(
        "SELECT id, campaign_id, email, panel_json FROM confirm_reviews "
        "WHERE id BETWEEN ? AND ? ORDER BY id", (ОТ, ДО)))
for rid, camp, email, pj in строки:
    try:
        p = json.loads(pj or "{}")
    except Exception:                                          # noqa: BLE001
        p = {}
    comp = p.get("company") if isinstance(p.get("company"), dict) else {}
    r = store.get_recipient_by_email(email) if hasattr(
        store, "get_recipient_by_email") else None
    if r is None:
        with store._lock:
            row = store._conn.execute(
                "SELECT id FROM recipients WHERE lower(email)=?",
                (str(email or "").lower(),)).fetchone()
        r = store.get_recipient(row[0]) if row else None
    сегмент = str(getattr(r, "segment", "") or "") if r else "?"
    группы = []
    if r is not None:
        try:
            группы = (json.loads(getattr(r, "extra_json", "") or "{}")
                      .get("gruppy") or [])
        except Exception:                                      # noqa: BLE001
            группы = []
    карточное = str(comp.get("division") or "")
    из_карты = карта.get(сегмент.lower(), "")
    п(f"### #{rid} камп.{camp} {email}")
    п(f"- сегмент получателя: `{сегмент}` -> карта даёт "
      f"**{из_карты or 'ничего'}**")
    п(f"- группы получателя: {группы or 'нет'}")
    п(f"- направление карточки: `{карточное}` -> norm_division даёт "
      f"**{norm_division(карточное) or 'ничего (составное)'}**")
    п(f"- письму досталось: **{p.get('letter_division')}** "
      f"(причина {p.get('letter_division_reason')})")
    решил = ("карта сегментов" if из_карты else
             "карточка" if norm_division(карточное) else
             "цепочка приоритетов (новость/потребности/профиль/запасной kc)")
    п(f"- **решил: {решил}**")
    п()

# --- по всей группе ------------------------------------------------------- #
п("## По всей группе «Партия 935»")
п()
группы_по_id = store.recipient_groups().get("по_id") or {}
в_группе = sorted(rid for rid, gr in группы_по_id.items() if ГРУППА in gr)
счёт_сегмент, счёт_карта = Counter(), Counter()
for rid in в_группе:
    r = store.get_recipient(rid)
    if not r:
        continue
    сег = str(getattr(r, "segment", "") or "").strip()
    счёт_сегмент[сег or "(пусто)"] += 1
    счёт_карта[карта.get(сег.lower(), "(карта молчит)")] += 1
п(f"строк в группе: **{len(в_группе)}**")
п()
п("Сегменты получателей:")
п()
for k, n in счёт_сегмент.most_common(20):
    п(f"- `{k}` — {n}")
п()
п("Что даёт карта segment_division на этих сегментах:")
п()
for k, n in счёт_карта.most_common():
    п(f"- **{k}** — {n}")
п()

текст = "\n".join(С) + "\n"
try:
    with io.open(ОТЧЁТ, "w", encoding="utf-8") as f:
        f.write(текст)
    rq = urllib.request.Request(
        os.environ["DROP_URL"].rstrip("/") + "/" + ИМЯ,
        data=текст.encode("utf-8"), method="PUT",
        headers={"X-Drop-Token": os.environ["DROP_TOKEN"]})
    with urllib.request.urlopen(rq, timeout=120) as rp:
        rp.read()
    print(f"отчёт на дропе: {ИМЯ}")
except Exception as ex:                                        # noqa: BLE001
    print("отчёт на дроп не уехал:", str(ex)[:200])

print(f"карта segment_division: {карта}")
print(f"строк в группе: {len(в_группе)}")
for k, n in счёт_карта.most_common():
    print(f"  {k:<20} {n}")

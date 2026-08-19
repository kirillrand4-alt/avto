# -*- coding: utf-8 -*-
"""Соннетовские письма против сегодняшних отправленных: цена и текст.

Владелец: «замерь качество писем на соннет по 10 штук, против отправленных
сегодня... покажи их мне потом, без рассуждения с кэшем, замерь сколько
стоило письмо».

Цену берём из журнала генерации (он пишет её на каждое письмо с разбивкой
на письмо и проверки), а не пересчитываем на глаз. Тексты печатаем целиком:
судить качество по обрезку нельзя.
"""
import io
import json
import os
import re
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                       # noqa: E402
from sender.store import Store                                         # noqa: E402

ЖУРНАЛ = r"C:\sender\_ops\gen-partiya-935.jsonl"
СКОЛЬКО = int(next((a for a in sys.argv[1:] if a.isdigit()), "10"))
# СРЕЗ. Раннер отдаёт только ХВОСТ вывода, и десять писем в него не лезут:
# печатаем по кускам — «срез=1-3».
СРЕЗ = None
for _а in sys.argv[1:]:
    if _а.startswith("срез="):
        _a, _b = _а.split("=", 1)[1].split("-")
        СРЕЗ = (int(_a) - 1, int(_b))


def _т(s, n=None):
    s = re.sub(r"<br\s*/?>", "\n", str(s or ""), flags=re.I)
    s = re.sub(r"</p>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    s = re.sub(r"&nbsp;?", " ", s)
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n\n", s).strip()
    return s[:n] if n else s


# ---- 1. соннетовские письма из журнала ---------------------------------- #
соннет = []
if os.path.exists(ЖУРНАЛ):
    for s in io.open(ЖУРНАЛ, encoding="utf-8"):
        try:
            z = json.loads(s)
        except Exception:                                              # noqa: BLE001
            continue
        if "sonnet" in str(z.get("модель") or "") and (
                z.get("тело") or z.get("тело_брака")):
            соннет.append(z)
соннет = соннет[-СКОЛЬКО:]
if СРЕЗ:
    соннет = соннет[СРЕЗ[0]:СРЕЗ[1]]
print(f"== писем на соннете в журнале: {len(соннет)} ==")

if соннет:
    ц = Counter()
    for z in соннет:
        ц["цена"] += float(z.get("цена_$") or 0)
        ц["письмо"] += float(z.get("цена_письма_$") or 0)
        ц["проверки"] += float(z.get("цена_проверок_$") or 0)
        ц["зап"] += int(z.get("вход_кэш_запись") or 0)
        ц["чт"] += int(z.get("вход_кэш_чтение") or 0)
        ц["вызовов"] += int(z.get("вызовов") or 0)
        ц["сек"] += int(z.get("сек") or 0)
    n = len(соннет)
    print(f"  цена одного письма: ${ц['цена']/n:.4f}  "
          f"(письмо ${ц['письмо']/n:.4f} + проверки ${ц['проверки']/n:.4f})")
    print(f"  кэш: записано {ц['зап']/n:,.0f}, прочитано {ц['чт']/n:,.0f} "
          f"на письмо  (чтение/запись {ц['чт']/max(1,ц['зап']):.2f})")
    print(f"  вызовов на письмо {ц['вызовов']/n:.1f} | "
          f"секунд {ц['сек']/n:.0f}")

# ---- 2. опус за сегодня, для сравнения ---------------------------------- #
опус = []
if os.path.exists(ЖУРНАЛ):
    for s in io.open(ЖУРНАЛ, encoding="utf-8"):
        try:
            z = json.loads(s)
        except Exception:                                              # noqa: BLE001
            continue
        if "opus" in str(z.get("модель") or "") and z.get("тело") and z.get(
                "цена_$"):
            опус.append(z)
опус = опус[-200:]
if опус:
    ц2 = Counter()
    for z in опус:
        ц2["цена"] += float(z.get("цена_$") or 0)
        ц2["письмо"] += float(z.get("цена_письма_$") or 0)
        ц2["проверки"] += float(z.get("цена_проверок_$") or 0)
        ц2["зап"] += int(z.get("вход_кэш_запись") or 0)
        ц2["чт"] += int(z.get("вход_кэш_чтение") or 0)
        ц2["вызовов"] += int(z.get("вызовов") or 0)
    m = len(опус)
    print(f"\n== опус, последние {m} писем ==")
    print(f"  цена одного письма: ${ц2['цена']/m:.4f}  "
          f"(письмо ${ц2['письмо']/m:.4f} + проверки ${ц2['проверки']/m:.4f})")
    print(f"  кэш: записано {ц2['зап']/m:,.0f}, прочитано {ц2['чт']/m:,.0f} "
          f"на письмо")
    if соннет:
        раз = (ц2["цена"]/m) / max(1e-9, ц["цена"]/n)
        print(f"\n  СОННЕТ ДЕШЕВЛЕ В {раз:.1f} РАЗА")

# ---- 3. тексты ----------------------------------------------------------- #
print("\n" + "=" * 78)
print("ПИСЬМА НА СОННЕТЕ")
print("=" * 78)
for i, z in enumerate(соннет, 1):
    годно = "ГОДНО" if z.get("тело") else "БРАК"
    брак = z.get("брак")
    print(f"\n--- {i}. [{годно}] {z.get('имя')} (ИНН {z.get('inn')}) "
          f"${z.get('цена_$')} ---")
    if брак:
        причина = брак if isinstance(брак, str) else "; ".join(map(str, брак))
        print(f"ПРИЧИНА БРАКА: {причина[:220]}")
    print(f"ТЕМА: {z.get('тема') or z.get('тема_брака')}")
    print(_т(z.get("тело") or z.get("тело_брака")))

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
print("\n" + "=" * 78)
print("ОТПРАВЛЕННЫЕ СЕГОДНЯ (опус) — для сравнения")
print("=" * 78)
with store._lock:
    ушли = store._conn.execute(
        "SELECT m.id, m.subject, m.body_rendered, r.company_name "
        "FROM messages m LEFT JOIN recipients r ON r.id=m.recipient_id "
        "WHERE m.status='sent' AND date(m.sent_at)=date('now') "
        "AND m.campaign_id=10 ORDER BY m.sent_at DESC LIMIT 3").fetchall()
for i, r in enumerate(ушли, 1):
    print(f"\n--- {i}. {r['company_name']} (письмо #{r['id']}) ---")
    print(f"ТЕМА: {r['subject']}")
    print(_т(r["body_rendered"]))

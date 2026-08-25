# -*- coding: utf-8 -*-
"""Линза направления пачками: один префикс на восемь писем.

vf_prompt принимает СПИСОК писем, а я гонял по одному — отсюда $0.019 за
проверку вместо $0.003. Статический префикс линзы весит 8 тысяч токенов и
оплачивается на каждом вызове, поэтому восемь писем в одном вызове дают
почти восьмикратную экономию.

Проверяем письма, созданные СЕГОДНЯ (старые прошли верификатор в своём
конвейере). Разбор ответа отказывающий по умолчанию: не поняли ответ —
письмо не годно.

Порядок: сначала --проба (одна пачка с заведомо плохим письмом, чтобы
убедиться, что разбор ловит отказ), потом сухой прогон, потом --снять.
"""
import json
import re
import sqlite3
import sys
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, r"C:\sender\sender")
sys.path.insert(0, r"C:\sender")

import gen_provider                                            # noqa: E402
from sender.ai_letter import vf_prompt                        # noqa: E402

МОДЕЛЬ = "claude-sonnet-4-6"
ПАЧКА = 8
ПОТОКОВ = 6
ПРОБА = "--проба" in sys.argv
СНЯТЬ = "--снять" in sys.argv

c = sqlite3.connect(r"C:\sender\sender.db", check_same_thread=False)
c.row_factory = sqlite3.Row
замок = threading.Lock()
итог = Counter()
расход = [0.0]
плохие = []


def _вердикты(текст, сколько, кц=False):
    """Ответ линзы -> {idx: (годно, почему)}. Не разобрали — все НЕ годны.

    Для КЦ выбрасываем претензию по правилу 2 к строке отказа: линза несёт
    редакцию 14.08 (запрет всем), а владелец 17.08 уточнил, что решение
    касалось только Meyer — zashit_kontsovku для КЦ строку ТРЕБУЕТ, и по
    замеру она стоит в 88% писем, на которые пришёл живой ответ. Без этой
    поправки линза бракует 708 писем из 1269 за то, что канон предписывает.
    """
    м = re.search(r"\{.*\}", текст or "", re.S)
    if not м:
        return {i: (False, "линза ответила не JSON") for i in range(сколько)}
    try:
        д = json.loads(м.group(0))
    except Exception:  # noqa: BLE001
        return {i: (False, "ответ линзы не разобрался") for i in range(сколько)}
    спис = д.get("verdicts") or д.get("letters") or д.get("results") or []
    если = {}
    for з in (спис if isinstance(спис, list) else []):
        try:
            i = int(з.get("idx"))
        except Exception:  # noqa: BLE001
            continue
        беды = з.get("problems") or з.get("why") or з.get("reason") or ""
        беды = беды if isinstance(беды, list) else ([беды] if беды else [])
        if кц:
            беды = [b for b in беды
                    if not (re.search(r"(?i)правил\w*\s*2", str(b))
                            and re.search(r"(?i)отказ", str(b)))]
        остались = "; ".join(str(x) for x in беды)
        если[i] = (bool(з.get("ok")) or not остались, остались[:170])
    # чего линза не назвала — не годно: молчание не одобрение
    return {i: если.get(i, (False, "линза не дала вердикт по этому письму"))
            for i in range(сколько)}


def пачка(аргумент):
    номер, строки, напр = аргумент
    слоты = [(i, str(р["subject"]), str(р["body"]))
             for i, р in enumerate(строки)]
    try:
        п = vf_prompt(слоты, напр)
        сис, тело = gen_provider.razrezat_promt(п)
        m = gen_provider._raw_stream([{"role": "user", "content": тело}],
                                     МОДЕЛЬ, 2000, thinking=False,
                                     effort="low", system=сис)
        т = "".join(b.text for b in m.content
                    if getattr(b, "type", "") == "text")
        u = getattr(m, "usage", None)
        ц = ((int(getattr(u, "input_tokens", 0) or 0)
              + 1.25 * int(getattr(u, "cache_creation_input_tokens", 0) or 0)
              + 0.1 * int(getattr(u, "cache_read_input_tokens", 0) or 0)) / 1e6 * 3.0
             + int(getattr(u, "output_tokens", 0) or 0) / 1e6 * 15.0)
    except Exception as e:  # noqa: BLE001
        with замок:
            итог["пачка упала"] += len(строки)
        return
    в = _вердикты(т, len(строки), кц=(напр == "kc"))
    with замок:
        расход[0] += ц
        for i, р in enumerate(строки):
            ок, почему = в[i]
            if ок:
                итог["годно"] += 1
            else:
                итог["брак"] += 1
                плохие.append((р["id"], str(р["company_name"] or "")[:34],
                               напр, почему))
    if ПРОБА:
        print("  ответ линзы целиком:\n%s" % т[:900])


# ---------- проба разбора на заведомо плохом письме ------------------------ #
if ПРОБА:
    р = c.execute(
        "SELECT cr.id, cr.subject, cr.body, r.company_name "
        "  FROM confirm_reviews cr JOIN recipients r ON r.id=cr.recipient_id "
        " WHERE r.company_name LIKE '%АЛМАЗ%' ORDER BY cr.id DESC LIMIT 1").fetchone()
    if not р:
        print("нет письма для пробы")
        raise SystemExit(1)
    print("проба на: %s (#%s)" % (р["company_name"], р["id"]))
    пачка((0, [р], "meyer"))
    print("\nитог пробы: %s" % dict(итог))
    print("плохие: %s" % [(x[0], x[3][:80]) for x in плохие])
    print("цена одной пачки из 1 письма: $%.4f" % расход[0])
    raise SystemExit(0)

# ---------- боевой проход по сегодняшним ---------------------------------- #
строки = c.execute(
    "SELECT cr.id, cr.subject, cr.body, r.company_name, m.campaign_id "
    "  FROM confirm_reviews cr JOIN recipients r ON r.id=cr.recipient_id "
    "  LEFT JOIN messages m ON m.id=cr.message_id "
    # ТОЛЬКО ТО, ЧТО ЕЩЁ МОЖЕТ УЙТИ. Карточек с текстом 3877, но у
    # большинства письмо давно отправлено или снято — проверять их значит
    # платить за историю.
    " WHERE m.status IN ('pending_review','scheduled') "
    "   AND COALESCE(cr.body,'')<>'' ORDER BY cr.id").fetchall()
print("писем к проверке: %d" % len(строки))
по_напр = {"kc": [], "meyer": []}
for р in строки:
    по_напр["meyer" if р["campaign_id"] == 11 else "kc"].append(р)
задания = []
for напр, спис in по_напр.items():
    print("  %s: %d" % (напр, len(спис)))
    for i in range(0, len(спис), ПАЧКА):
        задания.append((len(задания), спис[i:i + ПАЧКА], напр))
print("пачек: %d" % len(задания))

with ThreadPoolExecutor(max_workers=ПОТОКОВ) as пул:
    list(пул.map(пачка, задания))

print("\n=== ИТОГ ===")
for к, н in итог.most_common():
    print("  %-16s %d" % (к, н))
print("  потрачено: $%.3f (%.4f за письмо)"
      % (расход[0], расход[0] / max(1, итог["годно"] + итог["брак"])))
причины = Counter(x[3].split(":")[0][:46] for x in плохие)
print("\n  за что бракует:")
for к, н in причины.most_common(10):
    print("    %-48s %d" % (к, н))

if not СНЯТЬ:
    print("\nсухой прогон. Снять — --снять")
    raise SystemExit(0)

sys.path.insert(0, r"C:\sender")
from sender.config import Config                              # noqa: E402
from sender.store import Store                                # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
снято = 0
for rid, имя, напр, почему in плохие:
    try:
        if store.confirm_decide(rid, status="skipped",
                                decided_by="линза направления (пачкой)",
                                reason=("линза: " + почему)[:180]):
            снято += 1
        else:
            стр = store._conn.execute(
                "SELECT message_id FROM confirm_reviews WHERE id=?",
                (rid,)).fetchone()
            if стр and стр[0] and store.mark_skipped_if_not_terminal(
                    int(стр[0]), "линза: " + почему[:100]):
                снято += 1
    except Exception as e:  # noqa: BLE001
        print("  #%s: %s" % (rid, str(e)[:90]))
print("\nснято: %d" % снято)

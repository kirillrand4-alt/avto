# -*- coding: utf-8 -*-
"""Прогнать линзу направления по письмам дешёвой партии, уже лежащим в очереди.

Минус-класс и гейт адресата по ним прошли (снято 16). Линза направления —
нет, а именно она ловит смысловую чепуху вроде рентген-инспекции для
переработчика медотходов: формально письмо безупречно, по сути — не тому.

Без аргумента сухой прогон, снимает при --снять.
"""
import io
import json
import re
import sys
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, r"C:\sender\sender")
sys.path.insert(0, r"C:\sender")

import gen_provider                                            # noqa: E402
from sender.ai_letter import vf_prompt                        # noqa: E402
from sender.config import Config                              # noqa: E402
from sender.store import Store                                # noqa: E402

МОДЕЛЬ = "claude-sonnet-4-6"
СНЯТЬ = "--снять" in sys.argv or "--snyat" in sys.argv
ОТЧЁТ = r"C:\sender\_ops\deshevaya-partiya.jsonl"

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

карточки = []
for с in io.open(ОТЧЁТ, encoding="utf-8"):
    с = с.strip()
    if not с:
        continue
    try:
        з = json.loads(с)
    except Exception:  # noqa: BLE001
        continue
    if not (з.get("ок") and з.get("review_id")):
        continue
    стр = store._conn.execute(
        "SELECT status FROM confirm_reviews WHERE id=?",
        (int(з["review_id"]),)).fetchone()
    if стр and str(стр[0]) in ("pending", "approved"):
        карточки.append(з)
print("карточек дешёвой партии живых в очереди: %d" % len(карточки))

def _вердикт_линзы(текст):
    """Ответ vf_prompt -> (годно?, почему). Не разобрали — считаем НЕ годным.

    Линза отвечает {"verdicts":[{"idx":0,"ok":false,"problems":[...]}]}, а
    первая редакция разбора искала ключи letters/results, не находила их,
    откатывалась на весь словарь и по умолчанию ставила ok=True. Проверка
    молча отвечала «всё хорошо» на всё: прогон по 325 письмам дал ноль
    отказов, включая письмо, которое линза честно бракует. Поэтому теперь
    ключ верный, а неразобранный ответ — отказ, а не пропуск.
    """
    м = re.search(r"\{.*\}", текст or "", re.S)
    if not м:
        return False, "линза ответила не JSON"
    try:
        д = json.loads(м.group(0))
    except Exception:  # noqa: BLE001
        return False, "ответ линзы не разобрался"
    спис = (д.get("verdicts") or д.get("letters") or д.get("results") or [])
    з = спис[0] if isinstance(спис, list) and спис else д
    if "ok" not in з:
        return False, "в ответе линзы нет поля ok"
    беды = з.get("problems") or з.get("why") or з.get("reason") or ""
    if isinstance(беды, list):
        беды = "; ".join(str(x) for x in беды)
    return bool(з.get("ok")), str(беды)[:180]


замок = threading.Lock()
итог = Counter()
плохие = []
расход = [0.0]


def проверить(з):
    try:
        п = vf_prompt([(0, str(з.get("тема")), str(з.get("тело")))],
                      str(з.get("направление") or "kc"))
        сис, тело = gen_provider.razrezat_promt(п)
        m = gen_provider._raw_stream([{"role": "user", "content": тело}],
                                     МОДЕЛЬ, 700, thinking=False,
                                     effort="low", system=сис)
        т = "".join(b.text for b in m.content
                    if getattr(b, "type", "") == "text")
        u = getattr(m, "usage", None)
        ц = ((int(getattr(u, "input_tokens", 0) or 0)
              + 1.25 * int(getattr(u, "cache_creation_input_tokens", 0) or 0)
              + 0.1 * int(getattr(u, "cache_read_input_tokens", 0) or 0)) / 1e6 * 3.0
             + int(getattr(u, "output_tokens", 0) or 0) / 1e6 * 15.0)
        with замок:
            расход[0] += ц
        ок, почему = _вердикт_линзы(т)
        with замок:
            if ок:
                итог["годно"] += 1
            else:
                итог["ЛИНЗА ПРОТИВ"] += 1
                плохие.append((з, почему))
                print("  #%-6s %-34s %s"
                      % (з.get("review_id"), str(з.get("имя"))[:34], почему[:80]),
                      flush=True)
    except Exception as e:  # noqa: BLE001
        with замок:
            итог["сбой"] += 1


with ThreadPoolExecutor(max_workers=8) as пул:
    list(пул.map(проверить, карточки))

print("\n=== ИТОГ ЛИНЗЫ ===")
for к, н in итог.most_common():
    print("  %-20s %d" % (к, н))
print("  потрачено: $%.3f" % расход[0])

if not СНЯТЬ:
    print("\nсухой прогон. Снять — --снять")
    raise SystemExit(0)

снято = 0
for з, почему in плохие:
    r = int(з["review_id"])
    try:
        if store.confirm_decide(r, status="skipped",
                                decided_by="линза направления (добор)",
                                reason=("не то направление/смысл: " + почему)[:180]):
            снято += 1
        else:
            стр = store._conn.execute(
                "SELECT message_id FROM confirm_reviews WHERE id=?", (r,)).fetchone()
            if стр and стр[0] and store.mark_skipped_if_not_terminal(
                    int(стр[0]), "линза направления: " + почему[:100]):
                снято += 1
    except Exception as e:  # noqa: BLE001
        print("  #%s: %s" % (r, str(e)[:90]))
print("\nснято: %d" % снято)

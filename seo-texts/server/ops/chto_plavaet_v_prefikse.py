# -*- coding: utf-8 -*-
"""Что плавает в системном блоке письма: сверка префиксов по хешу.

Замер 24.08 доказал, что шлюз читает кэш безупречно: одинаковый system
даёт запись на первом вызове и чтение на втором и третьем (3.5 с вместо
24.5). А в журнале партии каждое письмо пишет кэш на КАЖДОМ из пяти
вызовов и не читает ни разу. Значит префикс между вызовами отличается.

Здесь никаких обращений к провайдеру: строим промпты локально теми же
функциями, режем тем же razrezat_promt и сверяем хеши статических
частей. Если они разные — печатаем первое расхождение с окрестностями,
чтобы было видно, какое поле течёт.
"""
import hashlib
import sys

sys.path.insert(0, r"C:\sender\sender")
sys.path.insert(0, r"C:\sender")

import gen_provider                                            # noqa: E402
from sender.ai_letter import (gen_prompt, judge_prompt,        # noqa: E402
                              load_facts, vf_prompt)
from sender.ai_quota import build_ai_quota                     # noqa: E402
from sender.config import Config                               # noqa: E402
from sender.store import Store                                 # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)
факты = load_facts(division="meyer")


def _хеш(с):
    return hashlib.sha256((с or "").encode("utf-8")).hexdigest()[:16]


def _разбор(имя, промпт):
    системный, тело = gen_provider.razrezat_promt(промпт)
    print("  %-26s статика %6s знаков хеш %s | тело %d знаков"
          % (имя,
             len(системный) if системный else "НЕТ",
             _хеш(системный) if системный else "-",
             len(тело)))
    return системный


# Берём трёх РАЗНЫХ получателей мейеровской группы.
группы = store.recipient_groups().get("по_id") or {}
ГРУППА = "Партия 935"
кандидаты = [rid for rid, gr in sorted(группы.items()) if ГРУППА in gr][:400]
взяли = []
for rid in кандидаты:
    rec = store.get_recipient(rid)
    if not rec:
        continue
    try:
        взяли.append(q._request(rec))
    except Exception as e:                                     # noqa: BLE001
        print("не собрался запрос для %s: %s" % (rid, str(e)[:80]))
    if len(взяли) >= 3:
        break

print("получателей взято: %d" % len(взяли))
print("\n=== ПРОМПТ ГЕНЕРАЦИИ (gen_prompt) ДЛЯ РАЗНЫХ КОМПАНИЙ ===")
статики = []
for н, req in enumerate(взяли):
    статики.append(_разбор("письмо #%d" % (н + 1),
                           gen_prompt([req], факты, "meyer", angle_base=н)))

print("\n=== ТЕ ЖЕ ПРОМПТЫ С ОДИНАКОВЫМ angle_base ===")
одинаковые = [gen_prompt([req], факты, "meyer", angle_base=0) for req in взяли]
for н, п in enumerate(одинаковые):
    _разбор("письмо #%d (angle 0)" % (н + 1), п)

print("\n=== ПРОЧИЕ ПРОМПТЫ ПИСЬМА ===")
проба = {"subject": "тема", "body": "тело письма для проверки"}
_разбор("судья (judge_prompt)", judge_prompt([(0, [проба, проба])], "meyer"))
_разбор("верификатор (vf)", vf_prompt(
    [(0, проба["subject"], проба["body"])], "meyer"))

if len(статики) >= 2 and статики[0] and статики[1]:
    a, b = статики[0], статики[1]
    if a == b:
        print("\nстатики письма #1 и #2 СОВПАДАЮТ байт в байт")
    else:
        i = 0
        while i < min(len(a), len(b)) and a[i] == b[i]:
            i += 1
        print("\nстатики РАСХОДЯТСЯ с позиции %d из %d" % (i, len(a)))
        print("  #1: ...%r" % a[max(0, i - 120):i + 160])
        print("  #2: ...%r" % b[max(0, i - 120):i + 160])

# -*- coding: utf-8 -*-
"""Читается ли кэш на БОЕВОМ пути письма, а не на синтетике.

Владелец 24.08: «раньше же письмо стоило в 3 раза меньше». Втрое — это
ровно разница между чтением кэша (0.1 ставки) и записью (1.25). Журнал
партии показывает запись на каждом из пяти вызовов письма и чтение ноль.

Прошлый мой замер кэш нашёл — но мерил синтетикой: короткий свой
системный блок, без effort, потолок 32 токена. Боевой вызов собран
иначе, и разница могла быть именно в этом. Здесь повторяем ровно тот
вызов, которым идут письма: системный блок от gen_prompt, тело от него
же, thinking=False, effort='low', потолок 4000.

Три захода подряд с ОДНИМ И ТЕМ ЖЕ системным блоком и разными телами —
как в жизни, где префикс общий, а компания разная. Контрольная серия без
effort — чтобы увидеть, не он ли ломает попадание.
"""
import hashlib
import sys
import time

sys.path.insert(0, r"C:\sender\sender")
sys.path.insert(0, r"C:\sender")

import gen_provider                                            # noqa: E402
from sender.ai_letter import gen_prompt, load_facts            # noqa: E402
from sender.ai_quota import build_ai_quota                     # noqa: E402
from sender.config import Config                               # noqa: E402
from sender.store import Store                                 # noqa: E402

ПОТОЛОК_ОТВЕТА = 4000
МОДЕЛЬ = "claude-opus-4-8"
ГРУППА = "Партия 935"

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)
факты = load_facts(division="meyer")

группы = store.recipient_groups().get("по_id") or {}
взяли = []
for rid in sorted(rid for rid, gr in группы.items() if ГРУППА in gr):
    rec = store.get_recipient(rid)
    if not rec:
        continue
    try:
        взяли.append(q._request(rec))
    except Exception:                                          # noqa: BLE001
        continue
    if len(взяли) >= 3:
        break
print("получателей взято: %d" % len(взяли))
if len(взяли) < 2:
    raise SystemExit("нечего сравнивать")

промпты = [gen_prompt([r], факты, "meyer", angle_base=0) for r in взяли]
части = [gen_provider.razrezat_promt(п) for п in промпты]
хеши = {hashlib.sha256((с or "").encode()).hexdigest()[:12] for с, _ in части}
print("системных блоков разных: %d (%s)" % (len(хеши), ", ".join(хеши)))
print("длина системного блока: %d знаков" % len(части[0][0] or ""))


def _зов(системный, тело, усилие, метка):
    т0 = time.time()
    try:
        m = gen_provider._raw_stream(
            [{"role": "user", "content": тело}], МОДЕЛЬ,
            ПОТОЛОК_ОТВЕТА, thinking=False, effort=усилие,
            system=системный)
        u = getattr(m, "usage", None)
        print("  %-22s %5.1f c | вход=%s запись=%s чтение=%s выход=%s"
              % (метка, time.time() - т0,
                 getattr(u, "input_tokens", "?"),
                 getattr(u, "cache_creation_input_tokens", "?"),
                 getattr(u, "cache_read_input_tokens", "?"),
                 getattr(u, "output_tokens", "?")))
    except Exception as e:                                     # noqa: BLE001
        print("  %-22s СБОЙ %5.1f c %s: %s"
              % (метка, time.time() - т0, type(e).__name__, str(e)[:120]))


print("\n=== БОЕВОЙ ВЫЗОВ: effort='low', потолок 4000 ===")
for н, (системный, тело) in enumerate(части, 1):
    _зов(системный, тело, "low", "письмо %d" % н)
    time.sleep(1)

print("\n=== КОНТРОЛЬ: то же самое БЕЗ effort ===")
for н, (системный, тело) in enumerate(части, 1):
    _зов(системный, тело, None, "письмо %d без effort" % н)
    time.sleep(1)

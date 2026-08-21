# -*- coding: utf-8 -*-
"""Довезти на боевой gates.py общую строку отказов почтовика.

Ящиковый гейт сегодняшние отказы не покажет: mailbox_id при неудачной
отправке пишем только с 21.08, и у 59 из 61 он пуст. Общая строка
«почтовик / вся отправка за сутки» считает по всей отправке и попадает в
active_trips, то есть в уже собранный экран «Сработавшие гейты» - без
пересборки фронта, которую делать нельзя (бандл чужой).

Хирургия по якорям, .bak, компиляция. Сухой прогон; катить: --katit
"""
import base64
import io
import json
import os
import py_compile
import sys
import time
import zlib

КОРЕНЬ = r"C:\sender\sender"
КАТИТЬ = "--katit" in sys.argv
ПАРЫ = json.loads(zlib.decompress(base64.b64decode("eJztVl+P20QQ/yqj9MUWqclVAkGk8IA48YL4Apco57M3iantDbZT2iKkS6LqWt3BCQRCvBTxzIsvJEqaa3JSP8HuV+CTMLPrxI7v6B+eKtScLrF3Zmd+85vZ2fm2ErPQZdH7XTthsdV/UKnDwUEFCp+AJZHnNJqViH3FnKQdoWazUm2GRaVwEDAU8KjBk7v2w5IUfSQN+oL34CZ50otY3OO+2xBXYi2PxVr8VVAxm6F+cVkHnB5z7ra7Pj+yfSNmfseE25/A5wjqM+Z4scfDer6zWaG//Xu2P0AF9MNA7wSHB33f9hASRQ4GiXp25EKc8L5pwZccgkFiJ2jP0lZyqyqSBpBzq+3wQZgYTeIxQVog9kKHNbRMPRummW/N3Zb3byWvNhKxZBCF2X4Xo3aZUSLc4X2GKdPBokW0+fYnVVlp34tZl79mZsVTORJLkYq5PAXl5gQX1mIiFrSslkD8JP4Qv4jfAMUjcYVIUlRYihmIOerIoRwrKwv4+/hneh0psEv8fwZiRWamIpWPxYUKY2ptkNNH/IqiEzETz7X5KT5eyjPctlYLIM/lE4WGUCEFYl0HOc6XU71PBQEKOJlYVUEFQqaWZGomh+ISISr8i4L/FYrGCuAJOSXIN4WJTCzQRCpWENief8Tvtz23CpojJcGwz9APIVRRo71UubyzZ9U+Im5yrxjABx8XgFNwgNDn8OHeNjTCOiY60c1CpyKPWvGFbhYqAiC0CGKJDlMxlaeIPJU/IKShPLcK0T4VF8rCM8rTifwRCdYsf6/oyrDPNllMiRgkaLRBsCkWsq/XLzDkKSVkqPTncrybX/RIoJTBM1UhL/4sV9qLy3qGQHtXxFygZLKtQszkmBhFARXIuaa+kHlVZxN5Kh+hMpZA4ajotFORZklayEdAhJOiznmhamcKg6qc+Q555TZWKPwGuHjMEi9gVsi/MejhIQ+ZNUgc04oYNian3GJ6fBA1alUIvHCQMHqKmcNDV685Ed+8mm/UOHNQhX2qMVzbmLWuuG8Hr9ifNyA00vG5nRhdhs09iYzMZKdbRX42JyOz3HcUsDtWzQQeqd//0oTL1XKtzyZ2hHBIc0L1Xj7AablPXTPwVnbzd1f0G17RrSrkk9emMSLbKfb3OZ75ERjq0GMRYFvGZrLIWg0cHrKMv7bt+4eHSI74HdvbMfYB6u1X2U2CzU01PZWg2+I5vVATkacvaRNYWv24Dr4XJwfFHLaQn4NWrtfd8LWT/gInXge6FlnrM7deqi7yYdkoCV2jaxadPyipZmeUxeiOMG1OMA87XtfaSneywe47rJ/Avvqh8gO4BSH/2q7Dp1/s12p7/+6iGGEHm0BwBF6Ya5TAubscZGpGcGTll65ZnMXepVl9bhWuwpdNctgfMdYbRhy6l1GFuJiUL0R8rW4vf9C3fH4774C4PqOs9H2aanJpYMmmgTMw8pzSQFSehmiseqwGQznUM1TxRttlsTj57lLJX4dK/n8/Ma3Wd/8AXfQd3A==")).decode())

for имя, куски in ПАРЫ.items():
    путь = os.path.join(КОРЕНЬ, имя.replace("sender/", ""))
    т = io.open(путь, encoding="utf-8").read()
    новый, применено, стояло = т, 0, 0
    for было, стало in куски:
        if стало in новый and было not in новый:
            стояло += 1
            continue
        n = новый.count(было)
        if n != 1:
            print(f"{имя}: якорь встречается {n} раз - НЕ ТРОГАЕМ")
            новый = None
            break
        новый = новый.replace(было, стало, 1)
        применено += 1
    if новый is None:
        raise SystemExit(1)
    print(f"{имя}: применено {применено}, уже стояло {стояло}, "
          f"было {len(т)} знаков, станет {len(новый)}")
    if not КАТИТЬ:
        continue
    io.open(f"{путь}.bak-{int(time.time())}", "w", encoding="utf-8",
            newline="").write(т)
    with io.open(путь, "w", encoding="utf-8", newline="") as f:
        f.write(новый)
        f.flush()
        os.fsync(f.fileno())
    py_compile.compile(путь, doraise=True)
    print(f"  записан: {имя}")

if not КАТИТЬ:
    print("\nсухой прогон. Катить - --katit")
    raise SystemExit(0)

sys.path.insert(0, r"C:\sender")
for м in list(sys.modules):
    if м.startswith("sender."):
        sys.modules.pop(м, None)
from sender.config import Config                                    # noqa: E402
from sender.store import Store                                      # noqa: E402
from sender.wiring import build_deps                                # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
deps = build_deps(cfg, store, dry_run=True)
о = deps.gates.check_otkaz_vsego()
print(f"\nобщая строка: {о.scope}/{о.target} {о.metric}={о.value}% "
      f"порог {о.threshold}% зажглась={о.tripped}")
trips = deps.gates.active_trips()
print(f"сработавших гейтов всего: {len(trips)}")
for t in trips[:8]:
    print(f"  {t.scope}/{t.target}: {t.metric} {t.value} при пороге {t.threshold}")
print("НУЖЕН РЕСТАРТ: Restart-Service SenderPanel -Force")

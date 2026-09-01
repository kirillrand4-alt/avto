# -*- coding: utf-8 -*-
"""Только чтение: готовность ящиков глазами панели (правильный конструктор)."""
import inspect
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config          # noqa: E402
from sender.store import Store            # noqa: E402
from sender.suppression import Suppression  # noqa: E402
import sender.sender as S                 # noqa: E402

print("=== Sender.__init__ ===")
print("  " + str(inspect.signature(S.Sender.__init__)))

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
sup = Suppression(store)

gates = None
for мод in ("sender.gates", "sender.reputation", "sender.zaslony"):
    try:
        m = __import__(мод, fromlist=["*"])
        for имя in dir(m):
            o = getattr(m, имя)
            if inspect.isclass(o) and "gate" in имя.lower():
                try:
                    gates = o(cfg, store)
                    print("  gates: %s.%s собран" % (мод, имя))
                    break
                except Exception:
                    try:
                        gates = o(store, cfg)
                        print("  gates: %s.%s собран (обратный порядок)" % (мод, имя))
                        break
                    except Exception:
                        pass
        if gates:
            break
    except Exception:
        pass
if gates is None:
    print("  gates собрать не вышло — пробую None")

НОВЫЕ = ("food-sort.ru", "sorting-systems", "rentgen-control", "optical-sort",
         "rentgen-inspec", "inspection-syst")
snd = S.Sender(cfg, store, sup, gates)
строки = []
for mb in cfg.mailboxes():
    mid = mb.mailbox_id
    нов = any(x in mid for x in НОВЫЕ)
    try:
        r = snd.mailbox_readiness(mid)
        строки.append((нов, mid, r.ready, r.ramp_day, r.daily_limit, r.sent_today,
                       ",".join(r.reasons or ())))
    except Exception as ex:
        строки.append((нов, mid, "ОШИБКА", "", "", "", str(ex)[:60]))

for метка, наб in (("СТАРЫЕ (21)", False), ("НОВЫЕ, заведены вчера (12)", True)):
    print("\n=== %s ===" % метка)
    print("  %-38s %6s %5s %6s %8s  %s"
          % ("ящик", "готов", "рамп", "лимит", "сегодня", "причины"))
    for нов, mid, ready, rd, dl, st, rs in строки:
        if нов == наб:
            print("  %-38s %6s %5s %6s %8s  %s" % (mid[:38], ready, rd, dl, st, rs))

print("\n=== ИТОГ ===")
ст = [x for x in строки if not x[0] and isinstance(x[4], int)]
нв = [x for x in строки if x[0] and isinstance(x[4], int)]
if ст:
    print("  старые: лимит %s, рамп %s"
          % (sorted({x[4] for x in ст}), sorted({x[3] for x in ст})))
if нв:
    print("  новые : лимит %s, рамп %s"
          % (sorted({x[4] for x in нв}), sorted({x[3] for x in нв})))

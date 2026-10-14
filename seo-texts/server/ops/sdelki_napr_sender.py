# -*- coding: utf-8 -*-
"""sender.py: заслон «сделка в работе» по направлениям (владелец 14.10). Правка по якорю, бэкап, py_compile, откат."""
import io
import py_compile
import shutil
import sys
import time
ПУТЬ = r"C:\\sender\\sender\\sender.py"
т = io.open(ПУТЬ, encoding="utf-8").read()
if "deal_in_division" in т:
    print("=== СДЕЛКИ: SENDER: УЖЕ БЫЛО ===")
    sys.exit(0)
ПАРЫ = [('                if _камп_div and _камп_div != mb_div:\n                    return (f"campaign_vs_mailbox:campaign={_камп_div},"\n                            f"mailbox={mb_div}")\n        except Exception:  # noqa: BLE001 - гейт не роняет отправку\n            pass\n', '                if _камп_div and _камп_div != mb_div:\n                    return (f"campaign_vs_mailbox:campaign={_камп_div},"\n                            f"mailbox={mb_div}")\n        except Exception:  # noqa: BLE001 - гейт не роняет отправку\n            pass\n        # СДЕЛКА В РАБОТЕ ПО НАПРАВЛЕНИЮ (владелец 14.10): сделка Meyer — не\n        # пишет Meyer, сделка КЦ — не пишет КЦ, только СЦ — пишут все.\n        try:\n            from sender.sdelki_napr import blok as _sdelka\n            with self.store._lock:\n                _сд = _sdelka(self.store._conn, getattr(recipient, "inn", None),\n                              письмо_div or mb_div)\n            if _сд:\n                return "deal_in_division:" + _сд\n        except Exception:  # noqa: BLE001\n            pass\n')]
for с, _н in ПАРЫ:
    if т.count(с) != 1:
        print("якорь (%d): %r" % (т.count(с), с[:120]))
        print("=== СДЕЛКИ: SENDER: НЕ ПРИМЕНЕНО ===")
        sys.exit(0)
бэкап = ПУТЬ + ".bak-%d" % int(time.time())
shutil.copy2(ПУТЬ, бэкап)
for с, н in ПАРЫ:
    т = т.replace(с, н)
io.open(ПУТЬ, "w", encoding="utf-8").write(т)
try:
    py_compile.compile(ПУТЬ, doraise=True)
except Exception as е:  # noqa: BLE001
    shutil.copy2(бэкап, ПУТЬ)
    print("сбой, откат: %s" % е)
    print("=== СДЕЛКИ: SENDER: ОТКАТ ===")
    sys.exit(0)
print("бэкап: %s" % бэкап)
print("=== СДЕЛКИ: SENDER: ПРИМЕНЕНО ===")

# -*- coding: utf-8 -*-
"""sender.py division_block: ящик должен совпадать и с направлением кампании (ящики КЦ 14.10).
Правка по якорю, бэкап, py_compile, откат."""
import io
import py_compile
import shutil
import sys
import time
ПУТЬ = r"C:\\sender\\sender\\sender.py"
т = io.open(ПУТЬ, encoding="utf-8").read()
if "campaign_vs_mailbox" in т:
    print("=== ЯЩИК = КАМПАНИЯ: УЖЕ БЫЛО ===")
    sys.exit(0)
ПАРЫ = [('        if письмо_div and письмо_div != mb_div:\n            return (f"letter_vs_mailbox:letter={письмо_div},"\n                    f"mailbox={mb_div}")\n', '        if письмо_div and письмо_div != mb_div:\n            return (f"letter_vs_mailbox:letter={письмо_div},"\n                    f"mailbox={mb_div}")\n        # ЯЩИК ОБЯЗАН СОВПАДАТЬ И С КАМПАНИЕЙ (ящики КЦ, 14.10). Направление\n        # письма бывает не определено (старое письмо без метки), а перелив пулов\n        # (provider_split.overflow) отдаёт кандидатов из ЛЮБОГО пула — так\n        # компрессорный ящик мог бы уйти под кампанию Meyer. Последний рубеж.\n        try:\n            _cid = getattr(message, "campaign_id", None) if message is not None else None\n            if _cid:\n                from sender.company_card import campaign_division as _cdiv\n                _camp = self.store.get_campaign(int(_cid))\n                _камп_div = _cdiv(_camp) if _camp else None\n                if _камп_div and _камп_div != mb_div:\n                    return (f"campaign_vs_mailbox:campaign={_камп_div},"\n                            f"mailbox={mb_div}")\n        except Exception:  # noqa: BLE001 - гейт не роняет отправку\n            pass\n')]
for с, _н in ПАРЫ:
    if т.count(с) != 1:
        print("якорь (%d): %r" % (т.count(с), с[:120]))
        print("=== ЯЩИК = КАМПАНИЯ: НЕ ПРИМЕНЕНО ===")
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
    print("=== ЯЩИК = КАМПАНИЯ: ОТКАТ ===")
    sys.exit(0)
print("бэкап: %s" % бэкап)
print("=== ЯЩИК = КАМПАНИЯ: ПРИМЕНЕНО ===")

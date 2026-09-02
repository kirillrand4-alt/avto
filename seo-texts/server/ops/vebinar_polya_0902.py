# -*- coding: utf-8 -*-
"""Только чтение: поля MessageIn/RecipientIn/CampaignIn и как рождается confirm_review."""
import inspect
import sys

sys.path.insert(0, r"C:\sender")
from sender import store as S  # noqa: E402

print("=== где создаётся confirm_review ===")
for имя in dir(S.Store):
    if "confirm" in имя.lower() and not имя.startswith("_"):
        try:
            print("  %-30s %s" % (имя, str(inspect.signature(getattr(S.Store, имя)))[:130]))
        except Exception:
            pass

print("\n=== ПОЛЯ ===")
мод = sys.modules.get("sender.models")
if мод is None:
    try:
        import sender.models as мод
    except Exception as ex:
        print("  нет sender.models: %s" % str(ex)[:80])
        мод = None
for имя in ("CampaignIn", "RecipientIn", "MessageIn", "ConfirmReviewIn", "SuppressionIn"):
    к = getattr(S, имя, None) or (getattr(мод, имя, None) if мод else None)
    if к is None:
        print("  %s: не найден" % имя)
        continue
    поля = getattr(к, "__dataclass_fields__", None)
    if поля:
        стр = []
        for n, f in поля.items():
            деф = "" if f.default is inspect._empty or str(f.default).startswith("<") else "=%s" % f.default
            стр.append("%s%s" % (n, деф))
        print("  %s(%s)" % (имя, ", ".join(стр)))
    else:
        print("  %s%s" % (имя, str(inspect.signature(к))[:400]))

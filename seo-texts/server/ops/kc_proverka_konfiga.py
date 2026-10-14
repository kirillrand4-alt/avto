# -*- coding: utf-8 -*-
"""После заведения ящиков КЦ: перелив пулов, индекс направлений, молодые домены,
бренд по направлению. Только чтение."""
import sys

sys.path.insert(0, r"C:\sender")
from sender.company_card import CompanyCards  # noqa: E402
from sender.config import Config  # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
print("provider_split.overflow:", cfg.get("provider_split.overflow", None))
print("obzvon.index_path:", cfg.get("obzvon.index_path", None))
try:
    cards = CompanyCards(index_path=cfg.get("obzvon.index_path", None), enrich_db_path=r"C:\sender\enrich.db")
    print("индекс направлений активен:", getattr(cards, "active", None))
except Exception as е:  # noqa: BLE001
    print("индекс не поднялся:", е)
мол = cfg.get("gates.young_domain.domains", {}) or {}
for д in ("compressor-air-expert.ru", "compressor-pro-systems.ru", "kompressor-air-trade.ru",
          "kompressor-pro-expert.ru", "kompressor-pro-trade.ru"):
    print("молодой домен %-28s %s" % (д, мол.get(д, "НЕТ В СПИСКЕ (считается зрелым)")))
print("young_domain min_age_days:", cfg.get("gates.young_domain.min_age_days", None))
print("brand_by_division:", cfg.get("personalization.brand_by_division", None))
print("warmup-узлы kc:", [m.mailbox_id for m in cfg.mailboxes() if getattr(m, "division", None) == "kc"
                          and getattr(m, "is_warmup_node", False)])
print("=== ПРОВЕРКА КОНФИГА КЦ ===")

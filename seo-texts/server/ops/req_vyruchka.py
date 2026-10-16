import sys
sys.path.insert(0, r"C:\sender")
from sender.config import Config
from sender.store import Store
from sender.ai_quota import build_ai_quota
import sqlite3
cfg = Config.load(r"C:\sender\sender.yaml"); st = Store(cfg.get("service.db_path", r"C:\sender\sender.db")); q = build_ai_quota(st, cfg)
c = sqlite3.connect(r"C:\sender\sender.db")
rid = c.execute("SELECT id FROM recipients WHERE email='info@veka.ru'").fetchone()[0]
req = q._request(st.get_recipient(rid))
ex = req.get("extra") or {}
print("ключи req:", sorted(req.keys())); print("ключи extra:", sorted(ex.keys()) if isinstance(ex, dict) else ex)
for k in ("revenue", "company_size", "revenue_rub"): print(k, "req:", req.get(k), "extra:", ex.get(k) if isinstance(ex, dict) else None)
e = sqlite3.connect(r"C:\sender\enrich.db"); print("enrich:", e.execute("SELECT revenue_rub FROM companies WHERE inn=(SELECT inn FROM recipients WHERE id=?)" , (rid,)).fetchone() if False else e.execute("SELECT revenue_rub FROM companies WHERE inn=?", (st.get_recipient(rid).inn,)).fetchone())

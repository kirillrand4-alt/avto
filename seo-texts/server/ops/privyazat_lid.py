# -*- coding: utf-8 -*-
"""Привязать лид к компании по ИНН (с пометкой в названии и в «нужде»).

    privyazat_lid.py <lead_id> <inn> "<пометка>"
"""
import sqlite3
import sys
from datetime import datetime, timezone
лид, инн, пометка = int(sys.argv[1]), sys.argv[2], sys.argv[3]
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
р = c.execute("SELECT id, company_name FROM recipients WHERE inn=? ORDER BY id DESC LIMIT 1", (инн,)).fetchone()
л = c.execute("SELECT need, version FROM leads WHERE id=?", (лид,)).fetchone()
имя = "%s (%s)" % (р["company_name"], пометка)
нужда = "[%s] %s" % (пометка, л["need"] or "")
т = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
with c:
    c.execute("UPDATE leads SET recipient_id=?, inn=?, company_name=?, need=?, version=version+1, updated_at=? WHERE id=?",
              (р["id"], инн, имя, нужда, т, лид))
print("лид #%d → %s, получатель #%s" % (лид, имя, р["id"]))
print("=== ЛИД ПРИВЯЗАН ===")

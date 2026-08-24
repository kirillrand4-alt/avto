# -*- coding: utf-8 -*-
"""Что можно вернуть из снятого линзой по «правилу 2».

Линза несёт старую редакцию правила: запрет строки отказа для всех. Для КЦ
канон её ТРЕБУЕТ (zashit_kontsovku), и в комментарии замер: «на письма с ней
приходили ответы». Значит снятые по этой причине КЦ-письма сняты зря.

Смотрим: сколько снято, в каком состоянии их письма, что восстановимо.
"""
import sqlite3
from collections import Counter

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row

строки = c.execute(
    "SELECT cr.id, cr.reason, cr.decided_by, cr.decided_at, cr.message_id, "
    "       m.status mst, m.campaign_id, r.company_name "
    "  FROM confirm_reviews cr LEFT JOIN messages m ON m.id=cr.message_id "
    "  LEFT JOIN recipients r ON r.id=cr.recipient_id "
    " WHERE cr.status='skipped' AND COALESCE(cr.decided_by,'') LIKE '%линза%' "
    " ORDER BY cr.id").fetchall()
print("снято линзой всего: %d" % len(строки))

по_причине = Counter(str(р["reason"] or "").split(":")[1].strip()[:40]
                     if ":" in str(р["reason"] or "") else "-"
                     for р in строки)
print("\n=== ПО ПРИЧИНАМ ===")
for к, н in по_причине.most_common(10):
    print("  %-44s %d" % (к, н))

правило2 = [р for р in строки if "правило 2" in str(р["reason"] or "")]
кц = [р for р in правило2 if р["campaign_id"] != 11]
мейер = [р for р in правило2 if р["campaign_id"] == 11]
print("\n=== СНЯТО ПО «ПРАВИЛУ 2» ===")
print("  всего: %d | КЦ: %d (сняты ЗРЯ) | Meyer: %d (сняты по делу)"
      % (len(правило2), len(кц), len(мейер)))

print("\n=== СОСТОЯНИЕ ПИСЕМ У КЦ-СНЯТЫХ ===")
for к, н in Counter(str(р["mst"] or "нет письма") for р in кц).most_common():
    метка = "  ← можно вернуть" if к in ("skipped", "pending_review") else \
            ("  ← УЖЕ УШЛО, возвращать нечего" if к == "sent" else "")
    print("  письмо %-16s %4d%s" % (к, н, метка))

print("\n=== ПРИМЕРЫ ===")
for р in кц[:6]:
    print("  #%-6s %-34s письмо=%s | %s"
          % (р["id"], str(р["company_name"] or "")[:34], р["mst"],
             str(р["reason"])[:70]))

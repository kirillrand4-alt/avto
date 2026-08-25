# -*- coding: utf-8 -*-
"""Сколько писем прогон переписал у СТАРЫХ карточек, а не завёл новых.

Блок КЦ шёл по компаниям, возвращённым в пул: у них карточка уже была, и
новое письмо легло в неё же. Поэтому в «создано сегодня» их не видно, а в
очереди подтверждения они есть.
"""
import sqlite3
from collections import Counter

СТАРТ = "2026-08-25 10:41"
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row

старые_ждут = c.execute(
    "SELECT COUNT(*) FROM confirm_reviews "
    " WHERE status='pending' AND created_at < ?", (СТАРТ,)).fetchone()[0]
новые_ждут = c.execute(
    "SELECT COUNT(*) FROM confirm_reviews "
    " WHERE status='pending' AND created_at >= ?", (СТАРТ,)).fetchone()[0]
print("ждут подтверждения: старых карточек %d, новых %d"
      % (старые_ждут, новые_ждут))

print("\n=== СТАРЫЕ КАРТОЧКИ, ПЕРЕПИСАННЫЕ СЕГОДНЯ (последние 10) ===")
for р in c.execute(
        "SELECT cr.id, substr(cr.created_at,6,11) заведена, "
        "       substr(cr.updated_at,6,11) переписана, r.company_name, "
        "       COALESCE(m.status,'-') ms "
        "  FROM confirm_reviews cr "
        "  LEFT JOIN recipients r ON r.id=cr.recipient_id "
        "  LEFT JOIN messages m ON m.id=cr.message_id "
        " WHERE cr.status='pending' AND cr.created_at < ? AND cr.updated_at >= ? "
        " ORDER BY cr.updated_at DESC LIMIT 10", (СТАРТ, СТАРТ)):
    print("   #%-6s заведена %s -> переписана %s | %-28s письмо %s"
          % (р["id"], р["заведена"], р["переписана"],
             str(р["company_name"] or "")[:28], р["ms"]))

print("\n=== ИТОГ: ГДЕ ПИСЬМА ПРОГОНА ===")
всего_ждут = старые_ждут + новые_ждут
print("   в очереди ПОДТВЕРЖДЕНИЯ (ждут вашего решения): %d" % всего_ждут)
print("   в очереди ОТПРАВКИ (уже подтверждены):         %d"
      % c.execute("SELECT COUNT(*) FROM messages "
                  " WHERE status IN ('scheduled','sending')").fetchone()[0])
print("   отправлено сегодня:                            %d"
      % c.execute("SELECT COUNT(*) FROM messages WHERE status='sent' "
                  "   AND substr(sent_at,1,10)=date('now')").fetchone()[0])

import sqlite3, sys
c = sqlite3.connect(r"C:\sender\sender.db")
for lid in sys.argv[1].split(","):
    inn, name, em = c.execute("SELECT inn, company_name, email FROM leads WHERE id=?", (int(lid),)).fetchone()
    dom = em.split("@")[-1]
    b = c.execute("SELECT id, status FROM leads WHERE status='in_bitrix' AND (inn=? OR email LIKE ?)", (inn, "%@" + dom)).fetchall()
    print(lid, name, "| в Bitrix:", b or "нет")

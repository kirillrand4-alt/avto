# -*- coding: utf-8 -*-
"""Какие операции умеет серверный обогатитель (enrich_contacts.py)."""
import io, re
т = io.open(r"C:\sender\server\enrich_contacts.py", encoding="utf-8",
            errors="ignore").read()
имена = sorted(set(re.findall(r"op\s*==\s*['\"]([a-z0-9_]+)['\"]", т)))
print("операций: %d" % len(имена))
for i in range(0, len(имена), 4):
    print("   " + "  ".join("%-26s" % x for x in имена[i:i + 4]))
print("\n=== те, что похожи на checko/реквизиты ===")
for и in имена:
    if any(с in и for с in ("checko", "okved", "rekviz", "company", "kartoch",
                            "finans", "egrul")):
        м = re.search(r"op\s*==\s*['\"]%s['\"][^\n]*\n" % и, т)
        i = т.index("'%s'" % и) if "'%s'" % и in т else т.index('"%s"' % и)
        кусок = т[max(0, i - 400):i + 700]
        док = re.findall(r'"""(.{0,300}?)"""', кусок, re.S)
        print("\n--- %s ---" % и)
        if док:
            print("   %s" % " ".join(док[0].split())[:260])

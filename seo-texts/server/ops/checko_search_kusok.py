# -*- coding: utf-8 -*-
import io, os, re
п = r"C:\seostat\Parser2\metalparser\checko.py"
стр = io.open(п, encoding="utf-8", errors="ignore").read().split("\n")
for i in range(40, 96):
    print("%4d| %s" % (i + 1, стр[i][:114]))
т = "\n".join(стр)
print("\n=== где считается количество ===")
for i, с in enumerate(стр):
    if re.search(r"(total|count|Всего|итого|len\(|записей)", с) \
            and re.search(r"search|найд|Data|результ", с, re.I):
        print("%4d| %s" % (i + 1, с.strip()[:110]))
print("\n=== ключ ===")
print("   CHECKO_API_KEY в окружении сервера: %s"
      % ("задан" if os.environ.get("CHECKO_API_KEY") else "НЕТ"))
for k in sorted(os.environ):
    if "CHECKO" in k.upper():
        print("   %s = задан" % k)

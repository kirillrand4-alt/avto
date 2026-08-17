# -*- coding: utf-8 -*-
"""Открыть сайт компании С СЕРВЕРА и сверить утверждения письма с ним."""
import re, sys, urllib.request, gzip, io
URL = sys.argv[1] if len(sys.argv) > 1 else "http://naturalsupp.ru/"
СЛОВА = sys.argv[2].split("|") if len(sys.argv) > 2 else [
    "бад", "витамин", "добавк", "фасовк", "упаковк", "производств"]
req = urllib.request.Request(URL, headers={
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept-Encoding": "gzip"})
try:
    with urllib.request.urlopen(req, timeout=60) as r:
        сырое = r.read()
        код = r.status
        if r.headers.get("Content-Encoding") == "gzip":
            сырое = gzip.decompress(сырое)
except Exception as ex:
    print(f"НЕ ОТКРЫЛСЯ: {type(ex).__name__} {str(ex)[:160]}")
    raise SystemExit(1)
текст = сырое.decode("utf-8", "replace")
без_тегов = re.sub(r"<script.*?</script>|<style.*?</style>", " ", текст,
                   flags=re.S | re.I)
без_тегов = re.sub(r"<[^>]+>", " ", без_тегов)
без_тегов = re.sub(r"\s+", " ", без_тегов)
print(f"HTTP {код}, знаков {len(текст)}, текста {len(без_тегов)}")
загл = re.search(r"(?is)<title[^>]*>(.*?)</title>", текст)
print("title:", (загл.group(1).strip()[:120] if загл else "нет"))
print("\nсверка слов из письма с сайтом:")
for с in СЛОВА:
    n = len(re.findall(с, без_тегов, flags=re.I))
    print(f"  «{с}»: {n} раз {'НАЙДЕНО' if n else 'НЕ НАЙДЕНО'}")
print("\nпервые 700 знаков текста сайта:")
print(без_тегов[:700])

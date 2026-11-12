# -*- coding: utf-8 -*-
"""Есть ли у сделки Битрикса отдельный «Комментарий» и поля причины провала Meyer: колонки выгрузки BITRIX-DEAL
и сколько сделок Meyer их заполнили. Только чтение."""
import html, re, zipfile
z = zipfile.ZipFile(r"C:\seostat\drop\drop-storage\BITRIX-DEAL-20260828.zip")
т = z.read([i.filename for i in z.infolist() if i.filename.lower().endswith(".xls")][0]).decode("utf-8", "replace")
ряды = re.findall(r"(?is)<tr[^>]*>(.*?)</tr>", т)
яч = lambda р: [html.unescape(re.sub(r"<[^>]+>", "", x)).strip() for x in re.findall(r"(?is)<t[hd][^>]*>(.*?)</t[hd]>", р)]
ш = яч(ряды[0]); кол = [(i, h) for i, h in enumerate(ш) if re.search(r"(?i)коммент|причин.*meyer|meyer.*причин", h) and not h.startswith(("Компания:", "Контакт:"))]
вор = ш.index("Воронка")
meyer = [яч(р) for р in ряды[1:] if "MEYER" in (яч(р)[вор] if вор < len(яч(р)) else "").upper()]
print("сделок Meyer в выгрузке:", len(meyer))
for i, h in кол:
    n = sum(1 for в in meyer if i < len(в) and в[i].strip())
    print("  %-75s заполнено у %d" % (h[:75], n))

# -*- coding: utf-8 -*-
"""Какие поля есть для сопоставления контактов Meyer со сделками: колонки BITRIX-DEAL (ID, ИНН, даты, компания)
и форма записи sdelki-vse-1410.json. Только чтение, значения контактов не печатаем."""
import html, io, json, re, zipfile
z = zipfile.ZipFile(r"C:\seostat\drop\drop-storage\BITRIX-DEAL-20260828.zip")
имя = [i.filename for i in z.infolist() if i.filename.lower().endswith(".xls")][0]
т = z.read(имя).decode("utf-8", "replace")
ряды = re.findall(r"(?is)<tr[^>]*>(.*?)</tr>", т)
яч = lambda р: [html.unescape(re.sub(r"<[^>]+>", "", x)).strip() for x in re.findall(r"(?is)<t[hd][^>]*>(.*?)</t[hd]>", р)]
ш = яч(ряды[0]); print("BITRIX-DEAL: сделок", len(ряды) - 1, "колонок", len(ш))
нужн = [(i, h) for i, h in enumerate(ш) if re.search(r"(?i)^ID$|ИНН|дата|создан|закры|изменен|стади|воронк|^Компания$|направлен|последн", h)]
пр = яч(ряды[1])
for i, h in нужн[:60]: print("  %3d %-60s пример: %s" % (i, h[:60], (пр[i] if i < len(пр) else "")[:25] if re.search(r"(?i)ID|дата|созда|закры|измен|стади|воронк|ИНН", h) else "…"))
д = json.load(io.open(r"C:\seostat\drop\drop-storage\sdelki-vse-1410.json", encoding="utf-8"))
к, v = next(iter(д.items())); print("sdelki-vse-1410: ключ ИНН вида", len(к), "знаков; запись:", json.dumps(v[:2], ensure_ascii=False)[:300])
import glob, os
print("прочие выгрузки сделок на дропе:", [os.path.basename(x) for x in glob.glob(r"C:\seostat\drop\drop-storage\*") if re.search(r"(?i)deal|sdelk|bitrix-export", x)][:20])

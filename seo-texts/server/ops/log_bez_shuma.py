# -*- coding: utf-8 -*-
"""Хвост panel_err.log без шума трёх известных битых писем (кириллица в адресе): что ещё пишет панель. Только чтение."""
import io, os, re
п = r"C:\sender\_ops\panel_err.log"; р = os.path.getsize(п)
with io.open(п, "rb") as f: f.seek(max(0, р - 3000000)); х = f.read().decode("utf-8", "replace").splitlines()
шум = re.compile(r"message_id=(20520|42885|21116)|UnicodeEncodeError|^\s+File |^\s+\^|^Traceback|^\s{4}\S|smtplib|_send_one|tick$")
ч = [x for x in х if not шум.search(x) and x.strip()]
print("\n".join(x[:230] for x in ч[-45:]))

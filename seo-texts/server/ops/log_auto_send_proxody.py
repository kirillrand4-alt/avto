# -*- coding: utf-8 -*-
"""Строки лога панели про проходы автоотправки (кроме трёх битых писем) и последние строки stdout. Только чтение."""
import io, os, re
for п in (r"C:\sender\_ops\panel_err.log",):
    р = os.path.getsize(п)
    with io.open(п, "rb") as f: f.seek(max(0, р - 6000000)); х = f.read().decode("utf-8", "replace").splitlines()
    кл = [x for x in х if re.search(r"(?i)auto_?send|проход|claim|разобрано|отправить некуда|Thread|Exception in", x) and not re.search(r"message_id=(20520|42885|21116)", x)]
    print("строк:", len(кл)); print("\n".join(x[:240] for x in кл[-25:]))

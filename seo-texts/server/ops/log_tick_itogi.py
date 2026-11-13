# -*- coding: utf-8 -*-
"""Итоги проходов автоотправки из логов панели («auto_send: {...}», «цикл запущен», «tick упал»). Только чтение."""
import io, os, re
for п in (r"C:\sender\_ops\panel_err.log", r"C:\sender\_ops\panel_out.log"):
    р = os.path.getsize(п)
    with io.open(п, "rb") as f: f.seek(max(0, р - 8000000)); х = f.read().decode("utf-8", "replace").splitlines()
    кл = [x for x in х if re.search(r"auto_send: \{|цикл запущен|tick упал|отправить некуда|podtyanut", x)]
    print("==", п, len(кл)); print("\n".join(x[:250] for x in кл[-15:]))

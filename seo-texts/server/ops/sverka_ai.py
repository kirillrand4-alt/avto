# -*- coding: utf-8 -*-
import hashlib, io, os
for f in ("ai_letter.py", "ai_quota.py"):
    п = os.path.join(r"C:\sender\sender", f)
    д = io.open(п, "rb").read()
    т = д.decode("utf-8", "replace")
    print("%-14s %7d байт  %5d строк  %s  метка:%s"
          % (f, len(д), т.count("\n"), hashlib.sha256(д).hexdigest()[:12],
             "ЕСТЬ" if ("ПОКУПАТЕЛЬ" in т or "perestavit" in т) else "нет"))

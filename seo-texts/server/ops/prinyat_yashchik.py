# -*- coding: utf-8 -*-
"""Разовый приём одного ящика за N дней: prinyat_yashchik.py <ящик> [дней=1]"""
import contextlib
import io
import os
import sys
sys.path.insert(0, r"C:\sender")
for с in open(r"C:\sender\panel.env", encoding="utf-8", errors="replace").read().splitlines():
    if "=" in с and not с.strip().startswith("#"):
        к, з = с.split("=", 1)
        os.environ.setdefault(к.strip(), з.strip().strip('"'))
from sender.cli import main  # noqa: E402
буф = io.StringIO()
with contextlib.redirect_stdout(буф), contextlib.redirect_stderr(буф):
    try:
        main(["--config", r"C:\sender\sender.yaml", "inbox-poll", "--keep-unread", "--no-drafts",
              "--mailbox", sys.argv[1], "--days", sys.argv[2] if len(sys.argv) > 2 else "1"])
    except SystemExit:
        pass
print("\n".join(с for с in буф.getvalue().splitlines() if "пусто" not in с)[-1500:])
print("=== ПРИЁМ ЯЩИКА ===")

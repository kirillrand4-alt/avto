# -*- coding: utf-8 -*-
"""Сверить серверные dsn.py и imap_watcher.py с моими правками.

Канон выкатки: сначала СРАВНИТЬ, потом трогать. C:\\sender\\sender\\ общий
с соседней сессией, и слепая перезапись затирает чужое.
"""
import hashlib
import io

ЯКОРЯ = {
    r"C:\sender\sender\dsn.py": [
        ("уже правлено", "def dsn_po_strukture"),
        ("место правки 1", 'if ctype in ("multipart/report", "message/delivery-status"):'),
        ("место правки 2", "m = _RE_STATUS.search(text)"),
    ],
    r"C:\sender\sender\imap_watcher.py": [
        ("уже правлено", "ПУСТОЙ РАЗБОР БЕЗ УЛИКИ"),
        ("место правки 1", "from sender.dsn import looks_like_dsn, parse_dsn"),
        ("место правки 2", "if kind == \"dsn\" and parse_dsn is not None:"),
    ],
}
for путь, якоря in ЯКОРЯ.items():
    try:
        т = io.open(путь, encoding="utf-8").read()
    except Exception as ex:                                   # noqa: BLE001
        print(f"{путь}: НЕ ПРОЧЁЛСЯ {type(ex).__name__} {ex}")
        continue
    ш = hashlib.sha256(т.encode()).hexdigest()[:16]
    print(f"\n{путь}\n  {len(т)} байт, sha {ш}")
    for имя, кусок in якоря:
        print(f"  {имя}: {'ЕСТЬ' if кусок in т else 'нет'}")

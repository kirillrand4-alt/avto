# -*- coding: utf-8 -*-
"""Ход отцеплённого добора: сколько карточек уже легло."""
import glob, io, os, sqlite3
логи = sorted(glob.glob(r"C:\sender\_ops\sdelki_dadata-*.log"))
if логи:
    п = логи[-1]
    т = io.open(п, encoding="utf-8", errors="ignore").read()
    print("лог %s (%d б):" % (os.path.basename(п), len(т)))
    print(т[-700:])
ошибки = sorted(glob.glob(r"C:\sender\_ops\sdelki_dadata-*.err"))
if ошибки:
    т = io.open(ошибки[-1], encoding="utf-8", errors="ignore").read()
    print("\nошибки (%d б): %s" % (len(т), т[-400:] if т else "пусто"))
ж = r"C:\sender\_ops\sdelki-rekvizity.jsonl"
if os.path.exists(ж):
    n = sum(1 for _ in io.open(ж, encoding="utf-8", errors="ignore"))
    print("\nстрок в журнале: %d" % n)
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True,
                    timeout=60)
print("в requisites с ОГРН: %d"
      % c.execute("SELECT COUNT(*) FROM requisites "
                  " WHERE COALESCE(ogrn,'')<>''").fetchone()[0])
c.close()

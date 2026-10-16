# -*- coding: utf-8 -*-
"""ai_quota._request: выручка из enrich.db (companies.revenue_rub), когда в карточке
обзвона финансов нет (группы «Россия 9000» и др.). Нужна канону КЦ 16.10 (крупным —
центробежные) и тону по размеру. Бэкап .bak-vyr-*. Нужен перезапуск панели для
панельной генерации; ops-генераторы подхватят сразу."""
import io, py_compile, shutil, sys, time
П = r"C:\sender\sender\ai_quota.py"
т = io.open(П, encoding="utf-8").read()
if "ВЫРУЧКА ИЗ ENRICH" in т:
    print("=== ВЫРУЧКА: УЖЕ БЫЛО ==="); sys.exit()
С = """        if not явное:
            карточное = self._division_kartochki(ecomp if card else {}, r)
"""
Н = """        # ВЫРУЧКА ИЗ ENRICH (16.10): у групп без карточки обзвона финансов нет,
        # и генерация не знала, что завод крупный (ВЕКА РУС, 8,6 млрд).
        if not extra.get("revenue") and self._enrich_db and os.path.exists(self._enrich_db):
            try:
                _con = sqlite3.connect(f"file:{self._enrich_db}?mode=ro", uri=True, timeout=5)
                try:
                    _row = _con.execute("SELECT revenue_rub FROM companies WHERE inn=?",
                                        (str(getattr(r, "inn", "") or "").strip(),)).fetchone()
                finally:
                    _con.close()
                if _row and _row[0]:
                    extra["revenue"] = _row[0]
            except Exception:  # noqa: BLE001 - без выручки письмо всё равно пишется
                pass
""" + С
if т.count(С) != 1:
    print("якорь:", т.count(С)); print("=== ВЫРУЧКА: НЕ ПРИМЕНЕНО ==="); sys.exit()
б = П + ".bak-vyr-%d" % int(time.time()); shutil.copy2(П, б)
io.open(П, "w", encoding="utf-8").write(т.replace(С, Н))
try:
    py_compile.compile(П, doraise=True)
except Exception as е:
    shutil.copy2(б, П); print("откат:", е); sys.exit()
print("бэкап:", б); print("=== ВЫРУЧКА: ПРИМЕНЕНО ===")

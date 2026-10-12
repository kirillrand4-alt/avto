# -*- coding: utf-8 -*-
"""Ролик другого станка — только если письмо называет этот станок.

Владелец 12.10 («к рентгену давать только рентгеновский ролик или не давать
никакого» — «давай»). Письмо «Кизлярским сырам» — только про рентген, а в
нём «видео с тестовой сортировки»: ролик фотосепаратора, подобранный по
самому уверенному продукту профиля (правило 14.08 «ролик про их продукт,
каким бы станком он ни снят»). Правило 14.08 оставляем там, где оно имеет
смысл — когда в карточке «ДВА ЭТАПА, ОБА НАШИ» и письмо называет второй
станок. Иначе — ролик своего станка или никакого.
"""
import importlib.util as _iu
import io
import os
import py_compile
import shutil
import sys
import time

sys.path.insert(0, r"C:\sender")
ПУТЬ = r"C:\sender\sender\ai_letter.py"
т = io.open(ПУТЬ, encoding="utf-8").read()
СТАР = """        _вставим = _ролик or _ролик_люб
        if (_ролик_люб and _ролик
                and _ролик_люб.get('продукт') != _ролик.get('продукт')):
            _вставим = _ролик_люб
"""
НОВ = """        _вставим = _ролик or _ролик_люб
        if (_ролик_люб and _ролик
                and _ролик_люб.get('продукт') != _ролик.get('продукт')):
            _вставим = _ролик_люб
        # РОЛИК ДРУГОГО СТАНКА — ТОЛЬКО КОГДА ПИСЬМО ЕГО НАЗЫВАЕТ (владелец
        # 12.10). Без строки «ДВА ЭТАПА» второго станка в письме нет, и ролик
        # сортировки вешался на рентгеновский текст («Кизлярские сыры»).
        # Тогда — свой станок или ничего.
        if (_вставим and (_вставим.get('станок') or _ст) != _ст
                and not (_чем2 and _ролик)):
            _вставим = _ролик
"""
if "ТОЛЬКО КОГДА ПИСЬМО ЕГО НАЗЫВАЕТ" in т:
    print("уже стоит")
    print("=== РОЛИК: УЖЕ БЫЛО ===")
    sys.exit(0)
if т.count(СТАР) != 1:
    print("якорь не найден (%d)" % т.count(СТАР))
    print("=== РОЛИК: НЕ ПРИМЕНЁН ===")
    sys.exit(0)
бэкап = ПУТЬ + ".bak-%d" % int(time.time())
shutil.copy2(ПУТЬ, бэкап)
io.open(ПУТЬ, "w", encoding="utf-8").write(т.replace(СТАР, НОВ))
try:
    py_compile.compile(ПУТЬ, doraise=True)
    сп = _iu.spec_from_file_location("al_rol", ПУТЬ)
    м = _iu.module_from_spec(сп)
    sys.modules["al_rol"] = м
    сп.loader.exec_module(м)
    from sender.ai_quota import build_ai_quota
    from sender.config import Config
    from sender.store import Store
    cfg = Config.load(r"C:\sender\sender.yaml")
    store = Store(r"C:\sender\sender.db")
    q = build_ai_quota(store, cfg)
    with store._lock:
        rid = store._conn.execute("SELECT id FROM recipients WHERE lower(email)="
                                  "'halal@darman.ru'").fetchone()[0]
    req = q._request(store.get_recipient(rid))
    блок = м._recipient_block(0, req, "meyer_rentgen")
    чужой = "Ролик снят на другом нашем станке" in блок
    ссылка = "rutube" in блок
    print("Кизлярские сыры: ссылка в карточке %s, ролик чужого станка %s"
          % (ссылка, чужой))
    assert not чужой
    print("ПРИМЕНЕНО, бэкап %s" % os.path.basename(бэкап))
    print("=== РОЛИК: ПРИМЕНЁН ===")
except Exception as e:  # noqa: BLE001
    shutil.copy2(бэкап, ПУТЬ)
    print("ОТКАТ: %s" % e)
    print("=== РОЛИК: ОТКАТ ===")

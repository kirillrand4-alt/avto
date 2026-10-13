# -*- coding: utf-8 -*-
"""confirm._recent_contact: повтор от Meyer раньше 90 дней (владелец 13.10).

После письма от КЦ — сразу; компании с новым паспортом (povtornoe) — через
30 дней; ответившим — по-прежнему 90. Правка по якорю, бэкап, py_compile, откат.
"""
import io
import py_compile
import shutil
import sys
import time
ПУТЬ = r"C:\\sender\\sender\\confirm.py"
т = io.open(ПУТЬ, encoding="utf-8").read()
if "ПОВТОР ОТ MEYER РАНЬШЕ 90 ДНЕЙ" in т:
    print("=== ПОВТОР: УЖЕ БЫЛО ===")
    sys.exit(0)
СТАР = '        в_окне = self._v_okne(str(last.get("ts") or ""))\n        if в_окне is None:\n            return last  # дата не парсится → консервативно считаем недавним\n        return last if в_окне else None\n'
НОВ = '        в_окне = self._v_okne(str(last.get("ts") or ""))\n        if в_окне is None:\n            return last  # дата не парсится → консервативно считаем недавним\n        if в_окне and self._povtor_razreshen(email, last):\n            return None\n        return last if в_окне else None\n\n    # ПОВТОР ОТ MEYER РАНЬШЕ 90 ДНЕЙ (владелец 13.10). Два случая:\n    #  * прошлое письмо на этот адрес было от КЦ (компрессоры) — «если\n    #    направление было кц, то точно пишем ещё раз от мейера»: это другое\n    #    предложение, окно не держим;\n    #  * компании дали новый паспорт (extra.povtornoe — все её адреса уже\n    #    отработаны) — повтор через 30 дней, а не через 90.\n    # Только для писем Meyer (extra.division) и только тем, кто нам НЕ отвечал:\n    # ответившему (лид есть) повтор автоматом не шлём — окно остаётся 90.\n    _КЦ_КАМПАНИИ = {1, 5, 6, 9, 10}\n    _ПОВТОР_ДНЕЙ = 30\n\n    def _povtor_razreshen(self, email: str, last: dict) -> bool:\n        try:\n            import json as _json\n            from datetime import datetime, timedelta, timezone\n            with self._store._lock:\n                c = self._store._conn\n                р = c.execute("SELECT inn, extra_json FROM recipients WHERE lower(email)=?",\n                              (str(email or "").strip().lower(),)).fetchone()\n                if р is None:\n                    return False\n                ex = _json.loads(р["extra_json"] or "{}") or {}\n                if str(ex.get("division") or "") != "meyer":\n                    return False\n                if р["inn"] and c.execute("SELECT 1 FROM leads WHERE inn=? LIMIT 1",\n                                          (р["inn"],)).fetchone():\n                    return False\n                камп = last.get("campaign_id")\n                if камп is not None:\n                    if int(камп) in self._КЦ_КАМПАНИИ:\n                        return True\n                    имя = c.execute("SELECT name FROM campaigns WHERE id=?", (камп,)).fetchone()\n                    if имя and "КЦ" in str(имя[0] or ""):\n                        return True\n            if ex.get("povtornoe"):\n                then = datetime.fromisoformat(str(last.get("ts") or "").replace("Z", "+00:00"))\n                if then.tzinfo is None:\n                    then = then.replace(tzinfo=timezone.utc)\n                return datetime.now(timezone.utc) - then >= timedelta(days=self._ПОВТОР_ДНЕЙ)\n        except Exception:  # noqa: BLE001 - мок-store или битые данные: не разрешаем\n            return False\n        return False\n'
if т.count(СТАР) != 1:
    print("якорь: %d" % т.count(СТАР))
    print("=== ПОВТОР: НЕ ПРИМЕНЕНО ===")
    sys.exit(0)
бэкап = ПУТЬ + ".bak-%d" % int(time.time())
shutil.copy2(ПУТЬ, бэкап)
io.open(ПУТЬ, "w", encoding="utf-8").write(т.replace(СТАР, НОВ))
try:
    py_compile.compile(ПУТЬ, doraise=True)
except Exception as е:  # noqa: BLE001
    shutil.copy2(бэкап, ПУТЬ)
    print("сбой, откат: %s" % е)
    print("=== ПОВТОР: ОТКАТ ===")
    sys.exit(0)
print("бэкап: %s" % бэкап)
print("=== ПОВТОР: ПРИМЕНЕНО ===")

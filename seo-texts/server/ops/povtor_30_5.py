# -*- coding: utf-8 -*-
"""confirm.py: заслон «сделка в работе» по направлениям (владелец 14.10). Правка по якорю, бэкап, py_compile, откат."""
import io
import py_compile
import shutil
import sys
import time
ПУТЬ = r"C:\\sender\\sender\\confirm.py"
т = io.open(ПУТЬ, encoding="utf-8").read()
if "ПОВТОР БЕЗ ОТВЕТА (владелец 14.10)" in т:
    print("=== ПОВТОР 30/5 ДНЕЙ: УЖЕ БЫЛО ===")
    sys.exit(0)
ПАРЫ = [('                if р["inn"] and c.execute("SELECT 1 FROM leads WHERE inn=? LIMIT 1",\n                                          (р["inn"],)).fetchone():\n                    return False', '                # «если не было ответа» (владелец 14.10): автоответ и отпуск —\n                # не ответ; живой лид (компания отвечала) — повтор не шлём\n                if р["inn"] and c.execute(\n                        "SELECT 1 FROM leads WHERE inn=? AND status NOT IN "\n                        "(\'avtootvet\',\'v_otpuske\',\'deleted\') AND coalesce(reply_kind,\'\') "\n                        "NOT IN (\'auto_reply\') LIMIT 1", (р["inn"],)).fetchone():\n                    return False'), ('            if ex.get("povtornoe"):\n                then = datetime.fromisoformat(str(last.get("ts") or "").replace("Z", "+00:00"))\n                if then.tzinfo is None:\n                    then = then.replace(tzinfo=timezone.utc)\n                return datetime.now(timezone.utc) - then >= timedelta(days=self._ПОВТОР_ДНЕЙ)', '            # ПОВТОР БЕЗ ОТВЕТА (владелец 14.10): «повторный контакт, если прошло\n            # 30 дней, даже на ту же почту, а если не было ответа — на другую\n            # почту можем писать хоть через 5 дней». Новый паспорт не нужен.\n            then = datetime.fromisoformat(str(last.get("ts") or "").replace("Z", "+00:00"))\n            if then.tzinfo is None:\n                then = then.replace(tzinfo=timezone.utc)\n            прошло = datetime.now(timezone.utc) - then\n            тот_же = (str(last.get("email") or "").strip().lower()\n                      == str(email or "").strip().lower())\n            return прошло >= timedelta(days=self._ПОВТОР_ДНЕЙ if тот_же else 5)')]
for с, _н in ПАРЫ:
    if т.count(с) != 1:
        print("якорь (%d): %r" % (т.count(с), с[:120]))
        print("=== ПОВТОР 30/5 ДНЕЙ: НЕ ПРИМЕНЕНО ===")
        sys.exit(0)
бэкап = ПУТЬ + ".bak-%d" % int(time.time())
shutil.copy2(ПУТЬ, бэкап)
for с, н in ПАРЫ:
    т = т.replace(с, н)
io.open(ПУТЬ, "w", encoding="utf-8").write(т)
try:
    py_compile.compile(ПУТЬ, doraise=True)
except Exception as е:  # noqa: BLE001
    shutil.copy2(бэкап, ПУТЬ)
    print("сбой, откат: %s" % е)
    print("=== ПОВТОР 30/5 ДНЕЙ: ОТКАТ ===")
    sys.exit(0)
print("бэкап: %s" % бэкап)
print("=== ПОВТОР 30/5 ДНЕЙ: ПРИМЕНЕНО ===")

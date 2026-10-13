# -*- coding: utf-8 -*-
"""confirm._guard: компании, которая отвечала (живой лид), холодных не шлём (13.10)."""
import io
import py_compile
import shutil
import sys
import time
ПУТЬ = r"C:\\sender\\sender\\confirm.py"
т = io.open(ПУТЬ, encoding="utf-8").read()
if "ХОЛОДНЫХ БОЛЬШЕ НЕ ШЛЁМ" in т:
    print("=== ОТВЕЧАЛИ: УЖЕ БЫЛО ===")
    sys.exit(0)
ПАРЫ = [('    def _guard(self, *, inn: Optional[str], email: str) -> Optional[str]:', '    def _guard(self, *, inn: Optional[str], email: str,\n               otvet: bool = False) -> Optional[str]:'), ('        entry = self._suppression_hit(inn=inn, email=email)\n        if entry is not None:\n            return f"suppressed:{entry.reason}"\n', '        entry = self._suppression_hit(inn=inn, email=email)\n        if entry is not None:\n            return f"suppressed:{entry.reason}"\n        # КОМПАНИЯ НАМ ОТВЕЧАЛА — ХОЛОДНЫХ БОЛЬШЕ НЕ ШЛЁМ (владелец 13.10: «если\n        # отвечала, то вообще не надо им писать»). Ответ — живой лид по ИНН;\n        # автоответ и «в отпуске» ответом не считаются. Черновик НАШЕГО ответа\n        # в переписке (submit_reply, otvet=True) это правило не трогает.\n        if not otvet:\n            лид = self._otvechali(inn)\n            if лид:\n                return f"otvechali:{лид}"\n'), ('        blocked = self._guard(inn=inn, email=reply_to)', '        blocked = self._guard(inn=inn, email=reply_to, otvet=True)'), ('    def _povtor_razreshen(self, email: str, last: dict) -> bool:', '    def _otvechali(self, inn: Optional[str]) -> Optional[str]:\n        """Статус живого лида компании (она нам отвечала) или None."""\n        цифры = "".join(c for c in str(inn or "") if c.isdigit())\n        if not цифры:\n            return None\n        try:\n            with self._store._lock:\n                р = self._store._conn.execute(\n                    "SELECT status FROM leads WHERE inn=? AND status NOT IN "\n                    "(\'avtootvet\',\'v_otpuske\',\'deleted\') AND coalesce(reply_kind,\'\') "\n                    "NOT IN (\'auto_reply\') LIMIT 1", (цифры,)).fetchone()\n        except Exception:  # noqa: BLE001 - мок-store без таблицы лидов\n            return None\n        return str(р[0]) if р else None\n\n    def _povtor_razreshen(self, email: str, last: dict) -> bool:')]
for с, _н in ПАРЫ:
    if т.count(с) != 1:
        print("якорь (%d): %r" % (т.count(с), с[:60]))
        print("=== ОТВЕЧАЛИ: НЕ ПРИМЕНЕНО ===")
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
    print("=== ОТВЕЧАЛИ: ОТКАТ ===")
    sys.exit(0)
print("бэкап: %s" % бэкап)
print("=== ОТВЕЧАЛИ: ПРИМЕНЕНО ===")

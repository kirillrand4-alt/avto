# -*- coding: utf-8 -*-
"""Выкатить правку пробы: метод в store.py по якорю + новый addr_probe.py.

store.py на сервере НАМНОГО новее репозитория (228963 против 200043 байт) —
его правим только по якорю. addr_probe.py совпал с репозиторием побайтно
(md5 fcbe9e9a860f), поэтому его кладём целиком из подготовленного файла.

Порядок важен: addr_probe зовёт store.mark_skipped_if_not_terminal, поэтому
сначала store. Не легло в store — addr_probe не трогаем вовсе.
"""
import hashlib
import io
import os
import py_compile
import shutil
import time

СЕРВЕР = r"C:\sender\sender"
СКЛАД = r"C:\sender\_ops"

МЕТОД = '''    def mark_skipped_if_not_terminal(self, message_id: int, reason: str) -> bool:
        """Снять письмо с отправки, не трогая терминальные статусы. → снято?

        ``mark_skipped`` пишет 'skipped' безусловно, и вызвать его на письме,
        которое секунду назад ушло, — значит потерять факт отправки: письмо
        перестанет считаться отправленным, правило 90 дней его не увидит, и
        компания получит второе письмо. Здесь проверка и запись — один UPDATE,
        разъехаться им негде.
        """
        now_iso = _now_iso()
        with self.transaction() as conn:
            cur = conn.execute(
                """UPDATE messages
                      SET status='skipped', last_error=?, updated_at=?
                    WHERE id=? AND status NOT IN ('sent','skipped','failed')""",
                (reason, now_iso, int(message_id)),
            )
            return cur.rowcount == 1

'''
ЯКОРЬ = "    def mark_pending_review(self, message_id: int) -> None:"


def выкатить(имя, новый_текст, проверка=None):
    путь = os.path.join(СЕРВЕР, имя)
    копия = путь + ".bak-%d" % int(time.time())
    shutil.copy2(путь, копия)
    io.open(путь, "w", encoding="utf-8", newline="").write(новый_текст)
    try:
        py_compile.compile(путь, doraise=True)
        if проверка and проверка not in новый_текст:
            raise RuntimeError("контрольная строка не найдена: %s" % проверка)
        print("  %s: легло, компиляция ОК (копия %s)"
              % (имя, os.path.basename(копия)))
        return True
    except Exception as e:  # noqa: BLE001
        shutil.copy2(копия, путь)
        print("  %s: ОТКАТ — %s" % (имя, e))
        return False


print("=== store.py ===")
sp = os.path.join(СЕРВЕР, "store.py")
т = io.open(sp, encoding="utf-8").read()
ок_store = False
if "mark_skipped_if_not_terminal" in т:
    print("  метод уже на месте — не трогаем")
    ок_store = True
elif т.count(ЯКОРЬ) != 1:
    print("  НЕ ПРАВИМ: якорь встречается %d раз" % т.count(ЯКОРЬ))
else:
    ок_store = выкатить("store.py", т.replace(ЯКОРЬ, МЕТОД + ЯКОРЬ),
                        проверка="mark_skipped_if_not_terminal")

print("\n=== addr_probe.py ===")
if not ок_store:
    print("  пропущено: без метода в store правка бессмысленна")
else:
    новый = os.path.join(СКЛАД, "addr_probe.py.new")
    if not os.path.exists(новый):
        print("  НЕТ подготовленного файла %s" % новый)
    else:
        т2 = io.open(новый, encoding="utf-8").read()
        текущий = io.open(os.path.join(СЕРВЕР, "addr_probe.py"), "rb").read()
        print("  боевой md5=%s, новый md5=%s"
              % (hashlib.md5(текущий).hexdigest()[:12],
                 hashlib.md5(т2.encode("utf-8")).hexdigest()[:12]))
        выкатить("addr_probe.py", т2, проверка="СНЯТЬ_С_ОЧЕРЕДИ")

print("\n=== ЧТО СТАЛО ===")
for имя, метка in (("store.py", "mark_skipped_if_not_terminal"),
                   ("addr_probe.py", "СНЯТЬ_С_ОЧЕРЕДИ"),
                   ("leaddesk.py", "КАНОН_МЕТОК")):
    т3 = io.open(os.path.join(СЕРВЕР, имя), encoding="utf-8").read()
    print("  %-16s %s %s" % (имя, "ЕСТЬ" if метка in т3 else "НЕТ ", метка))

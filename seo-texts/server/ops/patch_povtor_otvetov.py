# -*- coding: utf-8 -*-
"""ОТВЕТ ИЗ КАРТОЧКИ ЛИДА НЕ ТЕРЯЕТСЯ МОЛЧА (владелец 09.11: «применяй»).

06.11 два ответа менеджеров Meyer (Николай, Максим) не ушли: отправка из
карточки лида не нашла свободного ящика направления, черновик остался в
очереди подтверждения, а пометку «не ушло» никто не заметил. Висели три дня.

Правка в api/app.py по якорю: рядом с потоком авто-валидации заводится поток
«повтор ответов из карточки лида». Раз в 10 минут (confirm.povtor_otvetov_sec)
он берёт черновики kind='reply', написанные оператором в карточке лида
(review OPERATOR), старше 5 минут и не старше 7 дней, и штатно вызывает
confirm.approve. Заслоны (стоп-лист, отписка, жалоба, нет ящика) внутри approve
и остаются в силе: не прошло — черновик ждёт следующего круга.

Только якорь, .bak, py_compile, откат. [--primenit]
"""
import io
import os
import py_compile
import sys
import time

ФАЙЛ = r"C:\sender\sender\api\app.py"
ПРИМЕНИТЬ = "--primenit" in sys.argv

ПРИМЕНИТЬ = "--primenit" in sys.argv

ПАРЫ = [
    ('''        _th.Thread(target=_auto_validate_loop, daemon=True,
                   name="auto-validate").start()
''',
     '''        _th.Thread(target=_auto_validate_loop, daemon=True,
                   name="auto-validate").start()

        # ПОВТОР ОТВЕТОВ ИЗ КАРТОЧКИ ЛИДА (владелец 09.11). Ответ оператора
        # уходит сразу, но если в ту минуту не нашлось ящика направления
        # (06.11 ящики Meyer заняли напоминания), черновик оставался в
        # очереди молча и висел днями. Теперь его добивает этот круг тем же
        # approve - все заслоны внутри него.
        def _povtor_otvetov_loop():
            from datetime import datetime as _dt, timedelta as _td, timezone as _tz
            interval = float(deps.config.get(
                "confirm.povtor_otvetov_sec", 600) or 600)
            _time.sleep(120)
            while True:
                try:
                    with deps.store._lock:
                        _ids = [r[0] for r in deps.store._conn.execute(
                            "SELECT id FROM confirm_reviews"
                            " WHERE status='pending' AND kind='reply'"
                            "   AND panel_json LIKE '%OPERATOR%'"
                            "   AND created_at <= ? AND created_at >= ?"
                            " ORDER BY id LIMIT 50",
                            ((_dt.now(_tz.utc).replace(tzinfo=None) - _td(minutes=5)).isoformat(),
                             (_dt.now(_tz.utc).replace(tzinfo=None) - _td(days=7)).isoformat())).fetchall()]
                    for _id in _ids:
                        try:
                            _ok = deps.confirm.approve(
                                int(_id), operator="авто-повтор: ответ из карточки лида")
                            logger.info("повтор ответа #%s: %s", _id, _ok)
                        except Exception as _e:  # noqa: BLE001 - ждёт следующего круга
                            logger.info("повтор ответа #%s не прошёл: %s", _id, str(_e)[:160])
                except Exception:  # noqa: BLE001 - круг не роняет поток
                    logger.exception("повтор ответов: проход не удался")
                _time.sleep(interval)

        _th.Thread(target=_povtor_otvetov_loop, daemon=True,
                   name="povtor-otvetov").start()
'''),
]

т = io.open(ФАЙЛ, encoding="utf-8").read()
print("файл: %d Б, строк %d" % (len(т.encode("utf-8")), len(т.splitlines())))
ошибок = 0
for i, (стар, нов) in enumerate(ПАРЫ, 1):
    n = т.count(стар)
    print("   якорь %d: вхождений %d %s" % (i, n, "ок" if n == 1 else "ОТКАЗ"))
    if n != 1:
        ошибок += 1
if ошибок:
    print("\nякоря не уникальны — не трогаю файл")
    raise SystemExit(1)

новый = т
for стар, нов in ПАРЫ:
    новый = новый.replace(стар, нов, 1)
print("\nстанет строк: %d (было %d)" % (len(новый.splitlines()),
                                        len(т.splitlines())))
if not ПРИМЕНИТЬ:
    print("\n[сухой прогон] применить — с ключом --primenit")
    raise SystemExit(0)

запас = "%s.bak-%d" % (ФАЙЛ, int(time.time()))
io.open(запас, "w", encoding="utf-8").write(т)
print("бэкап: %s" % запас)
with io.open(ФАЙЛ, "w", encoding="utf-8") as f:
    f.write(новый)
    f.flush()
    os.fsync(f.fileno())
try:
    py_compile.compile(ФАЙЛ, doraise=True)
    print("py_compile: ок")
except Exception as e:                                        # noqa: BLE001
    io.open(ФАЙЛ, "w", encoding="utf-8").write(т)
    print("КОМПИЛЯЦИЯ УПАЛА, откатил: %s" % str(e)[:200])
    raise SystemExit(1)
print("\n=== ИТОГ ===")
print("правки на месте. Нужен перезапуск службы, чтобы панель их подхватила.")

# -*- coding: utf-8 -*-
"""Сузить сверку приговоров до тех, кто ещё в работе, и перевести на 12 часов.

Владелец 01.09: «не надо в принципе столько вердиктов, письма же ушли уже,
пусть проверяет тех кто подтвердил или ждёт, раз в 12 часов».

Было: в обогащение уходили ВСЕ приговоры из addr_probe — 5337 обновлений
каждый час по базе в 841 МБ. Полезной работы при этом ноль-пять писем за
прогон. Именно эти пять тысяч и держали пишущий замок enrich.db.

Стало: берём приговоры по адресам, у которых есть ЖИВАЯ карточка в очереди
(pending/approved/edited), плюс — страховка — приговоры, которых в
обогащении ещё нет вовсе. Без второго правило теряет смысл: адрес, чью
карточку уже отправили, иначе никогда не попал бы в обогащение и вернулся
бы в новую партию генерации. Проверка «чего ещё нет» — это ЧТЕНИЕ
enrich.db, пишущий замок она не берёт.

Файл общий, поэтому: сверяем якорь, кладём .bak-<время>, правим, проверяем
компиляцию, при неудаче откатываем.

По умолчанию СУХОЙ ПРОГОН. Запуск: python pochinit_sverku.py [--primenit]
"""
import io
import os
import py_compile
import shutil
import subprocess
import sys
import time

П = r"C:\sender\server\ops\sverka_prigovorov.py"
ПРИМЕНИТЬ = "--primenit" in sys.argv or "--apply" in sys.argv

ЯКОРЬ = '''все_приговоры = [dict(r) for r in c.execute(
    "SELECT email, verdict, answer FROM addr_probe WHERE verdict IN (?,?)",
    ПРИГОВОР)]'''

ЗАМЕНА = '''# ТОЛЬКО ТЕ, КТО ЕЩЁ В РАБОТЕ (владелец 01.09: «не надо в принципе
# столько вердиктов, письма же ушли уже, пусть проверяет тех кто
# подтвердил или ждёт»). Здесь брались ВСЕ приговоры из addr_probe, и все
# они уходили в обогащение: 5337 обновлений каждый час по базе в 841 МБ,
# при том что снималось ноль-пять писем за прогон. Эти пять тысяч и
# держали пишущий замок enrich.db — прогон 15:11 доработал к 16:26, и
# следующий стартовал раньше окончания предыдущего.
#
# СТРАХОВКА ВТОРЫМ УСЛОВИЕМ обязательна. Одной очередью ограничиться
# нельзя: адрес, чью карточку уже отправили, выпал бы из обогащения
# навсегда и вернулся бы в новую партию генерации — ровно та беда, ради
# которой сверка и заведена. Поэтому берём ещё и приговоры, которых в
# обогащении нет вовсе. Это ЧТЕНИЕ enrich.db, пишущий замок оно не берёт.
_в_работе = {str(r["email"] or "").strip().lower() for r in c.execute(
    "SELECT DISTINCT r.email FROM confirm_reviews cr "
    "  JOIN recipients r ON r.id=cr.recipient_id "
    " WHERE cr.status IN ('pending','approved','edited')")}
_уже_в_обогащении = set()
try:
    _об = sqlite3.connect("file:%s?mode=ro" % ОБОГ, uri=True, timeout=120)
    _уже_в_обогащении = {str(e or "").strip().lower() for (e,) in _об.execute(
        "SELECT email FROM emails WHERE COALESCE(probe_verdict,'') <> ''")}
    _об.close()
except Exception as _ex:                                      # noqa: BLE001
    print("обогащение не прочиталось (%s) — беру все приговоры"
          % str(_ex)[:70])
все_приговоры = [dict(r) for r in c.execute(
    "SELECT email, verdict, answer FROM addr_probe WHERE verdict IN (?,?)",
    ПРИГОВОР)
    if (not _уже_в_обогащении
        or str(r["email"] or "").strip().lower() in _в_работе
        or str(r["email"] or "").strip().lower() not in _уже_в_обогащении)]
print("в работе адресов: %d | уже в обогащении: %d | к записи: %d"
      % (len(_в_работе), len(_уже_в_обогащении), len(все_приговоры)))'''

т = io.open(П, encoding="utf-8", errors="replace").read()
есть_якорь = ЯКОРЬ in т
уже_правлен = "ТОЛЬКО ТЕ, КТО ЕЩЁ В РАБОТЕ" in т

шаги = []
if уже_правлен:
    шаги.append("файл уже правлен — второй раз не трогаю")
elif not есть_якорь:
    шаги.append("ЯКОРЬ НЕ НАЙДЕН — файл изменился, правку не применяю")
elif ПРИМЕНИТЬ:
    бэкап = П + ".bak-%d" % int(time.time())
    shutil.copy2(П, бэкап)
    шаги.append("бэкап: %s" % os.path.basename(бэкап))
    io.open(П, "w", encoding="utf-8").write(т.replace(ЯКОРЬ, ЗАМЕНА, 1))
    try:
        py_compile.compile(П, doraise=True)
        шаги.append("правка применена, компилируется")
    except Exception as ex:                                    # noqa: BLE001
        shutil.copy2(бэкап, П)
        шаги.append("НЕ КОМПИЛИРУЕТСЯ (%s) — откатил из бэкапа"
                    % str(ex)[:80])
else:
    шаги.append("якорь найден, готов править (сухой прогон)")

# расписание: раз в 12 часов
расписание = []
def пш(ком):
    r = subprocess.run(["powershell", "-NoProfile", "-Command", ком],
                       capture_output=True, text=True, timeout=120)
    return (r.stdout or "").strip() or (r.stderr or "").strip()[:200]

было_распис = пш(
    "(Get-ScheduledTask -TaskName 'sender-sverka-prigovorov').Triggers | "
    "ForEach-Object { \"$($_.CimClass.CimClassName) старт $($_.StartBoundary) "
    "повтор $($_.Repetition.Interval)\" }")
расписание.append("было: %s" % (было_распис or "?"))
if ПРИМЕНИТЬ:
    пш("$т = New-ScheduledTaskTrigger -Once -At (Get-Date -Hour 5 -Minute 11 "
       "-Second 0) -RepetitionInterval (New-TimeSpan -Hours 12); "
       "Set-ScheduledTask -TaskName 'sender-sverka-prigovorov' -Trigger $т "
       "| Out-Null")
    стало = пш(
        "(Get-ScheduledTask -TaskName 'sender-sverka-prigovorov').Triggers | "
        "ForEach-Object { \"$($_.CimClass.CimClassName) старт "
        "$($_.StartBoundary) повтор $($_.Repetition.Interval)\" }")
    расписание.append("стало: %s" % (стало or "?"))

print("=" * 70)
print("=== СВОДКА: ПОЧИНКА СВЕРКИ ПРИГОВОРОВ ===")
print("режим: %s" % ("ПРИМЕНЕНО" if ПРИМЕНИТЬ else "СУХОЙ ПРОГОН"))
print("")
print("правка скрипта:")
for с in шаги:
    print("   " + с)
print("")
print("расписание:")
for с in расписание:
    print("   " + с)

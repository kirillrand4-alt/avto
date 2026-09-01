# -*- coding: utf-8 -*-
"""Правка по якорям: increment_sent заводит строку вместо StoreError,
и сбой счётчика больше не отменяет запись события 'sent'.

Без аргумента primenit только показывает. Делает .bak, проверяет py_compile,
откатывается при ошибке. Якорь обязан быть единственным."""
import hashlib
import io
import os
import py_compile
import shutil
import sys
import time

ПРИМЕНИТЬ = "primenit" in sys.argv
ТС = time.strftime("%Y%m%d-%H%M%S")

СТАРОЕ_STORE = '''            if row is None:
                raise StoreError(f"mailbox_state not found: {mailbox_id}")
'''
НОВОЕ_STORE = '''            if row is None:
                # Ящик ещё ни разу не отправлял. Раньше здесь летел StoreError и
                # уносил с собой ВСЁ, что стоит в sender.send ПОСЛЕ счётчика:
                # событие 'sent' не писалось, потому что его except ловит только
                # TypeError. Письмо при этом уже ушло по SMTP и было помечено
                # mark_sent. Отсюда 31.08: 90 писем с нового ящика лежат в
                # messages как sent, событий 'sent' ноль, sent_total ноль, и
                # указатель ротации (он читает события) не сдвинулся ни разу —
                # вся пачка из 743 подтверждений ушла с одного адреса.
                # Заводим строку вместо исключения: day_key заведомо старый,
                # чтобы ниже посчитались первый день рампы и счётчик суток.
                conn.execute(
                    "INSERT OR IGNORE INTO mailbox_state(mailbox_id, provider, "
                    "day_key, sent_today, sent_total, ramp_day, daily_limit, "
                    "paused, pause_reason, updated_at) "
                    "VALUES(?, '', '1970-01-01', 0, 0, 0, 0, 0, NULL, ?)",
                    (mailbox_id, updated),
                )
                row = conn.execute(
                    "SELECT * FROM mailbox_state WHERE mailbox_id=?", (mailbox_id,)
                ).fetchone()
            if row is None:
                raise StoreError(f"mailbox_state not found: {mailbox_id}")
'''

СТАРОЕ_SENDER = '''        try:
            self.store.increment_sent(
                mailbox_id, now=sent_at, day_key=self._day_key(sent_at))
        except TypeError:
            self.store.increment_sent(mailbox_id, now=sent_at)
'''
НОВОЕ_SENDER = '''        try:
            self.store.increment_sent(
                mailbox_id, now=sent_at, day_key=self._day_key(sent_at))
        except TypeError:
            self.store.increment_sent(mailbox_id, now=sent_at)
        except Exception:  # noqa: BLE001
            # Счётчик суток важен, но событие 'sent' важнее: по нему считается
            # статистика и по нему же ходит указатель ротации ящиков. Раньше
            # любая ошибка счётчика уносила append_event ниже, и отправка
            # исчезала из всех журналов, кроме messages.
            logger.exception("счётчик отправки не обновился: %s", mailbox_id)
'''

# Метка применённой правки: строка, которой в СТАРОМ коде нет ни в одном виде.
МЕТКИ = {r"C:\sender\sender\store.py": "уносил с собой ВСЁ, что стоит в sender.send",
         r"C:\sender\sender\sender.py": "счётчик отправки не обновился"}

ФАЙЛЫ = [(r"C:\sender\sender\store.py", СТАРОЕ_STORE, НОВОЕ_STORE),
         (r"C:\sender\sender\sender.py", СТАРОЕ_SENDER, НОВОЕ_SENDER)]

план = []
for путь, ст, нов in ФАЙЛЫ:
    t = io.open(путь, encoding="utf-8").read()
    n = t.count(ст)
    sha = hashlib.sha1(t.encode()).hexdigest()[:12]
    print("=== %s ===" % os.path.basename(путь))
    print("  sha1 %s, размер %d" % (sha, len(t)))
    print("  якорь встречается: %d %s" % (n, "ОК" if n == 1 else "!!! НЕ ЕДИНСТВЕННЫЙ"))
    if МЕТКИ[путь] in t:
        print("  правка УЖЕ применена (метка найдена) — пропускаю")
        continue
    if n != 1:
        print("  ОТКАЗ по этому файлу")
        continue
    план.append((путь, ст, нов, t))

print("\n=== ПЛАН: править файлов %d ===" % len(план))
if ПРИМЕНИТЬ and план:
    for путь, ст, нов, t in план:
        bak = "%s.bak-%s" % (путь, ТС)
        shutil.copy2(путь, bak)
        io.open(путь, "w", encoding="utf-8").write(t.replace(ст, нов))
        try:
            py_compile.compile(путь, doraise=True)
            print("  %s: правка ок, .bak-%s" % (os.path.basename(путь), ТС))
        except Exception as ex:
            shutil.copy2(bak, путь)
            print("  %s: py_compile НЕ ПРОШЁЛ, ОТКАЧЕНО: %s"
                  % (os.path.basename(путь), str(ex)[:90]))

print("\n=== ИТОГ ===")
print("  РЕЖИМ: %s" % ("ПРИМЕНЕНО" if ПРИМЕНИТЬ else "показ без изменений"))
print("  после правки нужен перезапуск службы — код грузится при старте")

# -*- coding: utf-8 -*-
"""Приём входящих пропускал ответы, которые продажник успел прочитать в веб-почте:
задача RuspromInboxPoll шла штатным UNSEEN (владелец 15.10: «этого я не видел в
панели» — «Байкальский травник» и ещё 2). Добавляем в задачу --days 2: берём всё
за двое суток, повтор отсекает dedup события. Плюс разовый добор прямо сейчас."""
import io
import shutil
import subprocess
import sys
import time
П = r"C:\sender\inbox_poll_task.py"
т = io.open(П, encoding="utf-8").read()
с = "'--keep-unread', '--no-drafts', '--batch', '100']"
if "'--days'" not in т:
    assert т.count(с) == 1
    shutil.copy2(П, П + ".bak-%d" % int(time.time()))
    io.open(П, "w", encoding="utf-8").write(т.replace(с, "'--keep-unread', '--no-drafts', '--batch', '100', '--days', '2']"))
    print("задача приёма: добавлено --days 2")
else:
    print("задача приёма: --days уже есть")
р = subprocess.run([sys.executable, П], cwd=r"C:\sender", capture_output=True, text=True, timeout=1500)
print("разовый проход: код", р.returncode)
print("=== ПРИЁМ ВХОДЯЩИХ ===")

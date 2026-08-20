# -*- coding: utf-8 -*-
r"""Забираются ли входящие письма: когда был последний обход ящиков.

Ответы клиентов попадают в ленту лида из events (reply/reply_auto/...),
которые кладёт imap_watcher. Если обход не запускается, лента показывает
только наши исходящие — ровно то, что видит владелец.
"""
import json
import os
import sqlite3
import subprocess
import time

БД = r'C:\sender\sender.db'
итог = {}

c = sqlite3.connect('file:%s?mode=ro' % БД.replace('\\', '/'), uri=True)
c.row_factory = sqlite3.Row
try:
    итог['события_по_типам'] = dict(c.execute(
        "select event_type, count(*) from events "
        "where event_type in ('reply','reply_auto','complaint','dsn','bounce') "
        'group by event_type').fetchall())
    r = c.execute("select max(event_ts) from events where event_type like 'reply%'").fetchone()
    итог['последний_ответ'] = r[0] if r else None
    итог['последнее_любое_событие'] = c.execute(
        'select max(event_ts) from events').fetchone()[0]
    итог['свежие_ответы'] = [dict(x) for x in c.execute(
        "select id, event_ts, mailbox_id, recipient_id, event_type, "
        "substr(coalesce(detail_json,''),1,150) d from events "
        "where event_type like 'reply%' order by event_ts desc limit 6")]
    итог['ящиков'] = c.execute('select count(*) from mailboxes').fetchone()[0]
except Exception as e:  # noqa: BLE001
    итог['ошибка_бд'] = '%s: %s' % (type(e).__name__, e)
c.close()

# кто вообще ходит за почтой: служба, планировщик, процесс
try:
    out = subprocess.run(
        ['powershell', '-NoProfile', '-Command',
         "Get-ScheduledTask | Where-Object {$_.TaskName -match 'imap|inbox|pochta|reply|mail'} | "
         "%{ $_.TaskName + ' | ' + $_.State + ' | ' + "
         "($_.Actions | %{$_.Execute + ' ' + $_.Arguments}) };"
         "'---';"
         "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
         "Where-Object {$_.CommandLine -match 'imap|watch|inbox'} | "
         "%{ $_.ProcessId.ToString() + ' ' + $_.CommandLine.Substring(0,[Math]::Min(120,$_.CommandLine.Length)) }"],
        capture_output=True, text=True, timeout=120)
    итог['планировщик_и_процессы'] = [x.strip() for x in out.stdout.splitlines() if x.strip()]
except Exception as e:  # noqa: BLE001
    итог['планировщик'] = str(e)[:120]

# логи обхода
for п in (r'C:\sender\imap.log', r'C:\sender\imap_watcher.out',
          r'C:\sender\sender.log', r'C:\sender\panel.log'):
    if os.path.exists(п):
        итог.setdefault('логи', {})[п] = {
            'возраст_мин': round((time.time() - os.path.getmtime(п)) / 60, 1),
            'кб': round(os.path.getsize(п) / 1024)}
print(json.dumps(итог, ensure_ascii=False, indent=1))

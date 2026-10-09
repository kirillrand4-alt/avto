# -*- coding: utf-8 -*-
"""Автозапуск копии панели Meyer (C:\\centro2, порт 8016) при старте Windows (владелец 09.10: «да»).

09.10 после перезагрузки сервера основная панель и дроп поднялись сами, а копия Meyer – нет:
её не было в автозагрузке, Caddy отдавал на её адрес 502. Задача планировщика
`\\centro2-meyer` – по образцу `\\seostat-obzvon`: при загрузке системы (с задержкой 30 с, чтобы
поднялась сеть), от SYSTEM, рабочая папка C:\\centro2, запуск `zapusk.py` под венвом
C:\\seostat\\.venv (как start-centro2.bat). БЕЗ «перезапуска при сбое»: панель перезапускается
скриптами через taskkill, и планировщик принял бы это за сбой и стал бы поднимать второй
экземпляр на занятый порт. Сейчас задачу НЕ запускаем: панель уже работает.
Удалить: schtasks /delete /tn "\\centro2-meyer" /f
"""
import io, os, subprocess, tempfile
XML = '''<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.3" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><URI>\\centro2-meyer</URI><Description>Копия панели обзвона Meyer, порт 8016 (C:\\centro2)</Description></RegistrationInfo>
  <Principals><Principal id="Author"><UserId>S-1-5-18</UserId><RunLevel>HighestAvailable</RunLevel></Principal></Principals>
  <Settings>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <Enabled>true</Enabled>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <UseUnifiedSchedulingEngine>true</UseUnifiedSchedulingEngine>
  </Settings>
  <Triggers><BootTrigger><Delay>PT30S</Delay></BootTrigger></Triggers>
  <Actions Context="Author"><Exec>
    <Command>C:\\seostat\\.venv\\Scripts\\python.exe</Command>
    <Arguments>zapusk.py</Arguments>
    <WorkingDirectory>C:\\centro2</WorkingDirectory>
  </Exec></Actions>
</Task>
'''
put = os.path.join(tempfile.gettempdir(), 'centro2-meyer-task.xml')
io.open(put, 'w', encoding='utf-16').write(XML)
r = subprocess.run(['schtasks', '/create', '/tn', r'\centro2-meyer', '/xml', put, '/f'], capture_output=True, timeout=60)
print('создание:', r.returncode, r.stdout.decode('cp866', 'replace').strip(), r.stderr.decode('cp866', 'replace').strip())
os.remove(put)
r = subprocess.run(['schtasks', '/query', '/tn', r'\centro2-meyer', '/fo', 'LIST', '/v'], capture_output=True, timeout=60)
for l in r.stdout.decode('cp866', 'replace').splitlines():
    if any(s in l for s in ('Имя задачи', 'TaskName', 'Состояние', 'Status', 'Задача для выполнения', 'Task To Run', 'Начать в', 'Start In',
                            'Запуск от имени', 'Run As User', 'Тип расписания', 'Schedule Type', 'Scheduled Task State', 'Состояние назначенной')):
        print('  ' + l.strip())

#!/bin/bash
# Дождаться текущего задания справочников и пустить цепочку. Ставить их параллельно нельзя:
# очередь тяжёлых задач раннера однопоточная, второе задание просто встанет и съест таймаут.
while pgrep -f "zapusk_na_servere.py dept_directory" >/dev/null; do sleep 20; done
cd /home/user/work && exec python3 gnat_dept.py 6

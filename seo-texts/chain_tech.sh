#!/bin/bash
cd /tmp/claude-0/-home-user-avto/bcce55cd-293a-515c-9700-ae71a77daa5a/scratchpad
# 1) ждём завершения текущего 15-ре-рана (тот же state-файл, нельзя параллельно)
while pgrep -f "regen_driver.py" >/dev/null 2>&1; do sleep 20; done
echo "=== 15-run finished, launching 74 tech-residual ==="
# 2) гоним 74 тех-страницы (давление/поток/цепочка/адсорбция), maxrounds=3, полагаемся на 403 как реальный стоп
REGEN_QUEUE=regen-queue-tech.json REGEN_WORKERS=3 REGEN_BUDGET=450 REGEN_MAXROUNDS=3 python3 regen_driver.py
echo "=== 74 tech-run finished ==="

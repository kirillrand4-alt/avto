#!/bin/bash
# Сторож конвейера.
#
# ЗАЧЕМ. Ночной прогон некому пересмотреть, а встать он может тихо:
# процесс жив, но шлюз перестал отвечать и все потоки ждут таймаута.
# За сегодня шлюз ронял стрим двенадцать раз, дважды подряд на одной
# части. Сторож смотрит не на процесс, а на ДВИЖЕНИЕ: растёт ли журнал.
#
# Правило простое: если за 40 минут в журнале не прибавилось ни строки,
# конвейер считается вставшим и перезапускается. Он резюмируемый -
# готовые страницы пропускает по журналу, поэтому перезапуск не теряет
# сделанного.
#
# Порог 40 минут выбран по замерам: самая долгая цепочка сегодня заняла
# 28 минут (ТЗ 1064 с + статья 659 с). Сорок даёт запас и не дёргает
# живой прогон.
set -u
DIR="$(cd "$(dirname "$0")" && pwd)"
ZHURNAL="$DIR/konveyer.jsonl"
LOG="$DIR/storozh.log"
POTOKOV="${POTOKOV:-5}"
PREDEL_MIN="${PREDEL_MIN:-40}"

zapis() { echo "$(date '+%H:%M:%S') $*" >> "$LOG"; }

zhiv() { pgrep -f "konveyer.py" > /dev/null 2>&1; }

strok() { [ -f "$ZHURNAL" ] && wc -l < "$ZHURNAL" | tr -d ' ' || echo 0; }

bylo=$(strok)
tihо=0

while true; do
    sleep 300
    stalo=$(strok)
    if [ "$stalo" -gt "$bylo" ]; then
        zapis "движение: строк $bylo -> $stalo"
        bylo=$stalo
        tihо=0
        continue
    fi
    tihо=$((tihо + 5))
    if ! zhiv; then
        zapis "конвейер не запущен, поднимаю"
        cd "$DIR" && nohup python3 konveyer.py --potokov "$POTOKOV" \
            >> "$DIR/konveyer.log" 2>&1 &
        tihо=0
        continue
    fi
    if [ "$tihо" -ge "$PREDEL_MIN" ]; then
        zapis "тишина $tihо мин при живом процессе - перезапуск"
        pkill -f "konveyer.py"
        sleep 10
        cd "$DIR" && nohup python3 konveyer.py --potokov "$POTOKOV" \
            >> "$DIR/konveyer.log" 2>&1 &
        tihо=0
    fi
done

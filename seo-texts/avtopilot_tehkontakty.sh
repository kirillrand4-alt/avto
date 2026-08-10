#!/bin/bash
# АВТОПИЛОТ: снимаю техконтакты пачками, после каждой пересобираю проверенный список.
# Пачка = 40 строк, у каждой два снимка (человек и машина). Между пачками пауза 20 с,
# чтобы не долбить площадки. Останавливается сам, когда целей не осталось.
cd /home/user/avto/seo-texts
SCR="$1"
for i in $(seq 1 60); do
  P25_SCRATCH="$SCR" P25_SKOLKO=40 P25_POTOKOV=4 python3 p25_snimki_tehkontaktov.py \
      > "$SCR/avto_snimki_$i.log" 2>&1
  P25_SCRATCH="$SCR" python3 p25_tehkontakty_provereno.py > "$SCR/avto_prov_$i.log" 2>&1
  n=$(grep -o '"снято": [0-9]*' "$SCR/avto_snimki_$i.log" | grep -o '[0-9]*' | head -1)
  echo "$(date -u +%H:%M) пачка $i: снято ${n:-0}; проверено: $(grep -o '"проверено": [0-9]*' "$SCR/avto_prov_$i.log" | grep -o '[0-9]*' | head -1)" >> "$SCR/avtopilot.log"
  [ "${n:-0}" = "0" ] && { echo "$(date -u +%H:%M) целей не осталось — автопилот закончил" >> "$SCR/avtopilot.log"; break; }
  sleep 20
done

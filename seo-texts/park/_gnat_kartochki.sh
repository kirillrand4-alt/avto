#!/bin/bash
# Догрузка реквизитов с checko кусками: раннер не держит длинные задания, прогон возобновляемый.
cd /home/user/avto/seo-texts/server
for i in $(seq 1 25); do
  python3 run_on_server.py enrich_contacts \
    '{"op":"panel_py","script":"C:\\sender\\_ops\\park_1s_checko_kartochka.py","argv":[300],"timeout":360}' \
    > /dev/null 2>&1
  echo "кусок $i: $(date -u +%H:%M:%S)"
done

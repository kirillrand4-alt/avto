#!/bin/bash
# Гоню сбор checko кусками: раннер не держит длинные задания, а прогон возобновляемый.
cd /home/user/avto/seo-texts/server
for i in $(seq 1 40); do
  python3 run_on_server.py enrich_contacts \
    '{"op":"panel_py","script":"C:\\sender\\_ops\\park_1s_checko_okved.py","argv":[400],"timeout":460}' \
    > /dev/null 2>&1
  echo "кусок $i готов: $(date -u +%H:%M:%S)"
done

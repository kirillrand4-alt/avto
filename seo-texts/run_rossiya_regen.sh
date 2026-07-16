#!/bin/bash
cd /tmp/claude-0/-home-user-avto/bcce55cd-293a-515c-9700-ae71a77daa5a/scratchpad
for MODEL in claude-fable-5 claude-sonnet-5; do
  DIRSHORT=$(echo "$MODEL" | sed 's/claude-//')
  echo "=== REGEN $MODEL rossiya $(date +%H:%M:%S)"
  python3 gen_provider.py rossiya --model "$MODEL" --guide gen/STYLE-GUIDE-ELEKTRO.md \
    --payload gen/payload-el-rossiya.json --out "gen/r2-$DIRSHORT/result-el-rossiya.json" 2>&1 | tail -14
done
echo "REGEN ЗАВЕРШЁН $(date +%H:%M:%S)"

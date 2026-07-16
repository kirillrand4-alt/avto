#!/bin/bash
cd /tmp/claude-0/-home-user-avto/bcce55cd-293a-515c-9700-ae71a77daa5a/scratchpad
for MODEL in claude-fable-5 claude-sonnet-5; do
  DIRSHORT=$(echo "$MODEL" | sed 's/claude-//')
  for s in hansmann rossiya remennyy kompressory-10-bar kompressory-1000-l-min; do
    echo "=== $MODEL $s $(date +%H:%M:%S)"
    python3 gen_provider.py "$s" --model "$MODEL" --guide gen/STYLE-GUIDE-ELEKTRO.md \
      --payload "gen/payload-el-$s.json" --out "gen/r2-$DIRSHORT/result-el-$s.json" 2>&1 | tail -14
  done
done
echo "РАУНД 2 ЗАВЕРШЁН $(date +%H:%M:%S)"

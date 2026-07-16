#!/bin/bash
cd /tmp/claude-0/-home-user-avto/bcce55cd-293a-515c-9700-ae71a77daa5a/scratchpad
OPUS_LOG=/tmp/claude-0/-home-user-avto/bcce55cd-293a-515c-9700-ae71a77daa5a/tasks/buu1dll7w.output
until grep -q "ПИЛОТ ЗАВЕРШЁН" "$OPUS_LOG" 2>/dev/null; do sleep 30; done
echo "Opus-батч завершён, стартую A/B $(date +%H:%M:%S)"
for MODEL in claude-sonnet-5 claude-fable-5; do
  DIRSHORT=$(echo "$MODEL" | sed 's/claude-//')
  for s in enger berg dalgakiran 15-to-15 s-chastotnym-preobrazovatelem; do
    echo "=== $MODEL $s $(date +%H:%M:%S)"
    python3 gen_provider.py "$s" --model "$MODEL" --guide gen/STYLE-GUIDE-ELEKTRO.md \
      --payload "gen/payload-el-$s.json" --out "gen/ab-$DIRSHORT/result-el-$s.json" 2>&1 | tail -12
  done
done
echo "A/B ЗАВЕРШЁН $(date +%H:%M:%S)"

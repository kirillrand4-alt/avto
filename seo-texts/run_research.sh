#!/bin/bash
cd /tmp/claude-0/-home-user-avto/bcce55cd-293a-515c-9700-ae71a77daa5a/scratchpad
AB_LOG=/tmp/claude-0/-home-user-avto/bcce55cd-293a-515c-9700-ae71a77daa5a/tasks/bu001dqje.output
until grep -q "A/B ЗАВЕРШЁН" "$AB_LOG" 2>/dev/null; do sleep 60; done
echo "A/B завершён, отправляю исследовательский батч $(date +%H:%M:%S)"
python3 research_kb.py
echo "ИССЛЕДОВАНИЕ ЗАВЕРШЕНО $(date +%H:%M:%S)"

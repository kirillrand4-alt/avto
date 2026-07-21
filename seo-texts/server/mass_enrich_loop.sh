#!/usr/bin/env bash
# Массовый прогон xmlriver-поиск сайта + выгрузка контактов по ВСЕЙ базе без сайта.
# Драйвер со стороны песочницы: пачками cap=N submit'ит mass_base-задания раннеру.
# Резюмируемо: каждое задание само пропускает уже сделанные ИНН (done-set из jsonl на
# сервере). Переживает рестарт: прогресс на сервере, не в песочнице — повторный запуск
# продолжит с места. Каждое задание ≤30 мин (лимит раннера).
#
# Использование: bash mass_enrich_loop.sh <CAP> <BATCHES> [WORKERS] [CHANNELS]
#   CAP     — компаний за одно задание (по убыванию выручки, undone). Дефолт 400.
#   BATCHES — сколько заданий подряд (0 = пока не кончится пул). Дефолт 0.
set -u
cd "$(dirname "$0")"
CAP="${1:-400}"; BATCHES="${2:-0}"; WORKERS="${3:-8}"; CHANNELS="${4:-4}"
export XMLRIVER_CHANNELS="$CHANNELS"
i=0
while :; do
  i=$((i+1))
  ARGS=$(python3 - "$CAP" "$WORKERS" <<'PY'
import json,sys
cap=int(sys.argv[1]); workers=int(sys.argv[2])
print(json.dumps({"mass_base":True,"no_site":True,"cap":cap,"workers":workers,
  "no_fallback":True,"no_browser":True,"pace_min":1.5,"pace_max":3.5,
  "stream_file":"enrich_stream_mass.jsonl","source":"mass","write_db":True}, ensure_ascii=False))
PY
)
  echo "=== batch #$i (cap=$CAP, channels=$CHANNELS) $(date -u +%H:%M:%S)UTC ==="
  OUT=$(timeout 1750 python3 run_on_server.py enrich_contacts "$ARGS" 2>&1)
  echo "$OUT" | python3 -c "
import sys,json
raw=sys.stdin.read()
try:
    d=json.loads(raw[raw.index('{'):raw.rindex('}')+1])
    data=d.get('data') or {}
    print('  ok=%s took=%s count=%s summary=%s'%(d.get('ok'),d.get('took_sec'),
          (data or {}).get('count'), (data or {}).get('summary')))
    # признак опустевшего пула: обработано 0 компаний
    print('  EMPTY' if (data or {}).get('count')==0 else '  more')
except Exception as e:
    print('  parse-fail:', str(e)[:80]); print(raw[-300:])
"
  if echo "$OUT" | grep -q '"count": 0'; then echo 'пул пуст — стоп'; break; fi
  if [ "$BATCHES" != "0" ] && [ "$i" -ge "$BATCHES" ]; then echo 'достигнут лимит пачек'; break; fi
  sleep 3
done
echo "=== массовый прогон: $i пачек ==="

#!/bin/bash
# Клиент обменника parsercompressor.online/drop для сессий Claude Code.
# Токен и URL берутся из окружения: DROP_TOKEN, DROP_URL (задать в env-настройках окружения).
# Использование: drop_client.sh list | up <file> | down <name> [dst] | del <name>
U="${DROP_URL:-https://parsercompressor.online/drop}"
[ -z "$DROP_TOKEN" ] && { echo "нет DROP_TOKEN в окружении"; exit 1; }
case "$1" in
  list) curl -s -H "X-Drop-Token: $DROP_TOKEN" "$U/list" | python3 -m json.tool ;;
  up)   curl -s -H "X-Drop-Token: $DROP_TOKEN" -T "$2" "$U/$(basename "$2")" ;;
  down) curl -s -H "X-Drop-Token: $DROP_TOKEN" "$U/$2" -o "${3:-$2}" && echo "скачан: ${3:-$2}" ;;
  del)  curl -s -X DELETE -H "X-Drop-Token: $DROP_TOKEN" "$U/$2" ;;
  *)    echo "usage: $0 list | up <file> | down <name> [dst] | del <name>" ;;
esac

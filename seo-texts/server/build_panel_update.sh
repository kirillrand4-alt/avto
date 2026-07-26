#!/usr/bin/env bash
# Сборка пакетов обновления обеих панелей и заливка их на дроп.
# Сторона ПЕСОЧНИЦЫ. На сервере владелец запускает update-panel.ps1 / update-obzvon.ps1.
#
# Почему zip, а не пофайловый panel_file_put: панель рассыльщика — это пакет
# sender/ + собранный фронт web/dist, их надо класть одной транзакцией под
# остановленной службой. А панель обзвона вообще живёт в C:\seostat\app, куда
# panel_file_put не пишет (он ограничен C:\sender) — только дроп.
#
# Использование:
#   bash build_panel_update.sh panel     # только рассыльщик
#   bash build_panel_update.sh obzvon    # только обзвон
#   bash build_panel_update.sh all       # оба (по умолчанию)
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SENDER="$REPO/seo-texts/sender"
PATCHES="$REPO/seo-texts/sender-patches"
OUT="${TMPDIR:-/tmp}/panel-build"
DROP="$REPO/seo-texts/server/drop_client.sh"
WHAT="${1:-all}"

rm -rf "$OUT"; mkdir -p "$OUT"

build_panel() {
  echo "== пакет панели рассыльщика =="
  local stage="$OUT/panel"
  mkdir -p "$stage/sender" "$stage/web"

  # 1) питон-пакет: только исходники, без мусора и без тестов
  #    (тесты гоняются в песочнице/на сервере отдельно, в боевой каталог не кладём).
  #    Через find, а не rsync: rsync в песочнице не установлен.
  ( cd "$SENDER" && find . -name '*.py' -type f \
      -not -path './web/*' -not -path './tests/*' -not -path '*/__pycache__/*' \
      -print0 ) | while IFS= read -r -d '' f; do
    mkdir -p "$stage/sender/$(dirname "$f")"
    cp "$SENDER/$f" "$stage/sender/$f"
  done

  # 2) фронт: собираем ЗДЕСЬ, на сервер едет только dist (правило PANEL-DEPLOY.md —
  #    node_modules и исходники web в архив не кладём)
  if [ -d "$SENDER/web" ]; then
    if [ ! -d "$SENDER/web/dist/assets" ] || [ "${REBUILD_WEB:-0}" = "1" ]; then
      echo "  сборка фронта (npm run build)..."
      ( cd "$SENDER/web" && npm install --no-audit --no-fund >/dev/null 2>&1 && npm run build >/dev/null )
    else
      echo "  фронт уже собран, беру готовый dist (REBUILD_WEB=1 чтобы пересобрать)"
    fi
    mkdir -p "$stage/web/dist"
    cp -r "$SENDER/web/dist/." "$stage/web/dist/"
  fi

  # 3) манифест: что именно уехало — чтобы потом сверить с сервером
  ( cd "$stage" && find . -type f | sort | while read -r f; do
      printf '%s  %s\n' "$(sha256sum "$f" | cut -c1-16)" "${f#./}"
    done ) > "$stage/UPDATE-MANIFEST.txt"

  ( cd "$stage" && zip -qr "$OUT/panel-update.zip" sender web UPDATE-MANIFEST.txt )
  echo "  готов: $OUT/panel-update.zip ($(du -h "$OUT/panel-update.zip" | cut -f1))"
}

build_obzvon() {
  echo "== пакет панели обзвона =="
  local stage="$OUT/obzvon"
  mkdir -p "$stage"
  # Имена в sender-patches плоские (api__routes_obzvon.py), на сервере — вложенные
  # (api\routes_obzvon.py). Разворачиваем двойное подчёркивание обратно в каталоги.
  local n=0
  for f in "$PATCHES"/obzvon-pagination/*; do
    [ -f "$f" ] || continue
    local base rel
    base="$(basename "$f")"
    rel="${base//__//}"
    mkdir -p "$stage/$(dirname "$rel")"
    cp "$f" "$stage/$rel"
    n=$((n+1))
  done
  [ "$n" -gt 0 ] || { echo "  нечего паковать (sender-patches/obzvon-pagination пуст)"; return; }
  ( cd "$stage" && find . -type f | sort | while read -r f; do
      printf '%s  %s\n' "$(sha256sum "$f" | cut -c1-16)" "${f#./}"
    done ) > "$stage/UPDATE-MANIFEST.txt"
  ( cd "$stage" && zip -qr "$OUT/obzvon-update.zip" . )
  echo "  готов: $OUT/obzvon-update.zip ($n файлов)"
}

case "$WHAT" in
  panel)  build_panel ;;
  obzvon) build_obzvon ;;
  all)    build_panel; build_obzvon ;;
  *) echo "usage: $0 [panel|obzvon|all]"; exit 2 ;;
esac

echo "== заливка на дроп =="
for z in "$OUT"/*.zip; do
  bash "$DROP" up "$z" >/dev/null && echo "  залит: $(basename "$z")"
done
# скрипты обновления кладём туда же — владелец качает их той же командой
for p in "$REPO/seo-texts/server/update-panel.ps1" "$REPO/seo-texts/server/update-obzvon.ps1"; do
  [ -f "$p" ] && bash "$DROP" up "$p" >/dev/null && echo "  залит: $(basename "$p")"
done
echo
echo "Владельцу — по ОДНОЙ команде в PowerShell (без && и ::):"
echo '  $tok=(Select-String -Path C:\sender\server\runner-secrets.env -Pattern '"'"'DROP_TOKEN='"'"').Line.Split('"'"'='"'"',2)[1].Trim()'
echo '  Invoke-WebRequest -Uri "https://parsercompressor.online/drop/update-panel.ps1" -Headers @{'"'"'X-Drop-Token'"'"'=$tok} -OutFile C:\sender\update-panel.ps1'
echo '  powershell -ExecutionPolicy Bypass -File C:\sender\update-panel.ps1'

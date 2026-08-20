#!/usr/bin/env bash
# Ночной конвейер волны 2: от сырых статей до принятых, без участия человека.
#
# Владелец ушёл спать с задачей «в конце нужны идеальные статьи». Шаги идут
# последовательно, каждый отмечается в pipeline-state.txt — контейнер за ночь
# перезапускается по нескольку раз, и после рестарта скрипт продолжает с места,
# а не начинает заново.
#
# Ничего наружу не отправляется: только генерация и приёмка. Отправка на площадку
# и оплата - действия вовне, они под холдом до явного ОК владельца.
set -u
cd "$(dirname "$0")"
STATE=pipeline-state.txt
LOG=pipeline.log
touch "$STATE"
say() { echo "[$(date +%H:%M)] $*" | tee -a "$LOG"; }
# Коммит после КАЖДОГО шага. Урок ночи 19.08: статьи волны 2 сгенерировались,
# но в git не попали (git add падал с ошибкой пути), песочница откатилась к
# утреннему снимку - и час генерации пропал. Всё, что не в origin, не существует.
save() {
  ( cd /home/user/avto && git add -A seo-texts/ >/dev/null 2>&1 &&
    git commit -q -m "конвейер: $1" >/dev/null 2>&1 &&
    for i in 1 2 3 4; do
      git push -q origin claude/guest-post-text-generator-35u4n6 >/dev/null 2>&1 && break
      sleep $((2 ** i))
    done )
  say "сохранено в origin: $1"
}
done_step() { grep -qx "$1" "$STATE"; }
mark() { echo "$1" >> "$STATE"; }

SLUGS=$(python3 -c "
import importlib.util as iu
spec=iu.spec_from_file_location('wj','wave-jobs.py'); m=iu.module_from_spec(spec); spec.loader.exec_module(m)
print(' '.join(j['slug'] for j in m.JOBS))")

# ── 1. Дождаться текущей генерации (она стартовала до шпаргалки) ──────────────
if ! done_step gen1; then
  say "жду завершения генерации 1 (сырой материал, без шпаргалки)"
  while pgrep -f "gen_wave.py azotnye" > /dev/null 2>&1; do sleep 30; done
  save "генерация 1"; mark gen1; say "генерация 1 завершена"
fi

# ── 2. Приёмка сырого материала: замер, сколько ловит линза размерностей ──────
if ! done_step accept1; then
  say "приёмка 1: 16 линз по сырым статьям — проверяем teh_razmernost на деле"
  JOBS_MODULE=wave-jobs PROVIDER_DEAD_MODELS='claude-opus-5' \
    python3 finalize_gp.py $SLUGS >> "$LOG" 2>&1
  python3 - << 'PY' | tee -a "$LOG"
import glob, re, json, collections
stat = collections.Counter(); rows = []
for f in glob.glob('ready/*.finalize-log.md'):
    t = open(f, encoding='utf-8').read()
    slug = f.split('/')[-1].replace('gp-','').replace('.finalize-log.md','')
    dim = re.findall(r'\[teh_razmernost\] вердикт: (FAIL[^(]*|PASS)', t)
    conf = t.count('КОНФЛИКТ ПРАВОК')
    ok = 'ГОТОВ К ПУБЛИКАЦИИ' in t
    if dim: stat['размерность_FAIL' if dim[0].startswith('FAIL') else 'размерность_PASS'] += 1
    rows.append({'slug': slug, 'ok': ok, 'dim': dim[0] if dim else '?', 'conflicts': conf})
json.dump(rows, open('accept1-stat.json','w'), ensure_ascii=False, indent=1)
print('ЗАМЕР ПО СЫРОМУ МАТЕРИАЛУ:', dict(stat))
print('готовых:', sum(1 for r in rows if r['ok']), 'из', len(rows))
PY
  save "приёмка сырого материала"; mark accept1; say "приёмка 1 завершена, замер сохранён"
fi

# ── 3. Переписать заход 4tololo (владелец забраковал тему) ────────────────────
if ! done_step rework; then
  say "переписываю тему 4tololo: заход через производственные смерти забракован"
  GENRE_OUT=genre-jobs-rework.jsonl python3 genre_jobs.py 4tololo.ru >> "$LOG" 2>&1
  python3 - << 'PY' | tee -a "$LOG"
import json, os
# новая тема приезжает в отдельный файл, чтобы не затереть остальные
new = [json.loads(l) for l in open('genre-jobs-rework.jsonl', encoding='utf-8') if l.strip()]
new = [r for r in new if r['donor'] == '4tololo.ru' and r.get('title')]
if new:
    r = new[-1]
    jobs = [json.loads(l) for l in open('final-jobs.jsonl', encoding='utf-8') if l.strip()]
    for j in jobs:
        if j['donor'] == '4tololo.ru':
            j['title_rework_old'] = j.get('title'); j['title'] = r['title']
            j['angle'] = r.get('angle') or j['angle']
            j['skeleton'] = r.get('skeleton') or j['skeleton']
            j.pop('needs_rework', None)
            print('новая тема 4tololo:', r['title'])
    open('final-jobs.jsonl','w').writelines(json.dumps(j, ensure_ascii=False)+'\n' for j in jobs)
else:
    print('4tololo: новую тему получить не удалось, остаётся прежняя')
PY
  save "тема 4tololo переписана"; mark rework; say "тема 4tololo обновлена"
fi

# ── 4. Перегенерация со шпаргалкой опорных величин ────────────────────────────
if ! done_step gen2; then
  say "перегенерация всех статей со шпаргалкой ENGINEERING-CONSTANTS"
  python3 jobs_export.py >> "$LOG" 2>&1
  for s in $SLUGS; do rm -f "gp-$s.html" "gp-$s.meta.json"; done
  rm -f ready/*.final.html ready/*.NEEDS-REVIEW.html ready/*.finalize-log.md ready/*.progress.json
  JOBS_MODULE=wave-jobs PROVIDER_FIRST_TOKEN_SEC=300 PROVIDER_STREAM_DEADLINE_SEC=900 \
    python3 gen_wave.py $SLUGS >> "$LOG" 2>&1
  save "перегенерация со шпаргалкой"; mark gen2; say "перегенерация завершена"
fi

# ── 5. Финальная приёмка ──────────────────────────────────────────────────────
if ! done_step accept2; then
  say "приёмка 2: финальная, 16 линз"
  JOBS_MODULE=wave-jobs PROVIDER_DEAD_MODELS='claude-opus-5' \
    python3 finalize_gp.py $SLUGS >> "$LOG" 2>&1
  save "финальная приёмка"; mark accept2; say "приёмка 2 завершена"
fi

# ── 6. Проверка серии по готовым текстам ──────────────────────────────────────
if ! done_step series; then
  say "проверка серии по готовым текстам"
  python3 series_check.py --texts >> "$LOG" 2>&1
  save "проверка серии"; mark series; say "проверка серии завершена"
fi

# ── 7. Сводка ─────────────────────────────────────────────────────────────────
say "сборка итогового отчёта"
python3 wave_report.py >> "$LOG" 2>&1
say "ГОТОВО"

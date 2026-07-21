# -*- coding: utf-8 -*-
"""Массовый прогон: xmlriver-поиск сайта + выгрузка контактов по ВСЕЙ базе без сайта.
Драйвер (сторона песочницы): пачками cap=N submit'ит mass_base-задания раннеру.

Устойчивость:
 - РЕЗЮМИРУЕМО: каждое задание само пропускает уже сделанные ИНН (done-set из jsonl на
   сервере) → рестарт песочницы/сервера не теряет прогресс, повторный запуск продолжит.
 - ОРФАН-ТОЛЕРАНТНО: если задание осиротело (сервер рестартнул на середине) — ждём только
   per-batch-timeout, затем просто шлём следующую пачку (done-set покрывает частичное).
 - СТОП: пул пуст (обработано 0) ИЛИ подряд MAX_FAIL пустых/сбойных ответов.

Запуск: python3 mass_enrich_loop.py [CAP] [BATCHES] [WORKERS] [CHANNELS] [BATCH_TIMEOUT]
"""
import os, sys, json, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run_on_server as R

CAP = int(sys.argv[1]) if len(sys.argv) > 1 else 40
BATCHES = int(sys.argv[2]) if len(sys.argv) > 2 else 0        # 0 = пока не кончится пул
WORKERS = int(sys.argv[3]) if len(sys.argv) > 3 else 4
CHANNELS = int(sys.argv[4]) if len(sys.argv) > 4 else 4
BATCH_TIMEOUT = int(sys.argv[5]) if len(sys.argv) > 5 else 900  # быстрее ловим орфана
MAX_FAIL = 4

os.environ['XMLRIVER_CHANNELS'] = str(CHANNELS)
R._load_secret_from_drop()


def one_batch():
    args = {'mass_base': True, 'no_site': True, 'cap': CAP, 'workers': WORKERS,
            'channels': CHANNELS, 'no_fallback': True, 'no_browser': True,
            'pace_min': 0.5, 'pace_max': 1.5,
            'stream_file': 'enrich_stream_mass.jsonl', 'source': 'mass', 'write_db': True}
    out = R.submit('enrich_contacts', args, wait=True, poll=15, timeout=BATCH_TIMEOUT)
    return out


def main():
    i, fails, total_done = 0, 0, 0
    while True:
        i += 1
        t0 = time.time()
        print(f'=== пачка #{i} (cap={CAP}, ch={CHANNELS}) старт ===', flush=True)
        out = one_batch()
        data = out.get('data') if isinstance(out, dict) else None
        if not isinstance(data, dict):
            fails += 1
            print(f'  сбой/орфан/таймаут ({time.time()-t0:.0f}s): {str(out)[:160]} '
                  f'[подряд {fails}/{MAX_FAIL}]', flush=True)
            if fails >= MAX_FAIL:
                print('слишком много сбоев подряд — стоп', flush=True)
                break
            time.sleep(5)
            continue
        fails = 0
        cnt = data.get('count') or 0
        total_done += cnt
        s = data.get('summary') or {}
        print(f'  ok={out.get("ok")} за {time.time()-t0:.0f}s: обработано {cnt} '
              f'(всего {total_done}) | сайтов={s.get("site_sources")} '
              f'email={s.get("with_email")} lpr={s.get("with_lpr_email")}', flush=True)
        if cnt == 0:
            print('пул пуст — массовый прогон завершён', flush=True)
            break
        if BATCHES and i >= BATCHES:
            print('достигнут лимит пачек', flush=True)
            break
        time.sleep(3)
    print(f'=== ИТОГО: {i} пачек, обработано ~{total_done} компаний ===', flush=True)


if __name__ == '__main__':
    main()

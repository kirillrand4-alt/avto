# -*- coding: utf-8 -*-
r"""Разовая чистка диска по команде владельца 18.08 (сервер был занят на 334/447 ГБ).

Четыре цели, все проверены до удаления:
  1. zenno\razobrano старше суток — сырьё Зенки, УЖЕ разобранное: страницы в
     pagecache, контакты в enrich.db. Мост туда только переносит и не читает;
     свежие сутки оставляем — по их дате он понимает «Зенка встала».
  2. pagecache_staryy_20260813_2036 — снимок кэша перед карантином площадок,
     свою роль отыграл.
  3. Корзина — 6,4 ГБ удалённого, которое всё ещё занимает диск.
  4. ScreamingFrog: ProjectInstanceData (сохранённые краулы) и AppUpdater
     (скачанные установщики). Сам chrome и настройки не трогаем — программа
     останется рабочей. Проверено: процесс не запущен.

    python chistka_diska.py            посчитать
    python chistka_diska.py --udalit   удалить
"""
import ctypes
import json
import os
import shutil
import sys
import time

ЖУРНАЛ = r'C:\sender\server\chistka-diska.jsonl'
RAZOBRANO = r'C:\seostat\drop\zenno\razobrano'
ДЕРЖИМ_СУТОК = 1
ПАПКИ = (r'C:\seostat\drop\pagecache_staryy_20260813_2036',
         r'C:\Users\Administrator\.ScreamingFrogSEOSpider\ProjectInstanceData',
         r'C:\Users\Administrator\.ScreamingFrogSEOSpider\AppUpdater')


def _вес(п):
    н = 0
    try:
        for e in os.scandir(п):
            try:
                if e.is_symlink():
                    continue
                н += _вес(e.path) if e.is_dir(follow_symlinks=False) \
                    else e.stat(follow_symlinks=False).st_size
            except OSError:
                continue
    except OSError:
        pass
    return н


def _свободно():
    return round(shutil.disk_usage('C:\\').free / 2**30, 1)


def чистка(удалять=False):
    итог = {'свободно_до_ГБ': _свободно(), 'шаги': {}}
    # 1. razobrano старше суток
    порог = time.time() - ДЕРЖИМ_СУТОК * 86400
    n = байт = свежих = 0
    удалено = ошибок = 0
    свежесть = 0.0
    try:
        for e in os.scandir(RAZOBRANO):
            try:
                if not e.is_file():
                    continue
                st = e.stat()
            except OSError:
                continue
            if st.st_mtime >= порог:
                свежих += 1
                свежесть = max(свежесть, st.st_mtime)
                continue
            n += 1
            байт += st.st_size
            if удалять:
                try:
                    os.remove(e.path)
                    удалено += 1
                except OSError:
                    ошибок += 1
    except OSError as ex:
        итог['шаги']['razobrano'] = {'беда': str(ex)}
    else:
        итог['шаги']['razobrano'] = {
            'под_удаление': n, 'ГБ': round(байт / 2**30, 2), 'удалено': удалено,
            'ошибок': ошибок, 'оставлено_свежих': свежих,
            'самый_свежий': time.strftime('%Y-%m-%d %H:%M', time.localtime(свежесть))
            if свежесть else 'нет'}
    # 2-4. папки целиком (содержимое; сами папки сохраняем)
    for п in ПАПКИ:
        if not os.path.exists(п):
            итог['шаги'][os.path.basename(п)] = 'нет такой папки'
            continue
        в = _вес(п)
        зап = {'ГБ': round(в / 2**30, 2), 'удалено_узлов': 0, 'ошибок': 0}
        if удалять:
            for e in list(os.scandir(п)):
                try:
                    if e.is_dir(follow_symlinks=False):
                        shutil.rmtree(e.path, ignore_errors=True)
                    else:
                        os.remove(e.path)
                    зап['удалено_узлов'] += 1
                except OSError:
                    зап['ошибок'] += 1
            зап['осталось_ГБ'] = round(_вес(п) / 2**30, 2)
        итог['шаги'][os.path.basename(п)] = зап
    # 5. корзина
    корзина = _вес(r'C:\$Recycle.Bin')
    зап = {'ГБ': round(корзина / 2**30, 2)}
    if удалять:
        try:
            # 1|2|4 = без подтверждения, без окна прогресса, без звука
            зап['SHEmptyRecycleBin_rc'] = ctypes.windll.shell32.SHEmptyRecycleBinW(
                None, None, 7)
        except Exception as ex:  # noqa: BLE001
            зап['SHEmptyRecycleBin_rc'] = str(ex)[:80]
        try:
            for e in os.scandir(r'C:\$Recycle.Bin'):
                if e.is_dir(follow_symlinks=False):
                    for x in list(os.scandir(e.path)):
                        try:
                            if x.is_dir(follow_symlinks=False):
                                shutil.rmtree(x.path, ignore_errors=True)
                            else:
                                os.remove(x.path)
                        except OSError:
                            pass
        except OSError:
            pass
        зап['осталось_ГБ'] = round(_вес(r'C:\$Recycle.Bin') / 2**30, 2)
    итог['шаги']['корзина'] = зап
    итог['свободно_после_ГБ'] = _свободно()
    итог['освободили_ГБ'] = round(итог['свободно_после_ГБ'] - итог['свободно_до_ГБ'], 1)
    if удалять:
        with open(ЖУРНАЛ, 'a', encoding='utf-8') as f:
            f.write(json.dumps({**итог, 'ts': time.strftime('%Y-%m-%dT%H:%M:%S')},
                               ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())
    return итог


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    print(json.dumps(чистка('--udalit' in sys.argv), ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())

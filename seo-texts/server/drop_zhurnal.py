# -*- coding: utf-8 -*-
"""Живая переписка сессий через дроп: свой журнал наружу, чужие журналы внутрь.

Замысел владельца: у каждой сессии на дропе лежит файл-журнал, она дописывает в него, что сделала,
какие выводы и какие ошибки; остальные сессии читают его на ходу и отвечают — подсказывают, где
искать, кладут данные отдельными файлами.

Почему это отдельный сторож, а не «сессия сама опрашивает раз в десять секунд». Сессия действует
только когда делает вызов инструмента: опрос раз в десять секунд означал бы, что она только
опросом и занята. Поэтому опрашивает фоновый сторож, а сессия читает накопленное, когда
поднимает голову. Цена опроса для сессии — ноль.

Как устроено:
- **свой журнал** — обычный файл в репозитории, сессия дописывает его как хочет. Сторож замечает
  изменение по mtime и заливает на дроп. Пустых заливок нет.
- **чужие журналы** — всё, что на дропе называется `ZHURNAL-*.md` и не мой. Ничьё имя знать
  заранее не нужно, список сам их находит; появившаяся четвёртая сессия подхватится сама.
- **входящее** — новые куски чужих журналов дописываются в один файл `VHODYASHCHEE.md` с
  заголовком «откуда и когда». Дописывается ТОЛЬКО ПРИРОСТ, а не весь файл: иначе на третьем
  круге читать станет нечего из-за объёма.
- **в чужой журнал не пишем никогда.** `up` на дропе перезаписывает файл целиком, и двое
  пишущих в один файл затрут друг друга. Ответ соседу пишется в СВОЙ журнал, обращением по имени.

Обнаружение изменения — по `mtime` из `list`, а не по размеру: правка, не меняющая длину,
по размеру невидима. Это тот же класс, что «файл читается, значит цел».

Использование:
    python3 server/drop_zhurnal.py --start          # сторож в фоне
    python3 server/drop_zhurnal.py --raz            # один круг, для проверки
    python3 server/drop_zhurnal.py --kto            # кто ещё держит журнал на дропе
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import time

BAZA = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DROP = os.path.join(BAZA, 'server', 'drop_client.sh')
# Имена журналов сначала разъехались (`SESSIYA-*` против `ZHURNAL-*`), и я держал свой файл под
# обоими именами. Владелец выбрал общий шаблон `ZHURNAL-N.md`, зеркало снято.
# Слежение оставлено по обоим шаблонам намеренно: пока чьё-то `SESSIYA-*` ещё живо, его надо
# видеть, а лишний шаблон в слежении не стоит ничего.
MOY = 'ZHURNAL-2.md'
MOY_ZERKALO = None
MOY_PUT = os.path.join(BAZA, 'engineers-lens', MOY)
VHOD = os.path.join(BAZA, 'engineers-lens', 'VHODYASHCHEE.md')
KOPII = '/tmp/claude-0/-home-user-avto/520847fd-7699-5483-869b-cf6d49851f67/scratchpad/zhurnaly'
SOSTOYANIE = os.path.join(KOPII, 'sostoyanie.json')
SHABLON = re.compile(r'^(?:ZHURNAL|SESSIYA)-.+\.md$')


def drop(*args, timeout=120):
    p = subprocess.run(['bash', DROP] + list(args), capture_output=True, text=True,
                       timeout=timeout, cwd=KOPII)
    return p.stdout


def spisok():
    try:
        return json.loads(drop('list') or '[]')
    except (json.JSONDecodeError, subprocess.SubprocessError):
        return []


def sostoyanie():
    if os.path.exists(SOSTOYANIE):
        try:
            return json.load(open(SOSTOYANIE, encoding='utf-8'))
        except json.JSONDecodeError:
            pass
    return {'chuzhie': {}, 'moy_mtime': 0, 'kuski': []}


def zapisat_sostoyanie(s):
    json.dump(s, open(SOSTOYANIE, 'w', encoding='utf-8'), ensure_ascii=False)


def prirost(staroe, novoe):
    """Что в новом тексте появилось сверх старого.

    Обычный случай — дописали в конец, тогда прирост это хвост. Если начало разошлось (сосед
    переписал файл целиком), отдаём весь новый текст: лучше показать лишнее, чем пропустить.
    """
    if novoe.startswith(staroe):
        return novoe[len(staroe):]
    return novoe


def krug(gromko=False):
    os.makedirs(KOPII, exist_ok=True)
    s = sostoyanie()
    fajly = {f['name']: f for f in spisok() if SHABLON.match(f.get('name') or '')}
    novogo = 0

    # --- чужие журналы внутрь ---
    for imya, meta in sorted(fajly.items()):
        if imya == MOY or (MOY_ZERKALO and imya == MOY_ZERKALO):
            continue
        bylo = s['chuzhie'].get(imya) or {}
        if bylo.get('mtime') == meta.get('mtime'):
            continue
        drop('down', imya)
        put = os.path.join(KOPII, imya)
        if not os.path.exists(put):
            continue
        tekst = open(put, encoding='utf-8', errors='replace').read()
        staroe = bylo.get('tekst') or ''
        kusok = prirost(staroe, tekst).strip()
        s['chuzhie'][imya] = {'mtime': meta.get('mtime'), 'tekst': tekst}
        if not kusok:
            continue
        # Один и тот же журнал лежит под двумя именами (соседи тоже завели зеркала). Второй раз
        # тот же текст во входящее не кладём: иначе читать придётся вдвое больше того же самого.
        otpechatok = hashlib.sha256(kusok.encode('utf-8')).hexdigest()[:16]
        if otpechatok in s.setdefault('kuski', []):
            if gromko:
                print(f'  {imya}: тот же текст, что уже пришёл под другим именем — пропускаю',
                      file=sys.stderr, flush=True)
            continue
        s['kuski'].append(otpechatok)
        novogo += 1
        with open(VHOD, 'a', encoding='utf-8') as f:
            f.write(f'\n\n---\n## {imya} — {time.strftime("%H:%M:%S")} '
                    f'(+{len(kusok)} знаков)\n\n{kusok}\n')
        if gromko:
            print(f'  пришло от {imya}: +{len(kusok)} знаков', file=sys.stderr, flush=True)

    # --- свой журнал наружу ---
    if os.path.exists(MOY_PUT):
        m = int(os.path.getmtime(MOY_PUT))
        if m != s.get('moy_mtime'):
            drop('up', MOY_PUT)
            if MOY_ZERKALO:
                zerk = os.path.join(KOPII, MOY_ZERKALO)
                open(zerk, 'w', encoding='utf-8').write(open(MOY_PUT, encoding='utf-8').read())
                drop('up', zerk)
            s['moy_mtime'] = m
            if gromko:
                print(f'  залил свой журнал ({os.path.getsize(MOY_PUT)} байт)', file=sys.stderr,
                      flush=True)
    zapisat_sostoyanie(s)
    return novogo, sorted(x for x in fajly if x != MOY)


def main():
    os.makedirs(KOPII, exist_ok=True)
    if '--kto' in sys.argv:
        for f in sorted(spisok(), key=lambda x: x.get('name') or ''):
            if SHABLON.match(f.get('name') or ''):
                print(f'{f["name"]:52} {f["bytes"]:>8} байт  '
                      f'{time.strftime("%d.%m %H:%M", time.localtime(f["mtime"]))}')
        return
    if '--zapis' in sys.argv:
        # Дозапись, никогда не перезапись: читателю нужен хвост, а не итог.
        tekst = sys.argv[sys.argv.index('--zapis') + 1]
        nomer = len(re.findall(r'^## Запись ', open(MOY_PUT, encoding='utf-8').read(), re.M)) + 1
        with open(MOY_PUT, 'a', encoding='utf-8') as f:
            f.write(f'\n\n## Запись {nomer} — {time.strftime("%d.%m %H:%M:%S")}\n\n{tekst}\n')
        krug(gromko=True)
        return
    if '--raz' in sys.argv:
        n, chuzhie = krug(gromko=True)
        print(f'круг сделан: новых кусков {n}, чужих журналов {len(chuzhie)}: '
              + ', '.join(chuzhie), file=sys.stderr)
        return
    # сторож
    shag = int(sys.argv[sys.argv.index('--shag') + 1]) if '--shag' in sys.argv else 10
    print(f'сторож журналов пошёл, шаг {shag} с, мой файл {MOY}', file=sys.stderr, flush=True)
    while True:
        try:
            krug(gromko=True)
        except Exception as e:  # noqa: BLE001
            print(f'  круг не удался: {type(e).__name__}: {e}', file=sys.stderr, flush=True)
        time.sleep(shag)


if __name__ == '__main__':
    main()

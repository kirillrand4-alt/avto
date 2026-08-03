# -*- coding: utf-8 -*-
"""Журнал сессии на дропе: писать своё, следить за чужим.

Замысел владельца 30.07.2026: у всех сессий есть дроп, пусть каждая ведёт файл «что сделано,
какие выводы и ошибки», дописывает его, а чужие проверяет часто и отвечает.

Уговор по именам ЗАКРЫТ владельцем 30.07: разговорный шаблон — `ZHURNAL-*.md`. Схем какое-то
время жило две (`SESSIYA-*` и `ZHURNAL-*`), сессии дублировали журнал под обоими именами и один
раз это уже стоило часа невидимости. Теперь один шаблон, дубли `SESSIYA-*` удаляются своими
владельцами. Сторож ищет по шаблону, а не по списку номеров: четвёртая сессия подхватится сама.

Две поправки к исходной схеме, обе по замеру, а не по вкусу:

1. **Следить по размеру нельзя.** Правка в середине файла или перезапись той же длины размера не
   меняют — изменение пройдёт молча. В листинге дропа есть `mtime`, поэтому признак изменения —
   пара `(bytes, mtime)`.
2. **Журнал только дописывается, новая запись снизу, с отметкой времени.** Если каждый
   перезаписывает файл целиком, «прочитать новое» превращается в сравнение версий. При дописывании
   новое — это просто хвост длиннее прежнего.

Заслон против потери своих же записей: перед дописыванием журнал СКАЧИВАЕТСЯ с дропа и запись
идёт в конец скачанного. Иначе две сессии, пишущие в один файл, затрут друг друга — а на дропе
последняя выгрузка выигрывает молча.

Использование:
    python3 zhurnal_sessii.py --zapis "текст записи"      # дописать и выгрузить
    python3 zhurnal_sessii.py --sled                      # следить за чужими (для Monitor)
    python3 zhurnal_sessii.py --chitat 1                  # показать чужой журнал целиком
"""
import json
import os
import subprocess
import sys
import time

BAZA = os.path.dirname(os.path.abspath(__file__))
DROP = os.path.join(BAZA, 'server', 'drop_client.sh')
MOY_NOMER = os.environ.get('ZHURNAL_NOMER', '3')
MOY = f'ZHURNAL-{MOY_NOMER}.md'
# Чужие журналы ищутся ПО ШАБЛОНУ в листинге дропа, а не по заранее известному списку имён:
# иначе новая сессия останется невидимой, пока с ней не договорятся. Ровно это и случилось,
# когда схем имён было две.
MOY_PLAN = f'PLAN-{MOY_NOMER}-SESSII.md'
# Сторож следит и за ПЛАНАМИ, не только за журналами: владелец 03.08 велел читать планы друг
# друга так же, как журналы. Имена у сессий разошлись (`PLAN-1-SESSII.md` у первой,
# `PLAN-RABOT.md` у второй), поэтому ловим по началу слова, а не по точному шаблону — иначе
# чужой план останется невидимым ровно так же, как это уже случилось с двумя схемами имён
# журналов и стоило часа невидимости.
def chuzhie(spis):
    return sorted(n for n in spis
                  if n.endswith('.md') and n not in (MOY, MOY_PLAN)
                  and (n.startswith('ZHURNAL-') or n.upper().startswith('PLAN')))
RAB = os.environ.get('ZHURNAL_RAB', '/home/user/work/zhurnal')


def spisok():
    p = subprocess.run(['bash', DROP, 'list'], capture_output=True, text=True, timeout=120)
    try:
        return {f['name']: (f['bytes'], f['mtime']) for f in json.loads(p.stdout)}
    except Exception:  # noqa: BLE001  дроп мог ответить не-JSON; молчать нельзя, но и падать зря
        return {}


def skachat(imya, kuda):
    os.makedirs(kuda, exist_ok=True)
    # ВНИМАНИЕ: клиент пишет файл сам. Перенаправлять его вывод В ФАЙЛ нельзя — оболочка и curl
    # молча портят начало, файл потом читается, а заголовка нет (предупреждение соседней сессии).
    subprocess.run(['bash', DROP, 'down', imya], cwd=kuda, capture_output=True, timeout=300)
    p = os.path.join(kuda, imya)
    return open(p, encoding='utf-8', errors='replace').read() if os.path.exists(p) else ''


def vygruzit(put):
    p = subprocess.run(['bash', DROP, 'up', os.path.basename(put)],
                       cwd=os.path.dirname(put), capture_output=True, text=True, timeout=300)
    return '"ok":true' in p.stdout.replace(' ', '')


def zapisat(tekst):
    os.makedirs(RAB, exist_ok=True)
    bylo = skachat(MOY, RAB)
    put = os.path.join(RAB, MOY)
    metka = time.strftime('%d.%m %H:%M')
    with open(put, 'w', encoding='utf-8') as f:
        f.write((bylo.rstrip() + '\n\n' if bylo.strip() else '') + f'## {metka}\n\n{tekst}\n')
    ok = vygruzit(put)
    print(f'{"выгружено" if ok else "СБОЙ ВЫГРУЗКИ"}: {MOY}, стало {os.path.getsize(put)} байт')


def sled(pauza=10):
    """Печатает строку, когда чужой журнал изменился. Каждая строка — событие для наблюдателя."""
    s = spisok()
    bylo = {c: s.get(c) for c in chuzhie(s)}
    for c, v in bylo.items():
        print(f'{c}: есть на дропе, {v[0]} байт', flush=True)
    if not bylo:
        print('чужих журналов ZHURNAL-*.md на дропе пока нет', flush=True)
    while True:
        time.sleep(pauza)
        s = spisok()
        if not s:
            continue
        for c in chuzhie(s):
            if s.get(c) != bylo.get(c):
                staro = (bylo.get(c) or (0, 0))[0]
                print(f'{"ПОЯВИЛСЯ" if c not in bylo else "ИЗМЕНИЛСЯ"} {c}: '
                      f'было {staro} байт, стало {s[c][0]}', flush=True)
                bylo[c] = s.get(c)


def main():
    if '--zapis' in sys.argv:
        zapisat(sys.argv[sys.argv.index('--zapis') + 1])
    elif '--sled' in sys.argv:
        sled(int(sys.argv[sys.argv.index('--pauza') + 1]) if '--pauza' in sys.argv else 10)
    elif '--chitat' in sys.argv:
        n = sys.argv[sys.argv.index('--chitat') + 1]
        print(skachat(f'SESSIYA-{n}.md', RAB) or f'SESSIYA-{n}.md пуст или отсутствует')
    else:
        sys.exit(__doc__)


if __name__ == '__main__':
    main()

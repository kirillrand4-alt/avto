# -*- coding: utf-8 -*-
r"""Сравнение агентов-исследователей на двух моделях (владелец 09.10: «давай» — 100 агентов на Luna и 100 на Sol по одним
и тем же компаниям; если Luna не сильно хуже, агенты сверх первой 1 000 крупных идут на Luna).

Выборка (одна на обе модели, фиксируется в pilot-ab-vybor.json): компании пилота с цифровым ИНН, у которых сайт не
подтверждён — сайта нет, он не открылся или ИНН компании на нём не найден; 100 шт. равномерно по шкале выручки.
Агент — kc_agent_glubokiy.агент, итог проверяет скрипт kc_agent_glubokiy.проверить (номер — только с открытой страницы
подтверждённого сайта завода/холдинга или карточки закупки с ИНН). Модель — env PROVIDER_MODEL процесса.

    AB_MODEL=gpt-6-luna python pilot_agenty_ab.py      -> pilot-ab-gpt-6-luna.jsonl (fsync, резюм)
"""
import io
import json
import os
import shutil
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

МОДЕЛЬ = os.environ.get('AB_MODEL', 'gpt-6-luna')
os.environ['PROVIDER_MODEL'] = МОДЕЛЬ
os.environ.setdefault('KC_NABOR', 'pilot')
os.environ.setdefault('KC_CEL', 'meyer')
DIR = r'C:\sender\server'
sys.path.insert(0, DIR)
sys.path.insert(0, r'C:\sender')
os.chdir(DIR)
import kc_agent_glubokiy as A  # noqa: E402

ВЫБОР = os.path.join(DIR, 'pilot-ab-vybor.json')
ВЫХОД = os.path.join(DIR, 'pilot-ab-%s.jsonl' % МОДЕЛЬ)
_лок = threading.Lock()


def выборка():
    if os.path.exists(ВЫБОР):
        return json.load(io.open(ВЫБОР, encoding='utf-8'))
    сп = json.load(io.open(os.path.join(DIR, 'pilot-spisok.json'), encoding='utf-8'))['компании']
    конт = {}
    for s in io.open(os.path.join(DIR, 'pilot-kontakty.jsonl'), encoding='utf-8', errors='replace'):
        з = json.loads(s)
        if з.get('итог') == 'ok':
            конт[з['inn']] = з
    канд = []
    for i, к in сп.items():
        if not i.isdigit():
            continue
        з = конт.get(i) or {}
        сайт = з.get('сайт') or ''
        открылся = any(ст == 'ok' for _, ст in з.get('страницы', []))
        if сайт and открылся and i in (з.get('инн_живой') or []):
            continue  # сайт подтверждён ИНН — агенту делать нечего
        канд.append(dict(к, отклонены=MN_домен(сайт) if сайт else ''))
    # равномерно по всей шкале выручки, а не топ-100: Luna предлагается для компаний ПОСЛЕ первой 1 000 крупных
    канд.sort(key=lambda к: -(к.get('выручка') or 0))
    шаг = max(1, len(канд) // 100)
    выбор = канд[::шаг][:100]
    with io.open(ВЫБОР, 'w', encoding='utf-8') as f:
        json.dump(выбор, f, ensure_ascii=False)
    return выбор


def MN_домен(u):
    import meyer_nalichie as MN
    return MN.домен(u)


def main():
    выбор = выборка()
    сделано = set()
    if os.path.exists(ВЫХОД):
        for s in io.open(ВЫХОД, encoding='utf-8', errors='replace'):
            сделано.add(json.loads(s)['inn'])
    задачи = [к for к in выбор if к['inn'] not in сделано]
    print('модель', МОДЕЛЬ, 'компаний', len(выбор), 'в очереди', len(задачи), flush=True)

    def одна(к):
        t0 = time.time()
        try:
            итог, открыто, история = A.агент(к)
            рез = A.проверить(к, итог, открыто) if итог else {'пояснение': 'агент не дал итог', 'номера': [], 'снято': []}
            рез.update({'итог': 'ok', 'шагов': len(история), 'страниц_открыто': len(открыто),
                        'поисков': sum(1 for h in история if h.startswith('ПОИСК'))})
        except Exception as e:  # noqa: BLE001
            рез = {'итог': 'сбой', 'ошибка': repr(e)[:150]}
        рез.update({'inn': к['inn'], 'имя': к['имя'], 'выручка': к.get('выручка'), 'сек': round(time.time() - t0)})
        with _лок:
            with io.open(ВЫХОД, 'a', encoding='utf-8') as f:
                f.write(json.dumps(рез, ensure_ascii=False) + '\n')
                f.flush()
                os.fsync(f.fileno())

    with ThreadPoolExecutor(10) as ex:
        list(ex.map(одна, задачи))
    shutil.copyfile(ВЫХОД, os.path.join(r'C:\seostat\drop\drop-storage', os.path.basename(ВЫХОД)))
    print('готово', flush=True)


if __name__ == '__main__':
    main()

# -*- coding: utf-8 -*-
r"""Фильтр КЦ/Meyer в очереди подтверждения — считать на сервере, а не в браузере.

Локальный фильтр смотрел на метку КОМПАНИИ (`panel.company.division`) и
показывал письмо в обеих очередях, когда метка пуста. У «Русского радиатора»
метки нет, письмо чисто компрессорное (letter_division='kc'), и оператор видел
его при выбранном Meyer. Серверный предикат в /confirm/queue берёт направление
ПИСЬМА и такие письма отсекает — надо просто начать передавать division.
"""
import json
import os
import shutil

БАЗА = r'C:\sender\_tmp\web-src-iz-mapy'
ПРАВКИ = r'C:\sender\_tmp\web-pravki'
d = {}


def взять(отн):
    """Файл из правок; если его там нет — кладём туда копию базового."""
    цель = os.path.join(ПРАВКИ, отн.replace('/', os.sep))
    if not os.path.exists(цель):
        исток = os.path.join(БАЗА, отн.replace('/', os.sep))
        os.makedirs(os.path.dirname(цель), exist_ok=True)
        shutil.copy2(исток, цель)
        d.setdefault('скопировано_в_правки', []).append(отн)
    with open(цель, encoding='utf-8') as f:
        return цель, f.read()


def заменить(текст, было, стало, метка):
    if стало in текст:
        d.setdefault('уже_стояло', []).append(метка)
        return текст
    if было not in текст:
        d.setdefault('НЕ_НАШЁЛ', []).append(метка)
        return текст
    d.setdefault('заменено', []).append(метка)
    return текст.replace(было, стало, 1)


путь_c, c = взять('api/client.ts')
c = заменить(
    c,
    "  confirmQueue(f: { campaign_id?: number; limit?: number; gruppa?: string;\n"
    "                    hide_blocked?: boolean } = {}): Promise<{",
    "  confirmQueue(f: { campaign_id?: number; limit?: number; gruppa?: string;\n"
    "                    division?: string; hide_blocked?: boolean } = {}): Promise<{",
    'client.ts: division в типе запроса')

путь_f, f = взять('screens/Confirm.tsx')
f = заменить(
    f,
    '    queryKey: ["confirm-queue", limit, группа, прятатьЖдущих],\n'
    '    queryFn: () => api.confirmQueue({ limit, ...(группа ? { gruppa: группа } : {}),\n'
    '                                      ...(прятатьЖдущих ? { hide_blocked: true } : {}) }),',
    '    queryKey: ["confirm-queue", limit, группа, прятатьЖдущих, напр],\n'
    '    // Направление считает СЕРВЕР. Локальный фильтр смотрел на метку КОМПАНИИ,\n'
    '    // а она у многих пуста — и компрессорное письмо было видно в очереди\n'
    '    // Meyer (владелец 21.08, письмо #3585 «Русский радиатор»: текст, ящик и\n'
    '    // подпись компрессорные при выбранном Meyer). Серверный предикат берёт\n'
    '    // направление ПИСЬМА (letter_division) и такие письма отсекает.\n'
    '    queryFn: () => api.confirmQueue({ limit, ...(группа ? { gruppa: группа } : {}),\n'
    '                                      ...(напр && напр !== "все" ? { division: напр } : {}),\n'
    '                                      ...(прятатьЖдущих ? { hide_blocked: true } : {}) }),',
    'Confirm.tsx: division уходит в запрос')
f = заменить(
    f,
    '  const поНапр: ConfirmReview[] = напр === "все" ? list\n'
    '    : list.filter((r) => {\n'
    '        const d = ((r.panel as ConfirmPanel)?.company?.division || "").toLowerCase();\n'
    '        if (!d) return true;               // без направления — видно всем\n'
    '        return d.includes(напр);           // kc+meyer попадает в оба фильтра\n'
    '      });',
    '  // Фильтр направления отработал НА СЕРВЕРЕ (division в запросе очереди), и\n'
    '  // счётчик «N из M» после этого перестал врать: раньше сервер присылал\n'
    '  // полсотни писем, браузер выбрасывал из них чужие и показывал «29 из 50».\n'
    '  const поНапр: ConfirmReview[] = list;',
    'Confirm.tsx: убран локальный фильтр')

if 'НЕ_НАШЁЛ' not in d:
    with open(путь_c, 'w', encoding='utf-8', newline='') as fh:
        fh.write(c)
    with open(путь_f, 'w', encoding='utf-8', newline='') as fh:
        fh.write(f)
    d['записано'] = [путь_c, путь_f]
d['сборщик'] = {п: os.path.exists(п) for п in
                (r'C:\sender\server\sobrat_front.py', r'C:\sender\sobrat_front.py')}
print(json.dumps(d, ensure_ascii=False, indent=1))

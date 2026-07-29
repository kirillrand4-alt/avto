# -*- coding: utf-8 -*-
"""Разбор свободного текста комментариев Tender.pro провайдерским API.

Мехразбор регулярками ловит наличие контакта, но путает падежи («Метелице
Дмитрию Николаевичу»), приклеивает ФИО к горячей линии 8-800 и не достаёт
должность. Это ровно тот случай, где тяжёлую работу надо гнать через
провайдерский API, а не токенами сессии.

Вход:  tp_raw.json (сырьё со стадии сбора, ключ «карточки»)
Выход: tp_contacts.json — список контактов с ИНН, ссылкой и датой закупки.
Кэш ответов по id тендера: повторный запуск не платит заново.
"""
import json
import os
import re
import sys

sys.path.insert(0, '/home/user/avto/seo-texts')
import gen_provider as GP  # noqa: E402

МОДЕЛЬ = os.environ.get('TP_MODEL', 'claude-fable-5')
КЭШ = '/tmp/claude-0/-home-user-avto/693f5b2f-dea9-5fac-9cb3-79ec44ebf51b/scratchpad/tp_llm_cache.json'

ПРОМПТ = """Ты разбираешь текст объявления о закупке с российской тендерной
площадки и достаёшь КОНТАКТНЫХ ЛЮДЕЙ компании-организатора.

Верни СТРОГО JSON-объект {"1": [...], "2": [...]} — ключ это номер текста,
значение это массив контактов. Элемент массива строго такой:
{"person":"Фамилия Имя Отчество","post":"должность","phone":"телефон",
 "email":"почта","уверенность":"высокая|средняя|низкая"}
Никакого markdown, никаких пояснений, ключи ровно такие.

Правила:
1. ФИО приводи в ИМЕНИТЕЛЬНЫЙ падеж: «обращаться к Метелице Дмитрию
   Николаевичу» -> person «Метелица Дмитрий Николаевич»; «к начальнику отдела
   оборудования Евгению Епишеву» -> person «Епишев Евгений»,
   post «начальник отдела оборудования».
2. Должность тоже в именительный: «управляющего отбором» -> «управляющий
   отбором». Нет должности в тексте — post пустая строка. НЕ ДОГАДЫВАЙСЯ.
3. Телефон и почту привязывай к тому человеку, рядом с кем они стоят. Два
   человека и две почты — ДВЕ записи. Непонятно, чей контакт — оставь поле
   пустым и поставь уверенность «низкая». НЕ приписывай человеку чужой адрес.
4. НЕ БЕРИ контакты самой площадки (tender.pro, 8-495-215-14-38), горячие
   линии и «службы доверия» (8-800…, hotline@, signal@) — это не контактное
   лицо, и человеку такой номер приписывать НЕЛЬЗЯ.
5. Телефон бери целиком, как в тексте. Обрывок без кода города не бери.
6. Контактных людей нет — верни для этого текста [].
7. Ничего не выдумывай: значения должны буквально быть в тексте (кроме падежа).
"""


def нормализовать(x):
    """Провайдер иногда отвечает своей схемой (name/position/note) — принимаем."""
    if not isinstance(x, dict):
        return None
    def взять(*ключи):
        for k in ключи:
            v = x.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
        return ''
    тел = взять('phone', 'tel', 'телефон')
    if тел and len(re.sub(r'\D', '', тел)) < 10:
        тел = ''                       # обрывок без кода города — не телефон
    поч = взять('email', 'mail', 'почта').lower()
    if поч and not re.match(r'^[\w.\-]+@[\w\-]+(\.[\w\-]+)+$', поч):
        поч = ''
    чел = взять('person', 'name', 'fio', 'фио')
    должн = взять('post', 'position', 'должность', 'role')
    if not (тел or поч or чел):
        return None
    return {'person': чел[:120], 'post': должн[:160], 'phone': тел[:60],
            'email': поч[:120],
            'уверенность': взять('уверенность', 'confidence') or 'средняя'}


def разобрать(тексты, client):
    блоки = [f'=== ТЕКСТ {i + 1} ===\n{t[:2200]}' for i, t in enumerate(тексты)]
    msg = GP.call(client, [{'role': 'user',
                            'content': ПРОМПТ + '\n\n' + '\n\n'.join(блоки)}],
                  model=МОДЕЛЬ, attempts=3)
    txt = ''.join(b.text for b in msg.content if b.type == 'text').strip()
    txt = re.sub(r'^```(?:json)?|```$', '', txt, flags=re.M).strip()
    m = re.search(r'\{.*\}', txt, re.S)
    if not m:
        return [[] for _ in тексты]
    try:
        d = json.loads(m.group(0))
    except Exception:  # noqa: BLE001
        return [[] for _ in тексты]
    out = []
    for i in range(len(тексты)):
        v = d.get(str(i + 1))
        v = v if isinstance(v, list) else []
        out.append([y for y in (нормализовать(z) for z in v) if y])
    return out


def main():
    сыр = json.load(open(sys.argv[1], encoding='utf-8'))
    карт = сыр['карточки'] if isinstance(сыр, dict) else сыр
    кэш = {}
    if os.path.exists(КЭШ):
        try:
            кэш = json.load(open(КЭШ, encoding='utf-8'))
        except Exception:  # noqa: BLE001
            кэш = {}
    надо = [k for k in карт if k['tender_id'] not in кэш]
    print(f'карточек {len(карт)}, в кэше {len(карт) - len(надо)}, к разбору {len(надо)}',
          file=sys.stderr)
    cl = GP.make_client()
    ПАЧКА = 5
    for i in range(0, len(надо), ПАЧКА):
        часть = надо[i:i + ПАЧКА]
        try:
            рез = разобрать([x['comment'] for x in часть], cl)
        except Exception as ex:  # noqa: BLE001
            print('сбой пачки', i, repr(ex)[:140], file=sys.stderr)
            рез = [[] for _ in часть]
        for x, r in zip(часть, рез):
            кэш[x['tender_id']] = r
        with open(КЭШ, 'w', encoding='utf-8') as f:
            json.dump(кэш, f, ensure_ascii=False)
        print(f'.. {min(i + ПАЧКА, len(надо))}/{len(надо)}', file=sys.stderr)
    вых = []
    for k in карт:
        for c in кэш.get(k['tender_id']) or []:
            вых.append(dict(c, inn=k['inn'], url=k['url'], дата=k['дата'],
                            свежесть=k['свежесть'], предмет=k.get('предмет', ''),
                            company=k.get('company', '')))
    json.dump(вых, open(sys.argv[2], 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print(json.dumps({'карточек': len(карт), 'контактов': len(вых),
                      'с_ФИО': sum(1 for x in вых if x['person']),
                      'с_должностью': sum(1 for x in вых if x['post']),
                      'уник_ИНН': len({x['inn'] for x in вых})},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()

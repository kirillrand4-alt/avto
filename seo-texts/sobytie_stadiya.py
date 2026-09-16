# -*- coding: utf-8 -*-
"""Классификатор СТАДИИ проекта по тексту события.

Зачем. У сигнала есть тип события (модернизация/новый завод/запуск линии), но тип - это
ЧТО происходит, а не КОГДА в жизни проекта. Вход «от события на ранней стадии» требует
второго: намерение это или уже ввод. Тип и стадия не совпадают: «новый завод» бывает и
подписанным соглашением (рано, машина ещё не выбрана), и перерезанной лентой (поздно,
всё куплено без нас).

Шкала от ранней к поздней:
    намерение · планирование · проектирование · финансирование · стройка · оснащение ·
    ввод · эксплуатация
Три самые ранние (намерение, планирование, проектирование) - целевая очередь.

ДВА РЕЖИМА, оба через один код:
    stadiya_odnogo(tekst)      - одно событие (новый поток идёт по одному);
    stadiya_pachkoy([...])     - пачка (испытания на старых строках, дешевле по вызовам).

ТРИ ОТВЕТА, КОТОРЫЕ НЕЛЬЗЯ ПУТАТЬ (ради этого весь протокол):
    status='ok'                - модель назвала стадию;
    status='ne_opredelit'      - модель ОТВЕТИЛА «признаков стадии в тексте нет»;
    status='sboy_provaydera'   - вызов НЕ СОСТОЯЛСЯ (сеть/шлюз/пустой ответ).
Третье - НЕ голос. Если сбой смешать с «не знаю», распределение по стадиям молча
занижается на долю упавших вызовов, и чем хуже связь, тем «раньше» выглядит база.
Четвёртый случай: модель вернула ответ, но потеряла строку - status='net_v_otvete',
тоже не голос.

Провайдер берётся по месту запуска:
  - песочница: seo-texts/gen_provider.py (make_client + call), ключ из окружения;
  - сервер владельца: verify_company._provider_call_stdlib (там gen_provider нет).
"""
import json
import os
import re
import sys

DIR = os.path.dirname(os.path.abspath(__file__))

STADII = ['намерение', 'планирование', 'проектирование', 'финансирование',
          'стройка', 'оснащение', 'ввод', 'эксплуатация']
RANNIE = STADII[:3]            # целевая очередь: три самые ранние
NOMER = {s: i + 1 for i, s in enumerate(STADII)}

# синонимы, которыми модель может назвать ту же стадию
SINONIMY = {
    'намерение/решение': 'намерение', 'решение': 'намерение', 'намерения': 'намерение',
    'планирование/подготовка': 'планирование', 'подготовка': 'планирование',
    'проект': 'проектирование', 'проектная документация': 'проектирование',
    'финансы': 'финансирование', 'займ': 'финансирование',
    'строительство': 'стройка', 'смр': 'стройка',
    'оборудование': 'оснащение', 'закупка': 'оснащение', 'закупки': 'оснащение',
    'монтаж': 'оснащение', 'пусконаладка': 'ввод', 'пуск': 'ввод', 'запуск': 'ввод',
    'ввод в эксплуатацию': 'ввод', 'работа': 'эксплуатация', 'действующее': 'эксплуатация',
}

OTRASLI = ['химия и нефтехимия', 'металлургия', 'пищевая', 'фармацевтика',
           'целлюлозно-бумажная', 'энергетика', 'стекольная', 'цементная', 'прочее']

PROMPT = """Ты разбираешь короткие сводки промышленных новостей России. Для КАЖДОЙ сводки
определи СТАДИЮ проекта - на каком этапе жизненного пути находится описанное дело ИМЕННО В
МОМЕНТ НОВОСТИ, а не к чему оно приведёт потом.

Шкала, выбирай РОВНО ОДНО значение из восьми:
1 намерение - решение объявлено, работ нет: соглашение о намерениях, меморандум, инвестсовет
  одобрил, компания заявила о планах, статус резидента ОЭЗ/ТОР/АЗРФ, СЗПК, СПИК.
2 планирование - дело пошло в бумаги территории: генплан, ППТ, публичные слушания, выделение
  или перевод участка, изменение ВРИ, заявка на техприсоединение к газу и электросетям.
3 проектирование - делается проект: проектная документация, изыскания, ОВОС, госэкспертиза,
  заключение экспертизы, выбран проектировщик.
4 финансирование - деньги под проект: одобрен займ ФРП, кредитная линия, субсидия, облигации
  под проект, вошёл инвестор.
5 стройка - идут строительно-монтажные работы: разрешение на строительство, фундамент,
  возводят корпус, выбран генподрядчик, «строится», «ведётся строительство».
6 оснащение - в объект ставят оборудование: закупка, поставка, монтаж, шефмонтаж,
  пусконаладка, тендер на оборудование, «завозят линию».
7 ввод - пуск: объект введён, линия запущена, разрешение на ввод, первая продукция, открытие.
8 эксплуатация - действующее производство: вышли на проектную мощность, нарастили выпуск на
  работающем заводе, ремонт или обслуживание действующего.

ЖЁСТКИЕ ПРАВИЛА.
- Смотри на СОВЕРШЁННОЕ в тексте, а не на цель. «Подписано соглашение, завод построят к 2029»
  это намерение, а НЕ стройка. «Запустят линию в 2028 году» при идущей стройке это стройка.
- Если признаков стадии в тексте нет (общие слова, текст не про промышленный проект,
  одна безглагольная строка вроде «расширение производства») - верни stadiya:"" и
  uverennost:"низкая". НЕ УГАДЫВАЙ и не достраивай текст за автора.
- Если текст выглядит выдуманным или бессмысленным (производство того, чего не бывает;
  несуществующие единицы измерения; набор слов) - верни stadiya:"" и vydumka:true.
- zacepka - ДОСЛОВНАЯ цитата из сводки (до 80 знаков), по которой выбрана стадия. Нет
  цитаты - значит нет и стадии.
- otrasl - одно из: химия и нефтехимия, металлургия, пищевая, фармацевтика,
  целлюлозно-бумажная, энергетика, стекольная, цементная, прочее. Ставь ШИРОКО по смыслу
  производства, при сомнении пиши «прочее».

Верни СТРОГО JSON-массив без markdown, по одному объекту на КАЖДЫЙ входной id:
[{"id":1,"stadiya":"стройка","uverennost":"высокая|средняя|низкая","zacepka":"...",
  "otrasl":"металлургия","vydumka":false}]

СВОДКИ:
"""


# --------------------------------------------------------------- транспорт
def _zvat_pesochnica(prompt, model, attempts):
    sys.path.insert(0, DIR)
    import gen_provider as G
    if not os.path.exists(os.path.join(DIR, '.env')):
        G.env = lambda: {'PROVIDER_API_KEY': os.environ['PROVIDER_API_KEY'],
                         'PROVIDER_BASE_URL': os.environ.get('PROVIDER_BASE_URL',
                                                             'https://router.cheap')}
    msg = G.call(None, [{'role': 'user', 'content': prompt}], model=model, attempts=attempts)
    # у call НЕТ параметра max_tokens: передашь - TypeError и пустой прогон
    return ''.join(b.text for b in msg.content if b.type == 'text').strip()


def _zvat_server(prompt, model, attempts):
    sys.path.insert(0, r'C:\sender\server')
    import verify_company as VC
    posled = None
    for _ in range(max(1, attempts)):
        try:
            out = VC._provider_call_stdlib(prompt, model=model)
        except Exception as ex:  # noqa: BLE001
            posled = repr(ex)[:160]
            continue
        if out and out.strip():
            return out.strip()
        posled = 'пустой ответ шлюза'
    raise RuntimeError('провайдер не отдал ответ: %s' % posled)


def zvat(prompt, model='claude-fable-5', attempts=3):
    """Один вызов провайдера. Кидает исключение, если ответа НЕТ - это и есть сбой,
    который не должен голосовать. Пустая строка как «ответ» не возвращается никогда."""
    try:
        import verify_company  # noqa: F401
        na_servere = True
    except Exception:  # noqa: BLE001
        na_servere = False
    tekst = (_zvat_server if na_servere else _zvat_pesochnica)(prompt, model, attempts)
    if not tekst:
        raise RuntimeError('провайдер вернул пустой текст')
    return tekst


# --------------------------------------------------------------- разбор ответа
def _vytashchit_json(tekst):
    t = re.sub(r'^```(?:json)?\s*|\s*```$', '', (tekst or '').strip())
    try:
        return json.loads(t)
    except Exception:  # noqa: BLE001
        pass
    luchshiy = None
    for m in re.finditer(r'\[', t):
        konec = t.rfind(']')
        while konec > m.start():
            try:
                d = json.loads(t[m.start():konec + 1])
                if isinstance(d, list) and (luchshiy is None or len(d) > len(luchshiy)):
                    luchshiy = d
                break
            except Exception:  # noqa: BLE001
                konec = t.rfind(']', 0, konec)
    if luchshiy is None:
        m = re.search(r'\{.*\}', t, re.S)
        if m:
            try:
                d = json.loads(m.group(0))
                luchshiy = [d] if isinstance(d, dict) else d
            except Exception:  # noqa: BLE001
                pass
    return luchshiy


def _kanon_stadiya(s):
    s = re.sub(r'^\d\s*[).:-]?\s*', '', (s or '').strip().lower()).strip(' .')
    if not s:
        return ''
    if s in NOMER:
        return s
    if s in SINONIMY:
        return SINONIMY[s]
    for st in STADII:                      # «стройка (СМР)» и подобные хвосты
        if s.startswith(st) or st in s:
            return st
    return ''


def _kanon_otrasl(s):
    s = (s or '').strip().lower()
    if not s:
        return ''
    for o in OTRASLI:
        if o in s or s in o:
            return o
    if 'нефте' in s or 'хим' in s:
        return 'химия и нефтехимия'
    if 'метал' in s or 'сталь' in s:
        return 'металлургия'
    if 'пищ' in s or 'агро' in s or 'продукт' in s:
        return 'пищевая'
    if 'фарм' in s or 'мед' in s:
        return 'фармацевтика'
    if 'бумаж' in s or 'цбк' in s or 'целлюл' in s:
        return 'целлюлозно-бумажная'
    if 'энерг' in s or 'тэц' in s or 'гэс' in s:
        return 'энергетика'
    if 'стекл' in s:
        return 'стекольная'
    if 'цемент' in s or 'бетон' in s:
        return 'цементная'
    return 'прочее'


# --------------------------------------------------------------- классификация
def stadiya_pachkoy(zapisi, model='claude-fable-5', attempts=3, max_znakov=900):
    """zapisi: [{'id': ..., 'tekst': ...}] -> {id: {...}}.

    Сбой вызова помечает ВСЮ пачку статусом sboy_provaydera - и ни одна её строка
    не попадает в распределение по стадиям.
    """
    if not zapisi:
        return {}
    spisok = []
    for i, z in enumerate(zapisi):
        t = re.sub(r'\s+', ' ', str(z.get('tekst') or '')).strip()[:max_znakov]
        spisok.append({'id': z['id'], 'tekst': t})
    prompt = PROMPT + json.dumps(spisok, ensure_ascii=False, indent=None)
    itog = {}
    try:
        syro = zvat(prompt, model=model, attempts=attempts)
    except Exception as ex:  # noqa: BLE001
        for z in zapisi:
            itog[z['id']] = {'status': 'sboy_provaydera', 'stadiya': '', 'uverennost': '',
                             'zacepka': '', 'otrasl': '', 'vydumka': None,
                             'oshibka': repr(ex)[:200]}
        return itog
    dannye = _vytashchit_json(syro)
    if not isinstance(dannye, list):
        for z in zapisi:
            itog[z['id']] = {'status': 'sboy_provaydera', 'stadiya': '', 'uverennost': '',
                             'zacepka': '', 'otrasl': '', 'vydumka': None,
                             'oshibka': 'в ответе нет JSON-массива: ' + (syro or '')[:120]}
        return itog
    po_id = {}
    for d in dannye:
        if isinstance(d, dict) and 'id' in d:
            po_id[str(d['id'])] = d
    for z in zapisi:
        d = po_id.get(str(z['id']))
        if d is None:
            itog[z['id']] = {'status': 'net_v_otvete', 'stadiya': '', 'uverennost': '',
                             'zacepka': '', 'otrasl': '', 'vydumka': None, 'oshibka': ''}
            continue
        st = _kanon_stadiya(d.get('stadiya'))
        uv = (d.get('uverennost') or '').strip().lower()
        uv = uv if uv in ('высокая', 'средняя', 'низкая') else 'низкая'
        zac = re.sub(r'\s+', ' ', str(d.get('zacepka') or '')).strip()[:120]
        vyd = bool(d.get('vydumka'))
        itog[z['id']] = {'status': 'ok' if st else 'ne_opredelit',
                         'stadiya': st, 'nomer_stadii': NOMER.get(st, 0),
                         'uverennost': uv if st else 'низкая',
                         'zacepka': zac, 'otrasl': _kanon_otrasl(d.get('otrasl')),
                         'vydumka': vyd, 'oshibka': ''}
    return itog


def stadiya_odnogo(tekst, model='claude-fable-5', attempts=3):
    """Одно событие - один вызов. Ровно тот же промпт и тот же протокол статусов,
    чтобы новый поток и испытания мерились одной линейкой."""
    r = stadiya_pachkoy([{'id': 'odin', 'tekst': tekst}], model=model, attempts=attempts)
    return r.get('odin', {'status': 'net_v_otvete', 'stadiya': ''})


# --------------------------------------------------------------- приманки (контроль А)
PRIMANKI = [
    ('primanka-1',
     'ООО «Сиреневый Кварц» сообщило о переводе третьего цеха на лунный календарь и о '
     'запуске линии по производству дождевых облаков мощностью 12 тыс. тонн в год. '
     'Инвестиции составят 4,8 млрд рублей, подрядчиком выступит артель «Полдень».'),
    ('primanka-2',
     'Коллектив предприятия провёл субботник у проходной: высажено 40 саженцев липы, '
     'проведён конкурс детского рисунка, ветеранам вручены памятные подарки.'),
    ('primanka-3',
     'Компания продолжает работу в штатном режиме и выполняет обязательства перед '
     'партнёрами, сообщила пресс-служба.'),
    ('primanka-4',
     'Завод «Тихий Полуостров» получил заключение о соответствии выпускаемой продукции '
     'стандарту ГОСТ Р 9999-3000 на телепортацию сыпучих грузов и приступает ко второму '
     'этапу модернизации цеха антигравитации.'),
]


def podmeshat_primanki(zapisi, skolko=1, smeshchenie=0):
    """Подмешать выдуманные тексты в пачку. Возвращает (пачка, id приманок)."""
    p = [PRIMANKI[(smeshchenie + i) % len(PRIMANKI)] for i in range(skolko)]
    nabor = list(zapisi)
    ids = []
    for k, (pid, txt) in enumerate(p):
        uid = '%s-%d' % (pid, smeshchenie)
        mesto = min(len(nabor), (k + 1) * max(1, len(nabor) // (skolko + 1)))
        nabor.insert(mesto, {'id': uid, 'tekst': txt})
        ids.append(uid)
    return nabor, ids


if __name__ == '__main__':
    t = ' '.join(sys.argv[1:]) or PRIMANKI[0][1]
    print(json.dumps(stadiya_odnogo(t), ensure_ascii=False, indent=2))

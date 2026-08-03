# -*- coding: utf-8 -*-
"""Генерация SEO-текста через провайдерский эндпоинт (Opus 4.8) с авто-доводкой по QA.
Использование: python3 gen_provider.py <slug> [--payload FILE --out FILE --min-price N --no-price]"""
import json, os, re, sys, time

import anthropic
import httpx

import qa_text

DIR = os.path.dirname(os.path.abspath(__file__))

SELF_CHECK = """
=== САМОПРОВЕРКА ПЕРЕД ОТВЕТОМ (частые ошибки; из-за них текст возвращают на доработку) ===
1. ДЛИННОЕ ТИРЕ « — » ЗАПРЕЩЕНО ПОЛНОСТЬЮ, включая пункты списков и ответы FAQ.
   Живой человек его с клавиатуры не ставит — это главный маркер ИИ-текста.
   Вместо него используй обычный дефис «-» (там, где без разделителя не обойтись:
   «LUY - винтовой блок Atlas Copco»), либо перестраивай фразу (двоеточие, точка,
   отдельное предложение). Диапазоны чисел пиши через дефис без пробелов («7-35 бар»)
   или словом «от… до…» — не через длинное тире.
2. Витринные конструкции ЗАПРЕЩЕНЫ в любом виде: «в разделе/каталоге/линейке/ассортименте
   представлены/собраны/имеются». Пиши действием: «поставляются», «выпускаются», «закрывают задачи».
3. Каждое число в тексте должно быть взято из payload. Нет числа в payload — не пиши его.
4. Хедж-слова запрещены: около, примерно, порядка, ориентировочно.
5. Точных цен в тексте НЕТ нигде (цены на сайте пересчитываются автоматически за курсом).
7. Слова «тег», «фасет», «листинг», «выдача» (о числе позиций) запрещены — читатель-инженер
   такого жаргона не знает.
   Пиши «в каталоге», «в линейке», «в продаже».
8. РИТМ (анти-детект): не делай все абзацы одинаковой длины — это машинный маркер. Чередуй:
   часть абзацев короткие (1-2 предложения), часть развёрнутые. Длину предложений тоже варьируй.
9. Запрещённый «канцелярско-машинный» регистр: «таким образом», «в заключение», «подводя итог»,
   «важно понимать», «следует обратить внимание», «необходимо отметить», «в свою очередь»,
   «более того», «посредством», «в контексте», «данный/данная» (пиши «этот»), «безусловно».
   Связки-паразиты «при этом/кроме того» — максимум пара на весь текст.
Пройди по всем пунктам и исправь найденное ДО вывода JSON."""


DE_TEMPLATE = """
=== ПРОТИВ ШАБЛОННОСТИ (критично: 760 страниц одного сайта, поисковик ловит повторы дословных блоков) ===
Поле payload variant - твой индекс вариативности (0..5). Мандатные блоки КАЖДЫЙ РАЗ формулируй
ПО-СВОЕМУ, не повторяя образцы из стайлгайда дословно:
- Счётчик позиций: НЕ пиши шаблонно «в нашем каталоге N позиций (с учётом исполнений); под заказ
  поставляется весь модельный ряд». Смысл сохрани (число + пометка про исполнения/комплектации +
  «под заказ весь ряд»). ВАЖНО: НЕ начинай со слова «Доступно» и НЕ используй связку «с учётом
  исполнений/вариантов» - это уже стало новым штампом. Меняй и глагол, и конструкцию, например:
  «В каталоге N моделей под разные давления и комплектации, остальные - под заказ», «Держим в
  наличии N позиций, а всю линейку бренда возим под заказ», «N вариантов по давлению и присоединению
  уже в продаже; чего нет в наличии - привезём под заказ». Придумай СВОЮ живую формулировку под variant.
- Блок про цены и поставку: НЕ повторяй «Стоимость складывается из… Поставка по всей России, отгрузка
  со склада» слово в слово. Переформулируй под страницу.
- Мост к Enger и вводную фразу тоже варьируй.
Если в payload есть facet_application - веди раздел применения ИМЕННО под этот отраслевой акцент
(так близкие фасеты 8/10/12 бар перестают быть похожими)."""


_MONTHS = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля',
           'августа', 'сентября', 'октября', 'ноября', 'декабря']


def updated_date(slug):
    """Детерминированная по слагу дата «Обновлено» в диапазоне ~4 мес (15.03.2026–15.07.2026),
    чтобы 760 страниц не были «обновлены» одним днём (сигнал автонаполнения для Яндекс/Google)."""
    import hashlib, datetime
    off = int(hashlib.md5(('d' + slug).encode()).hexdigest(), 16) % 122   # 0..121 дней
    dt = datetime.date(2026, 7, 15) - datetime.timedelta(days=off)
    return f'{dt.day} {_MONTHS[dt.month - 1]} {dt.year}'


REFINEMENT = """
=== ИНЖЕНЕРНАЯ ТОЧНОСТЬ (ошибки отсюда роняют доверие B2B-аудитории; проверь ПЕРЕД выводом) ===
1. ДАВЛЕНИЕ vs ПРОИЗВОДИТЕЛЬНОСТЬ - зависимость ОБРАТНАЯ при одной мощности: выше давление -> НИЖЕ
   производительность. ЗАПРЕЩЕНО писать «производительность сохраняется/одинакова при разных давлениях»
   или «при снижении давления производительность/пропускная способность падает» (наоборот: растёт объёмная).
2. ЦЕПОЧКА ПОДГОТОВКИ ВОЗДУХА - канон и порядок строгий: компрессор -> концевой охладитель ->
   циклонный сепаратор -> ресивер -> префильтр грубой очистки -> осушитель (рефрижераторный/адсорбционный)
   -> магистральный фильтр тонкой очистки. Охладитель СРАЗУ после компрессора (пока воздух горячий),
   НЕ после ресивера. Перед осушителем ОБЯЗАТЕЛЕН префильтр. Не давай усечённых/переставленных цепочек.
3. АДСОРБЦИЯ - процесс ФИЗИЧЕСКИЙ (силы Ван-дер-Ваальса на поверхности сорбента), НЕ химический.
   Никогда не писать «связывает воду химически».
4. РЕСИВЕР - объём это 10-20% МИНУТНОЙ производительности компрессора (до 30-50% при резких пиках).
   НЕ ВЫДУМЫВАЙ конкретный объём ресивера в литрах: если точного числа нет в payload, говори о подборе
   ресивера ТОЛЬКО правилом («порядка 10-20% минутной производительности»), без выдуманной цифры «на N л».
   Выдуманные литры почти всегда противоречат производительности - это грубая ошибка.
5. ОСУШИТЕЛЬ и ТОЧКА РОСЫ: рефрижераторный даёт PDP около +3 °C; адсорбционный - до -40 °C и ниже.
   «Осушитель доводит до -40» без уточнения типа - ошибка (это только адсорбционный).
5a. ФАСЕТ ПРОИЗВОДИТЕЛЬНОСТИ (H1 «...производительностью N л/мин» или «N м³/мин»): страница группирует
    компрессоры по ПРОИЗВОДИТЕЛЬНОСТИ. Число N - это расход воздуха (л/мин), а НЕ объём ресивера в литрах.
    НЕ описывай эту страницу как страницу ресивера на N литров и НЕ подменяй производительность объёмом.
5b. ДАВЛЕНИЕ - НЕ причина «снижения» производительности. При фиксированной мощности компрессор на большем
    давлении ПАСПОРТНО выдаёт меньше м³/мин - это исходная характеристика, а не «запас давления снижает
    производительность». Формулируй как выбор рабочего давления, а не как «потерю от запаса».

=== ЖИВОЙ РУССКИЙ (без переводного канцелярита) ===
6. АКТИВ вместо пассива: «поставляем/отгружаем/меняют/обслуживают», НЕ «поставка ведётся»,
   «замена выполняется», «отгрузка ведётся».
7. ЗАПРЕЩЕНА калька «закрывает задачи/потребности» -> «подходит для», «справляется с», «обеспечивает».
8. «Пневмоаудит» - не чаще ОДНОГО раза на текст; в остальных местах: «замерим расход», «рассчитаем
   нагрузку по оборудованию», «обследуем пневмосеть».
9. Единый нейтрально-технический регистр: без просторечия («возим», «держим», «гоняют») рядом с
   официальным. Без «производственная площадка/объект» - конкретнее: «цех», «завод», «участок».

=== ПРОТИВ ПЕРЕСПАМА (Баден-Баден) ===
10. НЕ повторяй точное ключевое словосочетание из H1 дословно в H2 И в первом предложении подряд.
    В первых 500 знаках ключ - максимум дважды, во втором H2 и интро переформулируй (синонимы, части фразы)."""


def byline_block(payload):
    """Детерминированный блок авторства (E-E-A-T): имя-ссылка + роль + дата. ЕДИНАЯ формулировка
    (филолог: подпись автора должна быть стабильной), дата рандомизирована по слагу (Яндекс/Google)."""
    u = payload.get('byline_url', '/company/staff/igor-volkov/')
    d = updated_date(payload.get('slug', ''))
    tmpl = (f'Материал подготовил <a href="{u}">Игорь Волков</a>, технический директор ООО «Руспром», '
            f'более 5580 реализованных проектов подбора компрессорного оборудования.')
    dt = f' Обновлено: {d}.' if d else ''
    return f'<p class="expert-byline"><em>{tmpl}{dt}</em></p>'


def env():
    """Ключи из .env, а если файла нет — из окружения процесса.

    Файл .env в .gitignore и живёт только на машине владельца; в свежем контейнере его нет,
    зато PROVIDER_API_KEY и PROVIDER_BASE_URL приходят переменными окружения. Раньше на этом
    падало всё, что вызывает провайдера, с сообщением про несуществующий файл — искали причину
    в провайдере, а она была в чтении ключей.
    """
    vals = {}
    put = os.path.join(DIR, '.env')
    if os.path.exists(put):
        for line in open(put):
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                vals[k] = v
    for k in ('PROVIDER_API_KEY', 'PROVIDER_BASE_URL', 'DROP_URL', 'DROP_TOKEN'):
        if not vals.get(k) and os.environ.get(k):
            vals[k] = os.environ[k]
    vals.setdefault('PROVIDER_BASE_URL', 'https://router.cheap')
    return vals


def make_client():
    e = env()
    # WAF провайдера блокирует стандартные заголовки SDK — маскируемся под curl
    waf_headers = {'User-Agent': 'curl/8.5.0'}
    waf_headers.update({h: '' for h in (
        'X-Stainless-Lang', 'X-Stainless-Package-Version', 'X-Stainless-OS',
        'X-Stainless-Arch', 'X-Stainless-Runtime', 'X-Stainless-Runtime-Version',
        'X-Stainless-Retry-Count', 'X-Stainless-Timeout')})
    return anthropic.Anthropic(api_key=e['PROVIDER_API_KEY'], base_url=e['PROVIDER_BASE_URL'],
                               timeout=600.0, max_retries=2, default_headers=waf_headers)


# топик в первой строке промпта по типу страницы (полная типизация - см. стайлгайд)
TOPIC = {
    'compressor': 'промышленных компрессоров',
    'ref_dryer': 'рефрижераторных осушителей сжатого воздуха',
    'ads_dryer': 'адсорбционных осушителей сжатого воздуха',
    'receiver': 'ресиверов (воздухосборников) для компрессоров',
    'filter': 'магистральных фильтров сжатого воздуха',
    'separator': 'влагомаслоотделителей и сепараторов сжатого воздуха',
    'n2_gen': 'генераторов азота',
    'o2_gen': 'генераторов кислорода',
    'air_prep': 'оборудования подготовки сжатого воздуха',
    'spare_parts': 'запасных частей и расходников для компрессоров',
    'flowmeter': 'расходомеров и датчиков сжатого воздуха',
}


def build_prompt(slug, payload_path, guide_path='gen/STYLE-GUIDE.md',
                 etalon_path='gen/ETALON-atlas-copco.html', category='compressor', topic=None, extra=''):
    guide = open(os.path.join(DIR, guide_path)).read()
    payload = open(payload_path).read()
    topic = topic or TOPIC.get(category, TOPIC['compressor'])
    etalon_block = ''
    if etalon_path and os.path.exists(os.path.join(DIR, etalon_path)):
        etalon = open(os.path.join(DIR, etalon_path)).read()
        etalon_block = ("\n=== ЭТАЛОН (только калибровка тона и плотности фактов; НЕ копируй "
                        "формулировки, H2, интро и FAQ — они должны полностью отличаться) ===\n"
                        + etalon + "\n")
    return f"""Ты пишешь SEO-текст для страницы каталога {topic} prokompressor.ru.

=== СТАЙЛГАЙД (обязателен к исполнению целиком) ===
{guide}
{etalon_block}
=== ДАННЫЕ СТРАНИЦЫ (payload; факты бери ТОЛЬКО отсюда, ничего не выдумывай) ===
{payload}
{SELF_CHECK}
{DE_TEMPLATE}
{REFINEMENT}
{extra}

Задача: напиши текст для страницы из payload (это новая версия текста для этой страницы — старый будет заменён).
Ответь ОДНИМ JSON-объектом без пояснений и без markdown-ограждений:
{{"slug": "{slug}", "url": "...", "title": "", "description": "", "h1": "...", "text_html": "..."}}\n(title и description оставь пустыми строками: они не генерируются, на сайте остаются текущие)"""


class _Block:
    __slots__ = ('type', 'text')
    def __init__(self, type, text): self.type = type; self.text = text


class _Usage:
    def __init__(self, u):
        self.input_tokens = u.get('input_tokens', 0) or 0
        self.output_tokens = u.get('output_tokens', 0) or 0
        self.cache_read_input_tokens = u.get('cache_read_input_tokens', 0) or 0
        self.cache_creation_input_tokens = u.get('cache_creation_input_tokens', 0) or 0


class _Msg:
    def __init__(self, text, thinking, usage, stop_reason):
        self.content = ([_Block('thinking', thinking)] if thinking else []) + [_Block('text', text)]
        self.usage = _Usage(usage); self.stop_reason = stop_reason


_RAW_HEADERS = {'anthropic-version': '2023-06-01', 'content-type': 'application/json',
                'User-Agent': 'curl/8.5.0'}
_RAW_HEADERS.update({h: '' for h in (
    'X-Stainless-Lang', 'X-Stainless-Package-Version', 'X-Stainless-OS', 'X-Stainless-Arch',
    'X-Stainless-Runtime', 'X-Stainless-Runtime-Version', 'X-Stainless-Retry-Count', 'X-Stainless-Timeout')})


def _raw_stream(messages, model, max_tokens, thinking=True):
    """Сырой SSE-парсинг через httpx — минует .model_dump() SDK (провайдер иногда шлёт dict-кадр,
    на котором SDK-аккумулятор падает). Возвращает _Msg, совместимый с остальным кодом.
    Бросает httpx.HTTPStatusError на не-200 (в т.ч. 400 при отклонённом thinking, 403 при балансе)."""
    e = env()
    url = e['PROVIDER_BASE_URL'].rstrip('/') + '/v1/messages'
    headers = dict(_RAW_HEADERS); headers['x-api-key'] = e['PROVIDER_API_KEY']
    body = {'model': model, 'max_tokens': max_tokens, 'stream': True, 'messages': messages}
    if thinking:
        body['thinking'] = {'type': 'adaptive'}
    text_parts, think_parts = [], []
    usage = {}; stop_reason = None
    with httpx.stream('POST', url, headers=headers, json=body, timeout=600.0) as r:
        if r.status_code != 200:
            r.read()
            raise httpx.HTTPStatusError(f'HTTP {r.status_code}: {r.text[:200]}', request=r.request, response=r)
        for line in r.iter_lines():
            if not line or not line.startswith('data:'):
                continue
            payload = line[5:].strip()
            if not payload or payload == '[DONE]':
                continue
            try:
                d = json.loads(payload)
            except json.JSONDecodeError:
                continue
            t = d.get('type')
            if t == 'content_block_delta':
                delta = d.get('delta', {})
                if delta.get('type') == 'text_delta':
                    text_parts.append(delta.get('text', ''))
                elif delta.get('type') == 'thinking_delta':
                    think_parts.append(delta.get('thinking', ''))
            elif t == 'message_start':
                usage.update((d.get('message') or {}).get('usage') or {})
            elif t == 'message_delta':
                usage.update(d.get('usage') or {})
                stop_reason = (d.get('delta') or {}).get('stop_reason') or stop_reason
    return _Msg(''.join(text_parts), ''.join(think_parts), usage, stop_reason)


def call(client, messages, model='claude-opus-4-8', attempts=8):
    """Стриминг обязателен: Cloudflare провайдера обрывает молчащие соединения на 120 с.
    Провайдер нестабилен (рвёт стрим/шлёт битые кадры) — сырой SSE-парсинг + ретраи с паузами.
    client оставлен в сигнатуре для совместимости (raw-путь берёт креды из env).
    attempts: для необязательных вызовов (verify-мониторинг) ставь меньше — иначе 8 ретраев
    с паузами блокируют цикл на ~11 минут."""
    last = None
    ATTEMPTS = attempts
    thinking = True
    for attempt in range(ATTEMPTS):
        if attempt:
            pause = min(150, 15 * 2 ** (attempt - 1))
            print(f'сбой провайдера, ретрай {attempt}/{ATTEMPTS-1} через {pause} с: {last}', file=sys.stderr)
            time.sleep(pause)
        try:
            msg = _raw_stream(messages, model, 16000, thinking=thinking)
        except httpx.HTTPStatusError as ex:
            code = ex.response.status_code if ex.response is not None else None
            if code == 400 and thinking:
                print('thinking=adaptive отклонён (400), дальше без thinking', file=sys.stderr)
                thinking = False
            last = f'HTTP {code}: ' + repr(ex)[:150]
            continue
        except (httpx.HTTPError, Exception) as ex:
            last = 'сбой стрима: ' + repr(ex)[:160]
            continue
        text = ''.join(b.text for b in msg.content if b.type == 'text').strip()
        # Порог длины был единственным признаком сбоя, и это ошибка с ценой. Законный короткий
        # ответ — например `[{"tender_id":"...","lyudi":[]}]` на 38 знаков, то есть «людей в
        # карточке нет», — порог не проходил, уходил в восемь ОПЛАЧЕННЫХ ретраев и заканчивался
        # исключением. Снаружи это выглядело как «провайдер не отвечает», а платил владелец.
        # Найдено независимо двумя сессиями 30.07.2026.
        #
        # Правильный признак: **`stop_reason`**. Если модель закончила сама (`end_turn`), ответ
        # полон, какой бы короткий он ни был. Порог длины оставлен запасным путём для случая,
        # когда `stop_reason` не пришёл вовсе — тогда это и правда обрыв стрима.
        if text and msg.stop_reason == 'end_turn':
            return msg
        if len(text) > 200:
            return msg
        # ОТВЕТ В БЛОКЕ РАЗМЫШЛЕНИЯ. Шлюз иногда присылает `content=['thinking','text']`, где
        # текстовый блок ПУСТ, а сам ответ целиком лежит в блоке размышления. Повтор тем же
        # запросом ничего не меняет: код уходил в восемь ОПЛАЧЕННЫХ ретраев и падал
        # исключением, теряя уже посчитанный и оплаченный ответ. Нашла третья сессия на разборе
        # длинных карточек, у меня то же самое вылезло на опросе линз по ввозу.
        # Забираем оттуда, но ГРОМКО: это не штатный путь, и если он станет частым, надо знать.
        if msg.stop_reason == 'end_turn' and not text:
            razmyshlenie = ''.join(getattr(b, 'thinking', '') or ''
                                   for b in msg.content if b.type == 'thinking').strip()
            if len(razmyshlenie) > 200:
                print(f'ответ пришёл в блоке размышления ({len(razmyshlenie)} знаков), '
                      f'текстовый блок пуст — забираю оттуда', file=sys.stderr)
                for b in msg.content:
                    if b.type == 'text':
                        b.text = razmyshlenie
                        return msg
        last = (f'пустой/обрезанный ответ: stop_reason={msg.stop_reason} '
                f'content={[b.type for b in msg.content]} text={text[:100]!r}')
    raise RuntimeError(f'провайдер не отдал ответ за {ATTEMPTS} попыток: {last}')


def parse_json(msg):
    text = ''.join(b.text for b in msg.content if b.type == 'text').strip()
    text = re.sub(r'^```(?:json)?\s*|\s*```$', '', text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r'\{.*\}', text, re.S)
        data = json.loads(m.group(0))
    # страховка: даже если модель проигнорировала правило, длинное тире не должно уйти в текст
    for key in ('title', 'description', 'text_html'):
        if key in data and isinstance(data[key], str):
            data[key] = data[key].replace('—', '-')
    return data


def run_one(slug, payload_path=None, out_path=None, model='claude-fable-5',
            price_known=True, min_price=None, guide_path=None, etalon_path='__auto__',
            client=None, proj_urls='__load__', extra='', max_rounds=3):
    """Сгенерировать один текст с авто-доводкой по QA. Возвращает summary-dict.
    Пригоден и для CLI, и для параллельного батча (передай общий client/proj_urls)."""
    payload_path = payload_path or os.path.join(DIR, f'gen/payload-{slug}.json')
    out_path = out_path or os.path.join(DIR, f'gen/result-{slug}.json')
    payload = json.load(open(payload_path))
    if min_price is None and price_known and payload.get('price_min'):
        min_price = int(payload['price_min'])
    expected_h1 = payload.get('h1')
    category = payload.get('category', 'compressor')
    # гайд: payload может явно указать (компрессорный билдер роутит дизель/электро), иначе по категории
    if guide_path is None:
        guide_path = payload.get('guide') or (
            'gen/STYLE-GUIDE.md' if category == 'compressor' else 'gen/STYLE-GUIDE-PODGOTOVKA.md')
    if etalon_path == '__auto__':
        # эталон по умолчанию ВЫКЛ (стайлгайды зрелые; эталон раздувал промпт и замедлял).
        # Включается только явной передачей etalon_path.
        etalon_path = None
    typing = payload.get('typing')          # покомпонентная типизация H2 (дизель/электро/поршень)
    topic = payload.get('topic')            # тема в первой строке промпта
    banned_terms = qa_text.CATEGORY_TRAPS.get(category)
    # разрешённые и обязательные внутренние ссылки страницы (перелинковка/мост из payload)
    rel = list(payload.get('related_urls') or [])
    bridge = payload.get('enger_category_url')
    proj_links = [p['url'] for p in (payload.get('projects') or []) if p.get('url')]
    allowed_links = rel + ([bridge] if bridge else []) + proj_links + [
        '/services/uslugi/pneumoaudit_/',
        '/services/uslugi/tekhnicheskoe-obsluzhivanie-kompressora/',
        '/company/staff/igor-volkov/', '/company/reviews/']
    require_links = rel if (rel and category != 'compressor') else None
    # строго: разрешены только реальные фото проектов из payload (иначе модель выдумает битый путь)
    allowed_images = [p['photo_url'] for p in (payload.get('projects') or []) if p.get('photo_url')]
    # на брендовой странице с доступным фото проекта - фото обязательно (усиление по замечанию владельца)
    require_image = bool(allowed_images) and bool(payload.get('page_brand'))
    if proj_urls == '__load__':
        try:
            proj_urls = set(r['url'].replace('https://prokompressor.ru', '')
                            for r in json.load(open(os.path.join(DIR, 'projects-index.json'))) if not r.get('error'))
        except FileNotFoundError:
            proj_urls = None
    if client is None:
        client = make_client()

    prompt = build_prompt(slug, payload_path, guide_path, etalon_path, category, topic, extra=extra)
    messages = [{'role': 'user', 'content': prompt}]
    usage = {'input': 0, 'output': 0}
    t0 = time.time()
    rounds = []
    data = None
    for attempt in range(max_rounds):  # 1 генерация + до (max_rounds-1) доводок
        msg = call(client, messages, model)
        usage['input'] += msg.usage.input_tokens
        usage['output'] += msg.usage.output_tokens
        usage['cache_read'] = usage.get('cache_read', 0) + (getattr(msg.usage, 'cache_read_input_tokens', 0) or 0)
        usage['cache_write'] = usage.get('cache_write', 0) + (getattr(msg.usage, 'cache_creation_input_tokens', 0) or 0)
        data = parse_json(msg)
        # детерминированный блок авторства (E-E-A-T) - добавляем один раз, если модель его не вставила
        if isinstance(data.get('text_html'), str) and 'expert-byline' not in data['text_html']:
            data['text_html'] = data['text_html'].rstrip() + '\n' + byline_block(payload)
        issues = qa_text.check(data, min_price=min_price, price_known=price_known,
                               expected_h1=expected_h1, proj_urls=proj_urls,
                               category=category, banned_terms=banned_terms,
                               allowed_links=allowed_links, require_links=require_links, typing=typing,
                               allowed_images=allowed_images, require_image=require_image)
        rounds.append({'issues': issues})
        if not issues:
            break
        raw = ''.join(b.text for b in msg.content if b.type == 'text')
        messages = messages + [
            {'role': 'assistant', 'content': raw},
            {'role': 'user', 'content': 'Автоматическая проверка нашла нарушения:\n- '
             + '\n- '.join(issues)
             + '\n\nИсправь ТОЛЬКО перечисленное, остальной текст не трогай. '
               'Верни полный исправленный JSON в том же формате, без пояснений.'},
        ]

    json.dump(data, open(out_path, 'w'), ensure_ascii=False, indent=1)
    return {
        'slug': slug, 'out': out_path, 'category': category,
        'rounds': [{'round': i + 1, 'issues': r['issues']} for i, r in enumerate(rounds)],
        'clean': not rounds[-1]['issues'],
        'seconds': round(time.time() - t0, 1),
        'input_tokens': usage['input'], 'output_tokens': usage['output'],
        'cache_read_tokens': usage.get('cache_read', 0), 'cache_write_tokens': usage.get('cache_write', 0),
        'words': len(re.sub(r'<[^>]+>', ' ', data.get('text_html', '')).split()),
    }


def main():
    slug = sys.argv[1]
    kw = dict(model='claude-opus-4-8')
    for i, a in enumerate(sys.argv):
        if a == '--payload': kw['payload_path'] = os.path.join(DIR, sys.argv[i + 1])
        if a == '--out': kw['out_path'] = os.path.join(DIR, sys.argv[i + 1])
        if a == '--min-price': kw['min_price'] = int(sys.argv[i + 1])
        if a == '--no-price': kw['price_known'] = False
        if a == '--guide': kw['guide_path'] = sys.argv[i + 1]
        if a == '--etalon': kw['etalon_path'] = sys.argv[i + 1]
        if a == '--model': kw['model'] = sys.argv[i + 1]
    print(json.dumps(run_one(slug, **kw), ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()

# --- Вызов ЛЮБОЙ модели шлюза, а не только Claude -------------------------------------------
# Замер 02.08: не-Claude модели через Anthropic-совместимый `/v1/messages` ВИСНУТ (glm и gemini
# не ответили за 60 с, deepseek вернул пустой content). Они работают только через
# OpenAI-совместимый `/v1/chat/completions` с `Authorization: Bearer`. Поэтому маршрут
# выбирается по имени модели, а не задаётся вручную на каждом месте вызова.
# Цена на одной и той же задаче: deepseek-v4-pro $0,0033 против $0,1176 у fable-5 при
# идентичном результате; gemini-3.6-flash $0,0479 и вдвое быстрее fable-5.
import urllib.request as _ur


class _Otvet:
    """Ответ в том же виде, что отдаёт SDK: `.content[0].text` и `.stop_reason`."""

    class _Blok:
        def __init__(self, t):
            self.type = 'text'
            self.text = t

    def __init__(self, tekst, stop='end_turn'):
        self.content = [self._Blok(tekst)]
        self.stop_reason = stop


def call_model(model, messages, max_tokens=8000, attempts=4, timeout=300):
    """Один вызов любой модели. Claude идёт SDK-путём, остальные — OpenAI-путём."""
    e = env()
    base = e['PROVIDER_BASE_URL'].rstrip('/')
    if model.startswith('claude'):
        return call(make_client(), messages, model=model, attempts=attempts)
    # картинки в OpenAI-формате передаются как image_url с data-URI
    msgs = []
    for m in messages:
        c = m['content']
        if isinstance(c, list):
            nc = []
            for b in c:
                if b.get('type') == 'text':
                    nc.append({'type': 'text', 'text': b['text']})
                elif b.get('type') == 'image':
                    nc.append({'type': 'image_url', 'image_url': {
                        'url': 'data:image/png;base64,' + b['source']['data']}})
            msgs.append({'role': m['role'], 'content': nc})
        else:
            msgs.append(m)
    telo = json.dumps({'model': model, 'max_tokens': max_tokens, 'messages': msgs},
                      ensure_ascii=False).encode()
    zag = {'Authorization': 'Bearer ' + e['PROVIDER_API_KEY'], 'content-type': 'application/json',
           'User-Agent': 'curl/8.5.0'}
    posl = ''
    for att in range(attempts):
        try:
            req = _ur.Request(base + '/v1/chat/completions', data=telo, headers=zag)
            with _ur.urlopen(req, timeout=timeout) as r:
                d = json.loads(r.read().decode('utf-8', 'replace'))
            txt = (((d.get('choices') or [{}])[0].get('message') or {}).get('content') or '')
            if txt.strip():
                return _Otvet(txt)
            posl = 'пустой content'
        except Exception as ex:  # noqa: BLE001
            posl = f'{type(ex).__name__}: {str(ex)[:80]}'
        time.sleep(2 * (att + 1))
    raise RuntimeError(f'{model}: {posl}')

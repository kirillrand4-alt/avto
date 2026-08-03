# -*- coding: utf-8 -*-
"""Волна гост-постов: 5 статей на топ-5 доноров, нативная модель, 1-2 ссылки на статью.

    PROVIDER_FIRST_TOKEN_SEC=300 python3 gen_wave.py [slug ...]   # без аргументов - все JOBS

Обходы шлюза (замеры 03.08, см. README §4.10): JSON-ответы на генерационных промптах
шлюз не отдаёт (пустой text после ~9k thinking), длинный ПРОСТОЙ текст - отдаёт.
Поэтому контракт ответа - НЕ JSON: первая строка «TITLE: ...», дальше голый HTML.
Модели: черновик - gemini-3.6-flash (openai-роут, пробивает промпт за ~16с) либо
haiku; доводки - opus-4-8 (короткая задача проходит). Цепочки в DRAFT/FIX_MODELS.
Первая тема - гейт волны: если не отдалась ни одной моделью, волна прерывается.
"""
import json, os, re, sys, time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gen_provider as gp
import qa_text

DIR = os.path.dirname(os.path.abspath(__file__))
GUIDE = open(os.path.join(DIR, 'STYLE-GUIDE-GUEST.md'), encoding='utf-8').read()
# Урок волны 1 (03.08): черновик на генерационном промпте пробивает только haiku
# (у opus/sonnet форсированный thinking съедает всё и биллится пустота), а доводки
# (маленькая задача = короткий thinking) чаще проходят на opus. Поэтому два порядка.
# Префикс 'openai:' = роут /v1/chat/completions (Gemini/GPT доступны только там,
# замер 03.08: gemini-3.6-flash отдаёт полную статью за ~16с, 3.1-pro за ~90с,
# оба пробивают промпт, на котором opus/sonnet возвращают пустой text).
DRAFT_MODELS = ['openai:gemini-3.6-flash', 'claude-haiku-4-5', 'openai:gemini-3.1-pro-preview']
FIX_MODELS = ['claude-opus-4-8', 'openai:gemini-3.6-flash', 'claude-haiku-4-5']
# Потолок выхода (thinking + текст). 16000 - проектный консерватизм из gen_provider.call
# (под каталожные страницы), НЕ модельный лимит (у fable-5 - 128k). Пустые ответы 03.08
# были не из-за него (проверено на 32000 - идентично: ~9k thinking, text 0, end_turn).
MAX_TOKENS = int(os.environ.get('GP_MAX_TOKENS', '24000'))
MAX_ROUNDS = 3   # генерация + до 2 доводок

# Ссылки: [(url, инструкция по якорю)]. Всё согласовано с FINAL-ACCEPTORS (№ в комменте)
JOBS = [
 dict(slug='dizel-na-strojke', donor='kineshemec.ru',   # №7 + №13, пара производитель+каталог
  links=[('https://enger-air.ru/catalog/peredvizhnye-kompressory/dizelnye-kompressory',
          'брендовый: «дизельные компрессоры Enger» или «у производителя Enger»'),
         ('https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/dizelnye',
          'навигационный: «в каталоге передвижных дизельных компрессоров»')],
  angle='Дизельный компрессор для стройплощадки и дорожных работ: подбор по суммарному расходу '
        'пневмоинструмента (отбойники, буровые), почему у передвижных станций давление и расход '
        'связаны жёстко (выше давление - меньше выработка), шасси и работа зимой, типовая ошибка - '
        'брать станцию впритык по расходу.',
  case='обезличенно: буровой отряд геологоразведки взял передвижную дизельную станцию с запасом '
       'по расходу к паспорту бурового станка - и не встал, когда добавили второй инструмент.',
  skeleton='сцена-репортаж (утро на площадке, отбойники захлебнулись) -> расчёт от инструмента -> '
           'давление против расхода -> шасси/зима -> возврат к сцене',
  donor_note='kineshemec.ru - городской сайт промышленного райцентра Ивановской области. Читатели: '
             'малый бизнес, прорабы, дорожники, ИП. Регион упоминай сдержанно (райцентр, область), '
             'без выдуманных местных фактов.'),

 dict(slug='azot-zernohranilishche', donor='kz24.news',   # №5 + №9 (enger: категория + подкатегория)
  links=[('https://enger-air.ru/catalog/azotnye-ustanovki',
          'разбавленный: «как устроены азотные установки»'),
         ('https://enger-air.ru/catalog/azotnye-ustanovki/generatory_azota',
          'брендовый: «генераторы азота Enger»')],
  angle='Азотная среда при хранении зерна и семян (регулируемая атмосфера): кислород - главный '
        'союзник порчи (окисление жиров, дыхание массы, вредители), вытеснение его азотом работает '
        'без химии; азот получают на месте из воздуха (адсорбционные и мембранные установки - '
        'физическое разделение, никакой химии); подбор по расходу и требуемой чистоте; ошибка - '
        'возить баллоны годами вместо генерации на месте. Чистоту в конкретных процентах НЕ '
        'обещать (зависит от задачи), «пять девяток» не упоминать.',
  case='обезличенно: хозяйство зернового региона перевело газацию хранилища с привозных баллонов '
       'на генерацию азота на месте - вопрос логистики баллонов закрылся вместе с сезонными пиками.',
  skeleton='завязка-сезон (уборка закончилась - началась вторая битва, за сохранность) -> что кислород '
           'делает с зерном -> как работает азотная среда -> откуда берут азот -> подбор -> ошибки',
  donor_note='kz24.news - новостной сайт аграрной тематики, аудитория зернового пояса (агрономы, '
             'руководители хозяйств, элеваторы). Страну и регионы не конкретизируй («зерновые '
             'регионы», «юг»), местных фактов не выдумывай.'),

 dict(slug='kislorod-rybovodstvo', donor='gazetapetrovka.ru',   # №2 + №14
  links=[('https://enger-air.ru/catalog/kislorodnye-ustanovki',
          'навигационный: «станции генерации кислорода»'),
         ('https://enger-air.ru/catalog/kislorodnye-ustanovki/generator-kisloroda',
          'разбавленный: «подбирают генератор кислорода под биомассу»')],
  angle='Кислород в рыбоводстве (УЗВ и пруды): замор - главный риск отрасли, кислородное узкое '
        'место растёт вместе с плотностью посадки; три пути кислорода - привозные баллоны, жидкий '
        'в сосудах, генерация на месте (адсорбционное разделение воздуха - физика, до 93-95 '
        'процентов чистоты, для рыбы достаточно); подбор от биомассы и кормления; резервирование '
        'обязательно - рыба не ждёт ремонтов.',
  case='обезличенно: рыбоводное хозяйство с УЗВ ушло от баллонной логистики на генератор кислорода '
       'на месте; баллоны остались только как аварийный резерв.',
  skeleton='завязка-авария (ночной звонок: рыба у поверхности) -> почему кислород лимитирует -> '
           'три источника и их экономика -> подбор от биомассы -> резервирование',
  donor_note='gazetapetrovka.ru - районная газета сельской местности. Читатели: фермеры, хозяйства, '
             'сельский малый бизнес. Тон - разговор с практиком, без городского снобизма, без '
             'выдуманных местных фактов.'),

 dict(slug='kompressor-mehdvor', donor='gazetapervomaisk.ru',   # №1, 1 ссылка
  links=[('https://enger-air.ru/catalog/vintovye_kompressory',
          'разбавленный: «винтовой компрессор под длинную смену»')],
  angle='Сжатый воздух в мехдворе хозяйства: шиномонтаж, продувка техники, покраска, пескоструй '
        'перед сваркой; честное сравнение - когда хватает поршневого (короткие включения), а когда '
        'оправдан винтовой (длинная смена, покраска, несколько постов); подбор от инструмента, а '
        'не от киловатт; ресивер и подготовка воздуха для покраски.',
  case='обезличенно: мастерская хозяйства на несколько постов заменила пару загнанных поршневых '
       'на один винтовой с ресивером - покраска перестала плеваться конденсатом.',
  skeleton='завязка-вопрос читателя (письмо: какой компрессор в мастерскую) -> задачи мехдвора -> '
           'поршневой против винтового честно -> подбор от инструмента -> отступление про паспорта '
           'старой техники -> короткий ответ на письмо',
  donor_note='gazetapervomaisk.ru - районная газета. Читатели: фермеры, механизаторы, сельские '
             'мастерские. Формат «ответ на вопрос читателя» органичен. Без выдуманных местных фактов.'),

 dict(slug='vozduh-po-schetchiku', donor='operativa.ru',   # №8, 1 ссылка
  links=[('https://prokompressor.ru/services',
          'навигационный: «сервисные работы по пневмосистемам»')],
  angle='Сжатый воздух - единственная утилита завода, которую почти никто не меряет: киловатты и '
        'кубы воды считают, а воздух - нет; что дают замеры (расходомеры на магистралях, ночной '
        'тест падения давления, карта потребителей); типовые находки - утечки, завышенное давление '
        '«на всякий случай», рваный режим компрессора; данные окупают обследование быстрее любых '
        'закупок железа. Слово «пневмоаудит» использовать МАКСИМУМ ОДИН РАЗ, лучше «обследование '
        'пневмосети»/«замеры».',
  case='обезличенно: на производстве после недели замеров сняли бар лишнего давления с магистрали '
       'и закрыли найденные утечки - счёт за электричество это заметил раньше директора.',
  skeleton='завязка-парадокс (на проходной счётчик всего, кроме воздуха) -> воздух как четвёртая '
           'утилита -> что и чем меряют -> типовые находки -> когда данные окупаются',
  donor_note='operativa.ru - площадка про технологии, автоматизацию и «умное производство». '
             'Читатели любят данные и метрики. Тон - инженерная аналитика, без рекламности. '
             'Слова с корнем «инновац» запрещены.'),
]

PROMPT = """Ты пишешь ЭКСПЕРТНУЮ СТАТЬЮ для стороннего сайта (гост-пост). Не каталожный текст!

=== СТАЙЛГАЙД (обязателен целиком) ===
{guide}

=== ЗАДАНИЕ НА ЭТУ СТАТЬЮ ===
Тема/угол: {angle}
Скелет: {skeleton}
Кейс для вплетения (перескажи живо, без названий компаний и брендов техники): {case}

Ссылки (ровно {nlinks}, все в СЕРЕДИНЕ статьи, ни одной в первом/последнем абзаце,
в РАЗНЫХ разделах, каждая - как отсылка к внешнему источнику/каталогу):
{links_block}

=== ПЛОЩАДКА РАЗМЕЩЕНИЯ ===
{donor_note}

=== НАТИВНАЯ МОДЕЛЬ (обязательна) ===
Статья - редакционный материал площадки, НЕ от поставщика: без байлайна и подписи,
без названий компаний-продавцов в тексте (имена брендов допустимы ТОЛЬКО внутри
текста-якоря ссылки, если якорь брендовый). Максимум ОДИН нумерованный блок на
статью. «Ударный» однофразовый абзац - не больше одного. Финал без моральной
сентенции: вернись деталью к завязке или оборви на практическом факте. Одно
короткое содержательное отступление от темы. Объём тела 6000-9000 знаков.

=== ФОРМАТ ОТВЕТА (строго, БЕЗ JSON) ===
Первая строка: TITLE: <заголовок до 70 знаков>
Со второй строки: чистый HTML тела - только <p>, <h2>, <a>, <strong>. Без <h1>,
без <ul>/<li>, без длинных тире, без ```-ограждений, без пояснений до и после."""


def build_prompt(job):
    links_block = '\n'.join(f'{i+1}. {u}\n   якорь: {a}' for i, (u, a) in enumerate(job['links']))
    return PROMPT.format(guide=GUIDE, angle=job['angle'], skeleton=job['skeleton'],
                         case=job['case'], donor_note=job['donor_note'],
                         nlinks=len(job['links']), links_block=links_block)


def qa_multi(html, links):
    """qa_article из gp_gen, обобщённый на 1-2 разрешённых ссылки."""
    text = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', html)).strip()
    low = text.lower()
    issues = []
    if not (5200 <= len(text) <= 9800):
        issues.append(f'объём {len(text)} знаков (норма 6000-9000)')
    if '—' in html:
        issues.append('длинное тире запрещено')
    issues += [f'стоп-слово: {b}' for b in qa_text.BANNED if b in low][:5]
    issues += qa_text.refinement_check(low)
    issues += qa_text.naturalness(html, text, low)
    hrefs = re.findall(r'href="([^"]+)"', html)
    allowed = [u.rstrip('/') for u, _ in links]
    if not (1 <= len(hrefs) <= len(links)):
        issues.append(f'ссылок {len(hrefs)} (нужно {len(links)})')
    for h in hrefs:
        if h.rstrip('/') not in allowed:
            issues.append(f'ссылка не из белого списка: {h}')
    if len(hrefs) != len(set(h.rstrip('/') for h in hrefs)):
        issues.append('дубль ссылки на один URL')
    if len(links) > 1 and len(hrefs) < len(links):
        issues.append(f'ссылок {len(hrefs)}, а задано {len(links)} - добавь недостающую в другой раздел')
    paras = re.findall(r'<p[^>]*>(.*?)</p>', html, re.S)
    if paras and hrefs:
        for h in hrefs:
            if h in paras[0] or h in paras[-1]:
                issues.append('ссылка в первом/последнем абзаце - перенести в середину')
    if re.search(r'<(?!/?(p|h2|a|strong)\b)[a-z]', html):
        issues.append('посторонние HTML-теги (разрешены p, h2, a, strong)')
    return issues


def parse_plain(raw):
    raw = re.sub(r'^```(?:html)?\s*|\s*```$', '', raw.strip())
    m = re.match(r'\s*TITLE:\s*(.+)', raw)
    if not m:
        raise ValueError('нет строки TITLE: в начале ответа')
    title = m.group(1).strip()
    html = raw[m.end():].strip()
    if '<p' not in html:
        raise ValueError('после TITLE нет HTML-тела')
    return title, html.replace('—', '-')


def _openai_stream(messages, model, max_tokens):
    """Сырой стрим /v1/chat/completions (Gemini/GPT). Возвращает (text, out_tokens)."""
    import httpx
    e = gp.env()
    hdrs = {'authorization': f"Bearer {e['PROVIDER_API_KEY']}",
            'content-type': 'application/json', 'user-agent': 'curl/8.5.0'}
    body = {'model': model, 'max_tokens': max_tokens, 'stream': True,
            'stream_options': {'include_usage': True}, 'messages': messages}
    text, out_tok = [], 0
    with httpx.stream('POST', e['PROVIDER_BASE_URL'].rstrip('/') + '/v1/chat/completions',
                      headers=hdrs, json=body, timeout=420.0) as r:
        if r.status_code != 200:
            r.read()
            raise RuntimeError(f'HTTP {r.status_code}: {r.text[:150]}')
        for line in r.iter_lines():
            if not line.startswith('data:'):
                continue
            d = line[5:].strip()
            if not d or d == '[DONE]':
                continue
            try:
                ev = json.loads(d)
            except Exception:
                continue
            ch = ev.get('choices') or []
            if ch:
                c = ch[0].get('delta', {}).get('content')
                if c:
                    text.append(c)
            u = ev.get('usage')
            if u:
                out_tok = u.get('completion_tokens', 0)
    return ''.join(text), out_tok


def call_wave(messages, models):
    """Цепочка моделей по роутам: 'openai:<id>' -> chat/completions, иначе - anthropic
    _raw_stream (thinking=False, БЕЗ effort - рецепт 03.08). 2 попытки на модель.
    Возвращает (raw_text, model, out_tokens)."""
    last = None
    for model in models:
        for a in range(2):
            if a:
                time.sleep(10)
            try:
                if model.startswith('openai:'):
                    text, out_tok = _openai_stream(messages, model[7:], MAX_TOKENS)
                else:
                    msg = gp._raw_stream(messages, model, MAX_TOKENS, thinking=False, effort=None)
                    text = ''.join(b.text for b in msg.content if b.type == 'text')
                    out_tok = msg.usage.output_tokens
                if text.strip():
                    return text, model, out_tok
                last = f'{model}: пустой text'
            except Exception as e:
                last = f'{model}: {repr(e)[:100]}'
            print(f'  ретрай: {last}', file=sys.stderr, flush=True)
    raise RuntimeError(f'все модели исчерпаны: {last}')


def gen_job(job, model_override=None, tag=None):
    """model_override: одна модель на черновик И доводки (чистое сравнение моделей);
    tag: суффикс файлов gp-<slug>.<tag>.html, чтобы не перетирать основную волну."""
    messages = [{'role': 'user', 'content': build_prompt(job)}]
    t0 = time.time(); usage_out = 0; used_model = None
    title, html, issues = None, None, ['не сгенерировано']
    for rnd in range(MAX_ROUNDS):
        chain = [model_override] if model_override else (DRAFT_MODELS if rnd == 0 else FIX_MODELS)
        raw, used_model, out_tok = call_wave(messages, chain)
        usage_out += out_tok
        try:
            title, html = parse_plain(raw)
        except ValueError as e:
            messages = messages + [{'role': 'assistant', 'content': raw},
                {'role': 'user', 'content': f'Формат нарушен ({e}). Повтори ответ СТРОГО по формату: '
                 'первая строка TITLE: <заголовок>, дальше чистый HTML тела.'}]
            continue
        issues = qa_multi(html, job['links'])
        if not issues:
            break
        print(f"[{job['slug']}] раунд {rnd+1}: {len(issues)} претензий: {'; '.join(issues)[:160]}",
              file=sys.stderr, flush=True)
        messages = messages + [{'role': 'assistant', 'content': raw},
            {'role': 'user', 'content': 'Проверка нашла нарушения:\n- ' + '\n- '.join(issues) +
             '\nИсправь ТОЛЬКО это, остальное не трогай. Верни ПОЛНЫЙ ответ в том же формате '
             '(TITLE: + HTML), не сокращая статью.'}]
    if html is None:
        raise RuntimeError('не получен валидный формат за все раунды')
    sfx = f".{tag}" if tag else ''
    open(os.path.join(DIR, f"gp-{job['slug']}{sfx}.html"), 'w', encoding='utf-8').write(
        f'<h1>{title}</h1>\n' + html)
    meta = dict(slug=job['slug'], title=title, donor=job['donor'],
                links=[u for u, _ in job['links']],
                anchors=[a for _, a in job['links']], model=used_model, native=True,
                clean=not issues, issues=issues,
                chars=len(re.sub(r'<[^>]+>', '', html)), seconds=round(time.time() - t0),
                output_tokens=usage_out)
    json.dump(meta, open(os.path.join(DIR, f"gp-{job['slug']}{sfx}.meta.json"), 'w'),
              ensure_ascii=False, indent=1)
    return meta


def main():
    args = sys.argv[1:]
    model_override = tag = None
    if '--model' in args:
        model_override = args[args.index('--model') + 1]
    if '--tag' in args:
        tag = args[args.index('--tag') + 1]
    want = [a for a in args if not a.startswith('--')
            and a not in (model_override or '', tag or '')]
    jobs = [j for j in JOBS if not want or j['slug'] in want]
    res = []
    for i, job in enumerate(jobs):
        print(f"=== [{i+1}/{len(jobs)}] {job['slug']} -> {job['donor']} ===", flush=True)
        try:
            m = gen_job(job, model_override=model_override, tag=tag)
        except Exception as e:
            m = dict(slug=job['slug'], donor=job['donor'], clean=False, issues=[repr(e)[:150]])
            if i == 0 and not want:
                res.append(m)
                print('ГЕЙТ ВОЛНЫ: первая тема не отдалась - прерываю, чтобы не жечь баланс',
                      flush=True)
                break
        res.append(m)
        print(f"[{m['slug']}] clean={m.get('clean')} chars={m.get('chars')} model={m.get('model')} "
              f"issues={m.get('issues') or '-'}", flush=True)
    rep = ['# Волна гост-постов (топ-5 доноров, нативная модель)\n']
    for m in res:
        rep.append(f"- `{m['slug']}` -> {m.get('donor')} | {m.get('chars','?')} зн | "
                   f"{m.get('model','?')} | {'ЧИСТО' if m.get('clean') else 'issues: ' + '; '.join(m.get('issues', []))[:200]}")
    rname = f"wave1-report{'.' + tag if tag else ''}.md"
    open(os.path.join(DIR, rname), 'w', encoding='utf-8').write('\n'.join(rep))
    print('=>', rname)


if __name__ == '__main__':
    main()

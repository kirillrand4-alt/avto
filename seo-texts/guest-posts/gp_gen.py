# -*- coding: utf-8 -*-
"""Генератор гост-постов через провайдерский API (effort=xhigh) с мех-QA и 1 доводкой.
Темы пилота захардкожены в THEMES (с акцептором, типом якоря, фактурой и кейсом).
Выход: guest-posts/gp-<slug>.html + gp-<slug>.meta.json + сводка pilot-report.md"""
import json, os, re, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gen_provider as gp
import qa_text

DIR = os.path.dirname(os.path.abspath(__file__))
GUIDE = open(os.path.join(DIR, 'STYLE-GUIDE-GUEST.md'), encoding='utf-8').read()

THEMES = [
    dict(slug='podbor-vintovogo',
         angle='Подбор винтового компрессора по производительности: почему считают от инструмента, а не от кВт, '
               'типовая ошибка «взять с запасом по мощности», расчёт от фактического расхода + 15-20% на утечки и пики.',
         acceptor='https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/',
         anchor='разбавленный, например «подобрать винтовой компрессор по производительности»',
         case='ООО "Гранмото" (Москва, автосервис): винтовой ABAC SPINN 2.2-10-200 - хватило 2.2 кВт с ресивером 200 л на 4 поста.',
         skeleton='завязка-история (звонок клиента с неправильным запросом) -> разбор методики -> ошибки -> чек-лист'),
    dict(slug='osushitel-tochka-rosy',
         angle='Точка росы сжатого воздуха: почему рефрижераторный осушитель (+3 C PDP) не спасает покраску зимой и '
               'пневмотранспорт, когда обязателен адсорбционный (-40 C и ниже), полная цепочка подготовки воздуха '
               '(компрессор -> концевой охладитель -> циклон -> ресивер -> префильтр -> осушитель -> магистральный фильтр).',
         acceptor='https://prokompressor.ru/catalog/osushiteli/',
         anchor='брендовый, например «в каталоге Руспром»',
         case='ООО "Сфера Климата" (Пермь): Comaro LB 11-10/500 E со встроенным рефрижераторным осушителем закрыл задачу цеха, где раньше вода летела из краскопульта.',
         skeleton='завязка-симптом (брак покраски зимой) -> физика конденсата -> два типа осушителей и их пределы -> цепочка -> вывод'),
    dict(slug='utechki-szhatyj-vozduh',
         angle='Экономика сжатого воздуха: утечки съедают 20-30% выработки, свист 1-мм отверстия при 8 бар стоит '
               'десятки тысяч рублей в год на электричестве, простые способы аудита (ночной тест по манометру, обход с мыльным раствором), '
               'когда нужен полноценный пневмоаудит с замерами.',
         acceptor='https://prokompressor.ru/services/uslugi/pneumoaudit_/',
         anchor='URL-нейтральный, например «пневмоаудит» как слово-ссылка в предложении о замерах',
         case='практика: на пневмоаудитах у клиентов регулярно находят 3-5 утечек на цех, окупаемость устранения - недели.',
         skeleton='завязка-цифра (сколько стоит свист) -> откуда потери -> самодиагностика -> когда звать замерщиков -> чек-лист'),
    dict(slug='enger-brend-obzor',
         angle='Enger: китайский производитель винтовых компрессоров и осушителей, который берут вместо европейцев - '
               'винтовые блоки BAOSI и HANBELL, гарантия до 5 лет, локальный склад запчастей в РФ. Честный разбор: '
               'что реально хорошо, где ограничения, кому подходит. БЕЗ придуманных фактов о заводе.',
         acceptor='https://enger-air.ru/',
         anchor='брендовый/URL, например «на сайте Enger» или «enger-air.ru»',
         case='дизельный Enger DC-42/40 и винтовые HC-серии работают на российских производствах и СТО (пример: Enger HC-11BT 10 для ООО "Сибдортранс", Барнаул).',
         skeleton='завязка-вопрос (почему инженеры перестали бояться китайских винтовиков) -> кто такой Enger -> техника (блоки, гарантия) -> ограничения честно -> кому подходит'),
    dict(slug='dizel-na-strojke',
         angle='Дизельный компрессор для стройплощадки: подбор по расходу пневмоинструмента (отбойники, буровые), '
               'почему давление и производительность связаны обратно, передвижные станции на шасси, '
               'типовая ошибка - брать станцию впритык по расходу.',
         acceptor='https://dizel-compressor.ru/',
         anchor='разбавленный, например «подобрать дизельный компрессор под инструмент»',
         case='ООО "Киржач-Геология": дизельный Atlas Copco XAS 48 Kd под геологоразведку; ООО "СК-Инвест" (Барнаул): передвижной Cross Air Borey 65-10F.',
         skeleton='завязка-сцена (стройка, отбойники захлебнулись) -> расчёт от инструмента -> давление vs расход -> шасси/зима -> чек-лист'),
]

PROMPT = """Ты пишешь ЭКСПЕРТНУЮ СТАТЬЮ для стороннего отраслевого сайта (гост-пост). Не каталожный текст!

=== СТАЙЛГАЙД (обязателен целиком) ===
{guide}

=== ЗАДАНИЕ НА ЭТУ СТАТЬЮ ===
Тема/угол: {angle}
Скелет: {skeleton}
Кейс для вплетения (перескажи живо, не списком): {case}
Ссылка-акцептор: {acceptor}
Тип якоря: {anchor}
Ссылок на акцептор: РОВНО ОДНА, в середине статьи, контекстно.

Ответь ОДНИМ JSON-объектом без пояснений:
{{"title": "...", "html": "<p>...</p><h2>...</h2>..."}}
HTML простой: только <p>, <h2>, <a>, <strong>. Без <ul>/<li>, без длинных тире, БЕЗ байлайна в конце (добавим сами)."""

BYLINE = ('<p><em>Игорь Волков, технический директор ООО «Руспром», '
          'более 5580 проектов подбора компрессорного оборудования.</em></p>')


def qa_article(html, acceptor):
    text = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', html)).strip()
    low = text.lower()
    issues = []
    if not (5200 <= len(text) <= 9800):
        issues.append(f'объём {len(text)} знаков (норма 6000-9000)')
    if '—' in html:
        issues.append('длинное тире запрещено')
    issues += [f'стоп-слово: {b}' for b in qa_text.BANNED if b in low][:5]
    issues += [f'стоп-слово: {b}' for b in qa_text.banned_rx_hits(low)][:3]
    issues += qa_text.refinement_check(low)
    issues += qa_text.naturalness(html, text, low)
    hrefs = re.findall(r'href="([^"]+)"', html)
    if len(hrefs) != 1:
        issues.append(f'ссылок {len(hrefs)} (должна быть ровно 1)')
    elif not hrefs[0].rstrip('/').startswith(acceptor.rstrip('/')):
        issues.append(f'ссылка не на акцептор: {hrefs[0]}')
    if '<ul' in html or '<li' in html:
        issues.append('списки запрещены')
    paras = re.findall(r'<p[^>]*>(.*?)</p>', html, re.S)
    if paras and hrefs and (hrefs[0] in paras[0] or hrefs[0] in paras[-1]):
        issues.append('ссылка в первом/последнем абзаце - перенести в середину')
    return issues


def gen_one(theme, client):
    prompt = PROMPT.format(guide=GUIDE, **theme)
    messages = [{'role': 'user', 'content': prompt}]
    t0 = time.time(); usage_out = 0
    data = None; issues = ['первичная генерация']
    for attempt in range(3):
        msg = gp.call(client, messages, model='claude-fable-5', effort='xhigh')
        usage_out += msg.usage.output_tokens
        data = gp.parse_json(msg)
        issues = qa_article(data.get('html', ''), theme['acceptor'])
        if not issues:
            break
        raw = ''.join(b.text for b in msg.content if b.type == 'text')
        messages = messages + [
            {'role': 'assistant', 'content': raw},
            {'role': 'user', 'content': 'Проверка нашла нарушения:\n- ' + '\n- '.join(issues) +
             '\nИсправь ТОЛЬКО это, остальное не трогай. Верни полный JSON в том же формате.'}]
    html = data['html'].rstrip() + '\n' + BYLINE
    open(os.path.join(DIR, f"gp-{theme['slug']}.html"), 'w', encoding='utf-8').write(
        f"<h1>{data['title']}</h1>\n" + html)
    meta = dict(slug=theme['slug'], title=data['title'], acceptor=theme['acceptor'],
                anchor_type=theme['anchor'], clean=not issues, issues=issues,
                chars=len(re.sub(r'<[^>]+>', '', html)), seconds=round(time.time() - t0),
                output_tokens=usage_out)
    json.dump(meta, open(os.path.join(DIR, f"gp-{theme['slug']}.meta.json"), 'w'),
              ensure_ascii=False, indent=1)
    return meta


def main():
    client = gp.make_client()
    res = []
    with ThreadPoolExecutor(max_workers=3) as ex:
        futs = {ex.submit(gen_one, t, client): t['slug'] for t in THEMES}
        for f in as_completed(futs):
            try:
                m = f.result()
            except Exception as e:
                m = dict(slug=futs[f], clean=False, issues=[repr(e)[:120]])
            res.append(m)
            print(f"[{m['slug']}] clean={m.get('clean')} chars={m.get('chars')} "
                  f"issues={m.get('issues') or '-'}", flush=True)
    rep = ['# Пилот гост-постов\n']
    for m in sorted(res, key=lambda x: x['slug']):
        rep.append(f"- `{m['slug']}` -> {m.get('acceptor','?')} | якорь: {m.get('anchor_type','?')[:40]} | "
                   f"{m.get('chars','?')} зн | {'ЧИСТО' if m.get('clean') else 'issues: ' + '; '.join(m.get('issues', []))[:150]}")
    open(os.path.join(DIR, 'pilot-report.md'), 'w', encoding='utf-8').write('\n'.join(rep))
    print('=> pilot-report.md')


if __name__ == '__main__':
    main()

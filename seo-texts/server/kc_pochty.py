# -*- coding: utf-8 -*-
"""Почты со страниц сайта (план Meyer п. 3.2, владелец 08.10: «собираем не только номера, но и почты»).

  * `mailto:` из HTML и адреса из видимого текста;
  * снятие защиты от ботов: [at] / (at) / (собака) / « at » + « dot » / (точка);
  * адреса из скриптов и стилей не берутся (текст уже без них), заглушки вёрстки и картинки — мимо.
`почты(html, текст)` -> [{'почта', 'поз' (позиция в тексте или -1), 'контекст'}].
`вид(почта, домен_сайта)` -> своя | публичная | чужой домен | ловушка (для «Снято»).
"""
import html as H
import re

ПОЧТА = re.compile(r'(?<![\w.+-])([a-z0-9][a-z0-9._%+-]{0,63}@[a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,24})(?![\w-])', re.I)
ЗАЩИТА = [
    (re.compile(r'\s*[\[\(\{]\s*(?:at|собака|эт)\s*[\]\)\}]\s*', re.I), '@'),
    (re.compile(r'\s*[\[\(\{]\s*(?:dot|точка)\s*[\]\)\}]\s*', re.I), '.'),
    (re.compile(r'(?<=[a-z0-9])\s+(?:at|собака)\s+(?=[a-z0-9-]+\s*(?:\.|dot|точка))', re.I), '@'),
    (re.compile(r'(?<=[a-z0-9])\s+(?:dot|точка)\s+(?=[a-z]{2,6}\b)', re.I), '.'),
]
ЛОВУШКИ = re.compile(r'^(noreply|no-reply|donotreply|example|name|user|test|email|mail|yourname|ваш)@|@(example|domain|'
                     r'site|mysite|email)\.|\.(png|jpe?g|gif|webp|svg|css|js)$|@sentry|@2x\.|wixpress|@u00', re.I)
ПУБЛИЧНЫЕ = {'yandex.ru', 'ya.ru', 'yandex.by', 'yandex.com', 'mail.ru', 'bk.ru', 'list.ru', 'inbox.ru', 'internet.ru',
             'gmail.com', 'rambler.ru', 'lenta.ru', 'autorambler.ru', 'ro.ru', 'hotmail.com', 'outlook.com',
             'icloud.com', 'yahoo.com', 'tut.by', 'mail.by', 'list.by'}
СТУДИИ = re.compile(r'^(support|admin|webmaster|hosting|dev|design|seo|studio)@', re.I)


def _раскрыть(т):
    for rx, на in ЗАЩИТА:
        т = rx.sub(на, т)
    return т


def почты(html, текст):
    out, видел = [], set()
    раскр = _раскрыть(текст)
    for м in ПОЧТА.finditer(раскр):
        п = м.group(1).lower().rstrip('.')
        if п in видел or ЛОВУШКИ.search(п):
            continue
        видел.add(п)
        # позиция в исходном тексте (для подписи перед адресом); при раскрытии защиты — приблизительно
        поз = текст.lower().find(п.split('@')[0])
        поз = поз if поз >= 0 else м.start()
        out.append({'почта': п, 'поз': поз, 'контекст': re.sub(r'\s+', ' ', текст[max(0, поз - 200):поз + 80])})
    for м in re.finditer(r'(?i)href\s*=\s*["\']mailto:([^"\'?]+)', html or ''):
        п = H.unescape(м.group(1)).strip().lower()
        if not ПОЧТА.fullmatch(п) or п in видел or ЛОВУШКИ.search(п):
            continue
        видел.add(п)
        кусок = re.sub(r'<[^>]+>', ' ', html[max(0, м.start() - 1200):м.end() + 300])
        out.append({'почта': п, 'поз': -1, 'контекст': re.sub(r'\s+', ' ', H.unescape(кусок))[-300:]})
    return out


def домен(u):
    u = re.sub(r'^https?://', '', (u or '').lower()).split('/')[0]
    return u[4:] if u.startswith('www.') else u


def вид(почта, домен_сайта):
    д = почта.split('@')[-1].lower()
    дс = домен(домен_сайта)
    if ЛОВУШКИ.search(почта):
        return 'ловушка'
    if дс and (д == дс or д.endswith('.' + дс) or дс.endswith('.' + д) or д.split('.')[0] == дс.split('.')[0]):
        return 'своя'
    if д in ПУБЛИЧНЫЕ:
        return 'публичная'
    if СТУДИИ.search(почта):
        return 'ловушка'
    return 'чужой домен'


# 09.10 (владелец: «не берёт ли наш почты из невидимой части страниц — спам-ловушки»): где на странице стоит почта.
# Ловушки для сборщиков прячут адрес от людей: в комментарии HTML, в элементе со style display:none/visibility:hidden/
# font-size:0/opacity:0, уводом за экран (left/text-indent -9999), атрибутом hidden, классом honeypot/sr-only/hidden.
# Класс «hidden»/«d-none» вместе с адаптивным показом (d-md-block, md:block) — не прячет (меню для другой ширины).
_СКРЫТ_СТИЛЬ = re.compile(r'display\s*:\s*none|visibility\s*:\s*hidden|font-size\s*:\s*0(?![.\d])|opacity\s*:\s*0(?![.\d])|'
                         r'(?:left|top|text-indent|margin-left)\s*:\s*-\d{3,}|clip\s*:\s*rect\(\s*0', re.I)
_СКРЫТ_КЛАСС = re.compile(r'(?:^|\s)(hidden|d-none|hide|invisible|honeypot|honey-pot|hp-field|trap|visually-hidden|'
                         r'sr-only|screen-reader-text|visuallyhidden)(?:\s|$)', re.I)
_ПОКАЗ = re.compile(r'(?:^|\s)(?:d-(?:sm|md|lg|xl|xxl)-(?:block|flex|inline\S*|grid|table\S*)|(?:sm|md|lg|xl|2xl):'
                    r'(?:block|flex|inline\S*|grid|table\S*)|visible-\S+)', re.I)
_ПУСТЫЕ = {'br', 'img', 'input', 'meta', 'link', 'hr', 'area', 'base', 'col', 'embed', 'source', 'track', 'wbr', 'param'}
_АДРЕС = re.compile(r'[\w.+-]+@[\w-]+(?:\.[\w-]+)*\.[a-zа-я]{2,}', re.I)


def _причина(тег, attrs):
    a = {k.lower(): (v or '') for k, v in attrs}
    if тег == 'input' and a.get('type', '').lower() == 'hidden':
        return 'поле формы hidden'
    if 'hidden' in a:
        return 'атрибут hidden'
    if _СКРЫТ_СТИЛЬ.search(a.get('style', '')):
        return 'стиль: ' + _СКРЫТ_СТИЛЬ.search(a['style']).group(0)[:30]
    кл = a.get('class', '')
    м = _СКРЫТ_КЛАСС.search(кл)
    if м and not _ПОКАЗ.search(кл):
        return 'класс: ' + м.group(1)
    return ''


def видимость(html):
    """{почта: 'видна' | 'комментарий' | 'скрипт' | <причина скрытия>} — по всем вхождениям адреса на странице
    (текст и атрибуты, mailto). «видна» — хотя бы одно вхождение в видимом месте."""
    from html.parser import HTMLParser
    out = {}

    def отметить(адр, где):
        адр = H.unescape(адр).lower().strip().rstrip('.')
        if out.get(адр) != 'видна':
            out[адр] = где if где == 'видна' or адр not in out else out[адр]

    class П(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.стек = []

        def где(self):
            for т, пр in reversed(self.стек):
                if т in ('script', 'style', 'template'):
                    return 'скрипт'
                if пр:
                    return пр
            return 'видна'

        def handle_starttag(self, тег, attrs):
            пр = _причина(тег, attrs)
            for k, v in attrs:
                if v and '@' in v:
                    for м in _АДРЕС.finditer(v.replace('mailto:', ' ')):
                        отметить(м.group(0), пр or self.где() if k.lower() in ('href', 'content', 'value', 'title', 'data-email')
                                 else 'атрибут ' + k.lower()[:20])
            if тег not in _ПУСТЫЕ:
                self.стек.append((тег, пр))

        def handle_startendtag(self, тег, attrs):
            тег_ = тег
            self.handle_starttag(тег_, attrs)
            if тег_ not in _ПУСТЫЕ and self.стек:
                self.стек.pop()

        def handle_endtag(self, тег):
            for j in range(len(self.стек) - 1, -1, -1):
                if self.стек[j][0] == тег:
                    del self.стек[j:]
                    break

        def handle_data(self, d):
            if '@' in d:
                for м in _АДРЕС.finditer(d):
                    отметить(м.group(0), self.где())

        def handle_comment(self, d):
            if '@' in d:
                for м in _АДРЕС.finditer(d):
                    отметить(м.group(0), 'комментарий')

    try:
        п = П()
        п.feed(html or '')
        п.close()
    except Exception:  # noqa: BLE001
        pass
    return out


def ловушка(где):
    """По итогу видимость(): 'исключить' — адрес людям не виден никак (комментарий HTML, honeypot-класс, скрытое поле
    формы); 'пометить' — скрыт стилем/классом/атрибутом hidden (бывают и вкладки, всплывашки, выпадающие меню — проба
    09.10: почты снабжения snhz.ru в меню с left:-10000); '' — виден (в т.ч. через скрипт/данные компонента)."""
    if not где or где == 'видна' or где == 'скрипт' or (где.startswith('атрибут ') and где != 'атрибут hidden'):
        return ''
    if где == 'комментарий' or где == 'поле формы hidden' or re.search(r'honey|hp-field|trap', где):
        return 'исключить'
    return 'пометить'

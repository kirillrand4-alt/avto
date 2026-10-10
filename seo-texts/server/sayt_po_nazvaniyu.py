# -*- coding: utf-8 -*-
r"""Проверка сайта, найденного поиском по названию компании (10.10, полный прогон Meyer). EC.find_site_via_xmlriver
берёт карточку Яндекса или первый органический результат — на волне 1 из 721 найденного: check.tochka.com у 10
компаний, tenderguru.ru у 7, licexpert.ru у 5, соцсети, реестры, новости, «ООО Эксперт» -> клиника МРТ, «ООО Олимп» ->
фитнес; из 166 обойдённых ИНН компании был на 26. Сайт принимается, если:
  * домен не агрегатор/реестр/соцсеть/новости (СТОП) и не найден для другой компании (повтор домена);
  * на главной — ИНН компании или отличительное слово названия (ядра), либо домен похож на название (транслит).
-> (принят, причина)."""
import html as _html
import re
import types


def _ядра(имя):
    """Как kc_sayty.ядра (своя копия: kc_sayty при импорте меняет рабочую папку на серверную — Excel собирается локально)."""
    опф = re.compile(r'^(ООО|АО|ПАО|ЗАО|ОАО|НАО|АПФ|ПК|СПК|КФХ|МУП|ГУП|ФГУП)\s+', re.I)
    out = set()
    for кус in re.findall(r'[«"]+([^«»"]{3,})[»"]+', имя or ''):
        out.add(re.sub(r'\s+', ' ', кус).strip().lower())
    голое = опф.sub('', re.sub(r'[«»"]', ' ', имя or '')).strip()
    if len(голое) >= 4:
        out.add(re.sub(r'\s+', ' ', голое).lower())
    return {я for я in out if len(я) >= 4}


KS = types.SimpleNamespace(ядра=_ядра)


def _домен(u):
    u = re.sub(r'^https?://', '', (u or '').lower()).split('/')[0]
    return u[4:] if u.startswith('www.') else u


class _MN:  # meyer_nalichie — лениво (на сервере; локально нужен только домен)
    домен = staticmethod(_домен)

    @staticmethod
    def скачать(u):
        import meyer_nalichie
        return meyer_nalichie.скачать(u)


class _MP:
    @staticmethod
    def в_текст(h):
        import meyer_proverka
        return meyer_proverka.в_текст(h)


MN, MP = _MN, _MP

СТОП = re.compile(r'tochka\.com|tenderguru|licexpert|sensus\.kz|plastinfo|agroserver|dataslon|sudact|kommersant|'
                  r'innproverka|rusprofile|checko|list-org|zachestnyibiznes|audit-it|sbis\.ru|kontur|spark-|tarif|'
                  r'декларац|perekrestok|wikipedia|youtube|hh\.ru|avito|2gis|zoon|yell\.ru|orgpage|spravker|blizko|'
                  r'kartaslov|vk\.com|ok\.ru|t\.me|instagram|facebook|ria\.ru|rbc\.ru|tass\.ru|interfax|bel\.ru|'
                  r'egrul|nalog|gosuslugi|\.gov\.ru|tender|zakupki|b2b-center|fabrikant|rts-tender|sberbank|tbank|'
                  r'tinkoff|alfabank|vtb\.ru|pulscen|tiu\.ru|satom|flagma|regtorg|moscow-faq|vsetaksi|ivanovo\.ru', re.I)
ТР = dict(zip('абвгдеёзийклмнопрстуфыэ', ['a', 'b', 'v', 'g', 'd', 'e', 'e', 'z', 'i', 'y', 'k', 'l', 'm', 'n', 'o', 'p',
                                          'r', 's', 't', 'u', 'f', 'y', 'e']))
ТР.update({'ж': 'zh', 'х': 'h', 'ц': 'c', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch', 'ъ': '', 'ь': '', 'ю': 'yu', 'я': 'ya'})


def транслит(т):
    return ''.join(ТР.get(б, б) for б in (т or '').lower())


def _плоско(т):
    return re.sub(r'[^a-z0-9]', '', т.replace('kh', 'h').replace('ks', 'x').replace('ts', 'c').replace('j', 'y'))


НЕВИД = re.compile('[\u200b-\u200f\u2060\ufeff\u00ad]')


def _имя(имя):
    """10.10, ревизия: в списке названия с HTML-сущностями (ООО &quot;ДОН-АРТ&quot;) — ядра не выделялись, свои сайты
    отклонялись."""
    return НЕВИД.sub('', _html.unescape(_html.unescape(имя or '')))


def домен_похож(имя, сайт):
    имя = _имя(имя)
    д = _плоско(MN.домен(сайт).split('.')[0] if not MN.домен(сайт).startswith('xn--') else MN.домен(сайт))
    if MN.домен(сайт).endswith('.рф') or re.search(r'[а-яё]', MN.домен(сайт)):
        д = _плоско(транслит(MN.домен(сайт).split('.')[0]))
    for я in KS.ядра(имя):
        for сл in re.findall(r'[а-яёa-z0-9]{4,}', я):
            с = _плоско(транслит(сл))
            if len(с) >= 4 and (с[:6] in д or (len(д) >= 5 and д[:6] in с)):
                return True
    return False


СУД_МОДЕЛЬ = 'gpt-6-sol'
СУД = ('Компания «{имя}» (ИНН {инн}), регион {регион}, деятельность по ОКВЭД: {сегм}. Поиском по названию найден сайт {сайт}. '
       'На главной нет ни ИНН, ни юридического названия. Заголовок и начало главной: «{текст}».\n'
       'Это сайт этой компании или её бренда/продукции (а не однофамильца, каталога, СМИ, другой фирмы)? Учитывай '
       'бренд, вид деятельности и регион. Ответ — ТОЛЬКО JSON: {{"сайт_компании":"да|нет|неясно","почему":"до 15 слов"}}')


def _суд(имя, инн, сайт, регион, сегм, текст):
    """10.10, ревизия Sol: 12% отклонённых правилом — брендовые сайты компании (на главной бренд, а не юрназвание:
    «Дары Тайги» — кедровый орех, «Nordic Food»). Где механика не нашла ни ИНН, ни названия — решает модель."""
    import json
    import verify_company as VC
    try:
        out = VC._provider_call_stdlib(СУД.format(имя=имя, инн=инн, регион=регион or '?', сегм=сегм or '?', сайт=сайт,
                                                  текст=текст[:1600]), model=СУД_МОДЕЛЬ) or ''
        return (json.loads(re.search(r'\{.*\}', out, re.S).group(0)) or {})
    except Exception:  # noqa: BLE001
        return {}


def проверить(имя, инн, сайт, повтор=False, регион='', сегм=''):
    дом = MN.домен(сайт)
    if not дом:
        return False, 'пустой адрес'
    if СТОП.search(дом):
        return False, 'агрегатор/реестр/соцсеть: ' + дом
    if повтор:
        return False, 'домен найден и для другой компании: ' + дом
    ст, html, заг = MN.скачать(сайт if сайт.startswith('http') else 'https://' + сайт)
    похож = домен_похож(имя, сайт)
    if ст != 'ok':
        return (True, 'главная не открылась, домен похож на название') if похож else (False, 'главная не открылась, домен не похож на название')
    имя = _имя(имя)
    # невидимые символы внутри слов на странице («Норд\u200b\u200bик Фуд») — убрать
    т = НЕВИД.sub('', MP.в_текст(html) + ' ' + (заг or '')).lower().replace('«', '"').replace('»', '"').replace('ё', 'е')
    if инн and инн in re.sub(r'\D', ' ', т).split():
        return True, 'ИНН компании на главной'
    for я in KS.ядра(имя):
        if я.replace('ё', 'е').replace('«', '"').replace('»', '"') in т:
            return True, 'название «%s» на главной' % я
    if похож:
        return True, 'домен похож на название'
    if регион or сегм:
        о = _суд(имя, инн, сайт, регион, сегм, ((заг or '') + ' | ' + re.sub(r'\s+', ' ', т))[:1600])
        if о.get('сайт_компании') == 'да':
            return True, 'модель: сайт компании/бренда — %s' % (о.get('почему') or '')[:100]
        if о:
            return False, 'на главной ни ИНН, ни названия; модель: %s — %s' % (о.get('сайт_компании'), (о.get('почему') or '')[:100])
    return False, 'на главной ни ИНН, ни названия; домен не похож'


def инн_доказывает(инн, сайт, инн_живой):
    """ИНН компании на сайте — доказательство «свой», если это не реестр/каталог (10.10, ревизия: os.rssp.online,
    fishnet.ru — на страницах ИНН десятков компаний, сайт засчитывался «своим» и шёл мимо проверки моделью)."""
    инн_живой = set(инн_живой or [])
    return инн in инн_живой and len(инн_живой) <= 6 and not СТОП.search(MN.домен(сайт or '') or '')

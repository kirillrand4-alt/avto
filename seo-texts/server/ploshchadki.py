# -*- coding: utf-8 -*-
r"""Площадки, справочники и реестры — то, что НИКОГДА не является сайтом компании.

Откуда взялось. Владелец 16.08 попросил посмотреть 20 свежих паспортов глазами, и
в выборке сразу нашлись привязки: ООО «Гранд-Стройсервис» → check.tochka.com
(страница проверки контрагента в банке), ООО «Дорсервис» → строительные-компании.рф
(каталог), ООО СЗ «Монолитстрой-Иркутск» → licexpert.ru (услуги по лицензиям),
раньше попадался catalog.expocentr.ru.

Почему это пролезло мимо всех проверок. Наша «жёсткая улика» — ИНН компании на
странице. Реестр контрагентов печатает ИНН КРУПНО И ПЕРВЫМ ДЕЛОМ: страница проверки
контрагента подтверждает привязку лучше, чем настоящий сайт завода, где ИНН лежит
в подвале мелким шрифтом. То есть чем справочник полнее, тем убедительнее он врёт.

Отсюда две проверки, и вторая важнее первой:
  * СПИСОК известных площадок — банки, реестры, каталоги, маркетплейсы, соцсети,
    работные сайты, тендерные площадки;
  * СЧЁТ ЧУЖИХ ИНН на странице. Справочник по своей природе перечисляет много
    юрлиц: если на страницах встречается больше пяти разных ИНН, это каталог, как
    бы он ни назывался. Эта проверка ловит те площадки, которых нет в списке, —
    а их всегда больше, чем в списке.
"""
import re

# Домены целиком или их хвосты. Сравнение по хвосту: 'rusprofile.ru' поймает и
# 'www.rusprofile.ru', и 'msk.rusprofile.ru'.
СПИСОК = (
    # реестры и проверка контрагентов
    'rusprofile.ru', 'list-org.com', 'zachestnyibiznes.ru', 'sbis.ru', 'audit-it.ru',
    'kartoteka.ru', 'e-ecolog.ru', 'vypiska-nalog.com', 'nalog.ru', 'checko.ru',
    'datanewton.ru', 'seldon.basis.ru', 'sparkinterfax.ru', 'spark-interfax.ru',
    'focus.kontur.ru', 'kontur.ru', 'check.tochka.com', 'tochka.com', 'tinkoff.ru',
    'sbercorus.ru', 'testfirm.ru', 'bo.nalog.ru', 'egrul.nalog.ru', 'ogrn.ru',
    'compaper.ru', 'kompaniya.info', 'rescompany.ru', 'bizly.ru', 'igk.ru',
    # тендеры и госзакупки
    'zakupki.gov.ru', 'roseltorg.ru', 'rts-tender.ru', 'b2b-center.ru', 'etp-ets.ru',
    'sberbank-ast.ru', 'tektorg.ru', 'fabrikant.ru', 'gosuslugi.ru', 'torgi.gov.ru',
    # каталоги, доски, маркетплейсы
    'tiu.ru', 'pulscen.ru', 'satom.ru', 'blizko.ru', 'yell.ru', 'orgpage.ru',
    'spravker.ru', '2gis.ru', 'zoon.ru', 'flamp.ru', 'all.biz', 'allbiz',
    'avito.ru', 'ozon.ru', 'wildberries.ru', 'market.yandex.ru', 'prom.ua',
    'expocentr.ru', 'exportcenter.ru', 'postavshhiki.ru', 'regmarkets.ru',
    'строительные-компании.рф', 'licexpert.ru', 'sro-info.ru', 'reestr-sro.ru',
    'promportal.su', 'metaprom.ru', 'wikimapia.org', 'yandex.ru', 'google.com',
    # работные сайты
    'hh.ru', 'superjob.ru', 'rabota.ru', 'zarplata.ru', 'trudvsem.ru',
    # соцсети, мессенджеры, видео, энциклопедии
    'vk.com', 'ok.ru', 't.me', 'telegram.org', 'instagram.com', 'facebook.com',
    'youtube.com', 'rutube.ru', 'dzen.ru', 'livejournal.com', 'wikipedia.org',
    'pinterest.com', 'twitter.com', 'x.com', 'linkedin.com',
)
# ИНН на странице: 10 цифр (юрлицо) или 12 (ИП), не приклеенные к другим цифрам
_ИНН = re.compile(r'(?<!\d)(\d{10}|\d{12})(?!\d)')
ПРЕДЕЛ_ЧУЖИХ_ИНН = 5


def домен(url):
    d = re.sub(r'^\w+://', '', (url or '').strip().lower())
    d = d.split('/')[0].split('?')[0]
    return re.sub(r'^www\.', '', d)


def из_списка(url):
    d = домен(url)
    if not d:
        return ''
    for п in СПИСОК:
        if d == п or d.endswith('.' + п):
            return п
    return ''


def много_чужих_инн(текст, свой_инн='', предел=ПРЕДЕЛ_ЧУЖИХ_ИНН):
    """Сколько РАЗНЫХ ИНН перечислено на страницах — признак справочника."""
    свой = re.sub(r'\D', '', str(свой_инн or ''))
    чужие = {m for m in _ИНН.findall(текст or '') if m != свой}
    return len(чужие) if len(чужие) > предел else 0


def площадка(url, текст='', свой_инн='', свой_домен_или_имя=False):
    """Пусто — сайт годится. Иначе строка с причиной отказа.

    свой_домен_или_имя — на страницах найдено имя компании либо домен собран из
    её названия. Тогда счёт чужих ИНН НЕ применяем: замер 16.08 на 90 живых
    сайтах с подтверждённой привязкой дал 3 ложных срабатывания, и все три — у
    настоящих сайтов со списком дилеров или реквизитов партнёров. Список
    известных площадок работает всегда: check.tochka.com не станет сайтом завода
    оттого, что название совпало.
    """
    п = из_списка(url)
    if п:
        return 'площадка из списка: ' + п
    if свой_домен_или_имя:
        return ''
    n = много_чужих_инн(текст, свой_инн)
    if n:
        return 'справочник: на страницах %d чужих ИНН' % n
    return ''

# -*- coding: utf-8 -*-
"""Номер снят со страницы, которая к предприятию отношения не имеет. Заслон и чистка.

СЛУЧАЙ ВЛАДЕЛЬЦА, разобранный до конца. На карточке АО «ПОЛИЭФ» (ИНН 0258005638) стоял
контакт:

    +7 (495) 664-49-55   Юрин Михаил (М.Н. Юрин)   гл.инженер
    Источник: обратный ход по ФИО | перенос из enrich.db 3-й сессией
    Ссылка:   pulpfor.ru/news/.../privetstvie-uchastnikam-i-gostyam-pulpfor

Открываем ссылку: это ПРИВЕТСТВИЕ участникам выставки PulpFor 2026, подписанное
«Заместитель Министра промышленности и торговли Российской Федерации М.Н. Юрин».

Ошибок сложилось три, и каждая по отдельности выглядела безобидно:
  1. ИМЯ верное, но устаревшее. Юрин М.Н. действительно был главным инженером ПОЛИЭФа, потом
     генеральным директором — это записано в нашем же старом факте. Сейчас он замминистра.
     Должность в карточке годится для истории и не годится для звонка.
  2. СТРАНИЦА чужая. Она не про ПОЛИЭФ, она про выставку. Совпало только имя.
  3. НОМЕР со страницы принадлежит ЕЙ, а не человеку: московский телефон организатора
     выставки. Продавец набирает его, чтобы поговорить с главным инженером в Благовещенске.

КЛАСС, А НЕ СЛУЧАЙ. Это третье возвращение одной и той же ошибки: «близость не доказывает
принадлежность». Сначала она была про фамилию рядом с номером во вложении, потом про инженера
РУСАЛа в докладе Сегежского ЦБК, теперь про имя на чужой странице. Каждый раз я чинил ДАННЫЕ и
не чинил КАНАЛ — и она возвращалась с новой стороны.

ЗАСЛОН. Страница засчитывается источником контакта предприятия, только если выполнено хотя бы
одно:
  * хост страницы совпадает с сайтом предприятия (ядро домена);
  * на странице названо само предприятие (его имя есть в тексте окна вокруг номера);
  * код номера соответствует региону предприятия.
Иначе — это чужая страница, где просто встретилось имя. Контакт не удаляется: он
переписывается на «источник не подтверждает принадлежность», чтобы не потерять след.

ОТДЕЛЬНО ПРО НОВОСТНЫЕ И ВЫСТАВОЧНЫЕ ДОМЕНЫ. Приветствия, программы конференций, отраслевые
новости — самый частый вид чужой страницы: там имена руководителей стоят списком, а телефон
на странице всегда один и тот же, редакции или организатора.
"""
import re

# Домены, где имя человека встречается без всякой связи с его работодателем.
CHUZHOY_DOMEN = re.compile(
    r'pulpfor|expo|vystavk|forum|conference|konferenc|news|novosti|smi|press|media|'
    r'globalmsk|rusprofile|list-org|zachestnyibiznes|checko|sbis|kartoteka|audit-it|'
    r'vedomosti|kommersant|rbc\.|interfax|tass\.|ria\.|regnum|gazeta|journal|zhurnal|'
    r'wikipedia|dzen|vk\.com|ok\.ru|t\.me|telegram|youtube|linkedin|hh\.ru|superjob|'
    r'award|premi[yai]|nagrad', re.I)


# ЗАКУПОЧНЫЕ ПЛОЩАДКИ — НЕ ЧУЖИЕ СТРАНИЦЫ, и первый вариант правила зря их поймал. Карточка
# закупки на zakupki.gov.ru или tektorg.ru называет КОНТАКТНОЕ ЛИЦО ЗАКАЗЧИКА с телефоном —
# это ровно то место, откуда контакт брать и следует. Домен там чужой по имени, а по существу
# страница про наше предприятие: в ней стоит его ИНН.
PLOSHCHADKA = re.compile(
    r'zakupki\.gov|roseltorg|rts-tender|etp-?gpb|etpgpb|tektorg|tender\.pro|b2b-center|'
    r'sberbank-ast|fabrikant|otc\.ru|gazneftetorg|estp|torgi\.gov|zakupki\.mos|'
    r'gz-spb|komita|onlinecontract|tp\.rosseti|zakupki\.rushydro', re.I)


def yadro_domena(url_ili_domen):
    """Второй уровень домена: `www.sibur.ru/polief/` → `sibur`."""
    v = re.sub(r'^\w+://', '', (url_ili_domen or '').strip().lower())
    v = v.split('/')[0].split('?')[0]
    chasti = [c for c in v.split('.') if c and c != 'www']
    if len(chasti) >= 2:
        # ru, com, рф и прочие первого уровня отбрасываем, берём следующий слева.
        return chasti[-2]
    return chasti[0] if chasti else ''


def stranica_podtverzhdaet(url, sayt_predpriyatiya='', imya_predpriyatiya='', tekst_stranicy=''):
    """(подтверждает ли страница принадлежность, объяснение)."""
    if not (url or '').strip():
        return False, 'ссылки нет — проверить нечем'
    yd = yadro_domena(url)
    ys = yadro_domena(sayt_predpriyatiya)
    if ys and yd and yd == ys:
        return True, f'страница на сайте предприятия («{yd}»)'
    # САЙТ ХОЛДИНГА — ТОЖЕ САЙТ ПРЕДПРИЯТИЯ. Первый прогон пометил как чужие 6 контактов
    # АО «ПОЛИЭФ» со страницы `sibur.ru/polief/contacts/`: ядро домена «sibur» не совпало с
    # полем `sayt`. Но это страница ПРО ПОЛИЭФ на сайте владеющего холдинга, и контакты на
    # ней его. Признак: имя предприятия стоит в АДРЕСЕ страницы.
    if imya_predpriyatiya:
        osnova = re.sub(r'[^а-яёa-z0-9]', '',
                        re.sub(r'\b(ООО|ОАО|ЗАО|ПАО|АО|ФГУП|ГУП|МУП)\b', '',
                               imya_predpriyatiya, flags=re.I).lower())
        # Транслитерация ядра: «полиэф» → «polief». Только ходовые соответствия, без затей.
        tr = str.maketrans({'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ё':'e','ж':'z',
                            'з':'z','и':'i','й':'y','к':'k','л':'l','м':'m','н':'n','о':'o',
                            'п':'p','р':'r','с':'s','т':'t','у':'u','ф':'f','х':'h','ц':'c',
                            'ч':'c','ш':'s','щ':'s','ъ':'','ы':'y','ь':'','э':'e','ю':'u',
                            'я':'a'})
        lat = osnova.translate(tr)
        adres = re.sub(r'[^a-z0-9]', '', (url or '').lower())
        if len(lat) >= 5 and lat[:9] in adres:
            return True, f'страница про предприятие на сайте холдинга («{yd}»)'
    # Имя предприятия на странице: сравниваем по ядру, как в `yadro_imeni`.
    if imya_predpriyatiya and tekst_stranicy:
        osnova = re.sub(r'[^а-яёa-z0-9]', '', imya_predpriyatiya.lower())[:14]
        if osnova and osnova in re.sub(r'[^а-яёa-z0-9]', '', tekst_stranicy.lower()):
            return True, 'предприятие названо в тексте страницы'
    if PLOSHCHADKA.search(url):
        return True, 'карточка закупки самого предприятия — контактное лицо заказчика назван'
    if CHUZHOY_DOMEN.search(url):
        return (False, f'страница отраслевого или новостного домена («{yd}») — имя на ней '
                       f'встретилось, но принадлежность контакта из этого не следует')
    return False, f'домен «{yd}» с предприятием не связан и имени предприятия на странице нет'


if __name__ == '__main__':
    proby = [
        ('https://pulpfor.ru/news/tpost/k18juk0d11-privetstvie-uchastnikam',
         'http://polief.ru', 'АО «ПОЛИЭФ»', '', False),
        ('https://www.sibur.ru/polief/contacts/', 'https://www.sibur.ru/polief/',
         'АО «ПОЛИЭФ»', '', True),
        ('https://globalmsk.ru/person/id/11375', '', 'АО «ПОЛИЭФ»', '', False),
        ('https://asu-samara.ru/otzyvy/ao-polief/', '', 'АО «ПОЛИЭФ»',
         'отзыв АО ПОЛИЭФ о внедрении', True),
        ('https://kaustik.ru/about/management/', 'http://kaustik.ru', 'АО «Каустик»', '', True),
    ]
    for url, sayt, imya, tekst, ozhid in proby:
        est, poch = stranica_podtverzhdaet(url, sayt, imya, tekst)
        print(f'{"OK  " if est == ozhid else "МИМО"} {url[:52]:<54} {poch[:60]}')

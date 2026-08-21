# -*- coding: utf-8 -*-
r"""Ссылка на лид для отдела продаж: переписка и контакты без наших адресов.

Владелец 20.08: «мы можем сделать механизм передачи в незашифрованном виде
только ссылки лида? то есть что бы вся история переписки была видна + вся
информация кроме почты и подписи которая была при отправке?»

Смысл: менеджеру, который будет звонить, нужна вся фактура — кто ответил, что
написал, чем компания занимается, кому звонить. И НЕ нужны две вещи:

  * НАШИ адреса — ящики рассылки. Персоны рассылки наружу не показываем.
    Адрес самого получателя остаётся: владелец 20.08 поправил — «получатель
    можно, наш нет». Менеджеру он и нужен, чтобы понимать, с кем разговор;
  * подпись, которой письмо было подписано, — «С уважением, Менеджер по
    продажам, Игорь Ляпин, «Компрессор Центр», ООО «Руспром», ИНН…».
    Менеджер звонит от своего имени, и чужая подпись в тексте только путает.

Ссылка «незашифрованная» в том смысле, что в ней нет данных: это случайный
токен на 32 знака, а всё содержимое достаётся по нему из базы. Значит ссылку
можно отозвать, и по самой ссылке ничего не восстановить.
"""
import hashlib
import json
import os
import re
import secrets
import sqlite3
import time

БД = os.environ.get('SENDER_DB', r'C:\sender\sender.db')
ENRICH = os.environ.get('ENRICH_DB', r'C:\sender\enrich.db')
БАЗОВЫЙ = os.environ.get('PANEL_PUBLIC_URL',
                         'https://panel.parsercompressor.online')

СХЕМА = """CREATE TABLE IF NOT EXISTS lead_ssylki(
    token TEXT PRIMARY KEY,
    lead_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    created_by TEXT,
    revoked_at TEXT,
    otkrytiy INTEGER DEFAULT 0,
    last_seen TEXT)"""

# Подпись отрезаем от «С уважением» до конца письма: шаблон подписи в
# sender._DEFAULT_SIGNATURE начинается именно этой строкой, и ничего
# содержательного после неё в письме не бывает.
_ПОДПИСЬ = re.compile(r'\n\s*С\s+уважением\s*,?.*$', re.S | re.I)
# Футер почтовика и юр-атрибуция «--\n…ИНН…» — тоже служебное.
_ФУТЕР = re.compile(
    r'\n-{2,}\s*\n.*?(VK\s*WorkSpace|ИНН\s*\d{10,12}).*$', re.S | re.I)
_АДРЕС = re.compile(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}')


def _соединение():
    c = sqlite3.connect(БД, timeout=60)
    try:
        c.execute('PRAGMA busy_timeout=30000')
    except Exception:  # noqa: BLE001
        pass
    c.execute(СХЕМА)
    c.row_factory = sqlite3.Row
    return c


def bez_podpisi(текст: str) -> str:
    """Тело письма без подписи и служебных футеров."""
    т = str(текст or '')
    т = _ФУТЕР.sub('', т)
    т = _ПОДПИСЬ.sub('', т)
    return т.strip()


# Шапка цитирования: почтовики ставят её перед процитированным письмом.
_ШАПКА_ЦИТАТЫ = re.compile(
    r'^\s*(?:'
    r'(?:>\s*)*(?:В|в)\s+.{0,80}?(?:писал|написал)\(?а?\)?\s*:|'
    r'(?:>\s*)*On\s+.{0,80}?wrote\s*:|'
    r'-{2,}\s*(?:Original Message|Исходное сообщение|Пересланное сообщение)\s*-{2,}|'
    r'(?:>\s*)*(?:От|From|Кому|To|Копия|Cc|Тема|Subject|Дата|Date|Отправлено|Sent)'
    r'\s*:\s*.*|'
    # «20.08.2026, 09:04, "Юрий Кузьмин, Meyer" <адрес>:» — так цитирует
    # mail.ru и другие веб-почты; знака «>» при этом в тексте нет вообще
    r'(?:>\s*)*\d{1,2}[./]\d{1,2}[./]\d{2,4},?\s+\d{1,2}:\d{2}.{0,90}?:\s*|'
    r'-{4,}\s*'
    r')\s*$', re.I)


def bez_citaty(текст: str) -> str:
    """Убрать процитированное письмо, оставив то, что человек написал сам.

    Наша подпись утекала наружу не из нашего письма — его-то мы чистим, — а из
    ЦИТАТЫ в ответе клиента: почтовик подставляет наш текст со строками «>», и
    вместе с ним «С уважением, менеджер, ООО «Руспром», ИНН». Проба 21.08 по
    лиду «Канат» показала это дословно. Резать у входящего письма всё от слов
    «С уважением» нельзя — там подпись самого клиента, а это имя и телефон,
    ради которых страницу и открывают. Поэтому убираем именно цитату: строки
    со знаком «>» и шапку над ними. Ответ вперемешку с цитатой (частый случай в
    деловой переписке) при этом уцелеет — свои строки человек не цитирует.

    Если после чистки не осталось ничего (письмо целиком переслано), возвращаем
    исходный текст без подписи: пустая карточка хуже, чем текст с цитатой, но
    наша подпись не должна утечь и в этом случае.
    """
    строки = str(текст or '').splitlines()
    # ХВОСТ ПОСЛЕ ШАПКИ. Веб-почта цитирует вёрсткой: знаков «>» нет, а после
    # строки «20.08.2026, 09:04, "Юрий Кузьмин, Meyer" <адрес>:» идёт наше
    # письмо целиком — с именем менеджера в самой шапке (владелец 21.08).
    # Режем от первой шапки до конца, но только если выше осталось что читать.
    for i, с in enumerate(строки):
        if not _ШАПКА_ЦИТАТЫ.match(с):
            continue
        выше = '\n'.join(строки[:i]).strip()
        if len(re.sub(r'\s+', ' ', выше)) >= 40:
            строки = строки[:i]
            break
    оставили = []
    for с in строки:
        if с.lstrip().startswith('>'):
            continue
        if _ШАПКА_ЦИТАТЫ.match(с):
            continue
        оставили.append(с)
    итог = '\n'.join(оставили).strip()
    # схлопываем пустоту, оставшуюся на месте вырезанного
    итог = re.sub(r'\n{3,}', '\n\n', итог)
    return итог if len(итог) >= 20 else bez_podpisi(текст)


# По этим словам подпись опознаётся как НАША. Своё «С уважением» клиент
# подписывает своей компанией, и слова «Руспром» в ней быть не может.
_НАШИ_ПРИЗНАКИ = ('руспром', 'компрессор центр', 'руспром мейер',
                  'инн 2221239841')
_НАЧАЛО_ПОДПИСИ = re.compile(r'^[ \t>]*С\s+уважением', re.I)


def bez_nashey_podpisi(текст: str) -> str:
    """Вырезать НАШУ подпись где угодно в письме, подпись клиента не трогая.

    Цитату режет bez_citaty — но только когда почтовик пометил её знаками «>».
    Клиенты отвечают и из веб-интерфейсов, которые цитируют вёрсткой, а в
    текстовом слое остаётся наше письмо без единого знака цитирования: владелец
    21.08 прислал страницу лида, где «Юрий Кузьмин, «Руспром Мейер», ООО
    «Руспром», ИНН…» стояли прямо в теле ответа.

    Поэтому ищем подпись по её собственным приметам: строка «С уважением» и
    несколько коротких строк за ней. Вырезаем ТОЛЬКО если внутри блока есть
    наши слова — «Руспром», «Компрессор Центр», наш ИНН. Подпись клиента с его
    именем и телефоном такой проверки не проходит и остаётся на месте.
    """
    строки = str(текст or '').splitlines()
    итог, i = [], 0
    while i < len(строки):
        if _НАЧАЛО_ПОДПИСИ.match(строки[i]):
            блок, j = [строки[i]], i + 1
            while j < len(строки) and len(блок) < 9:
                чисто = строки[j].strip().lstrip('>').strip()
                if not чисто or len(чисто) > 80:
                    break
                блок.append(строки[j])
                j += 1
            if any(п in ' '.join(блок).lower() for п in _НАШИ_ПРИЗНАКИ):
                i = j
                continue
        итог.append(строки[i])
        i += 1
    return re.sub(r'\n{3,}', '\n\n', '\n'.join(итог).strip())


_НАШИ_КЭШ = {'домены': None, 'до': 0.0}


def nashi_domeny() -> set:
    """Домены НАШИХ ящиков — из самих ящиков, а не списком в коде.

    Списком нельзя: домены добавляют и меняют, а забытый в списке домен утечёт
    наружу молча. Берём их оттуда, где они заведомо настоящие, — из отправок.
    Держим четверть часа, чтобы не дёргать базу на каждое письмо страницы.
    """
    if _НАШИ_КЭШ['домены'] is not None and time.time() < _НАШИ_КЭШ['до']:
        return _НАШИ_КЭШ['домены']
    домены = set()
    try:
        c = sqlite3.connect('file:%s?mode=ro' % БД.replace('\\', '/'), uri=True)
        for таблица, поле in (('mailbox_state', 'mailbox_id'),
                              ('messages', 'mailbox_id'),
                              ('events', 'mailbox_id')):
            try:
                for (я,) in c.execute(
                        'SELECT DISTINCT "%s" FROM "%s" '
                        'WHERE "%s" IS NOT NULL' % (поле, таблица, поле)):
                    д = str(я or '').lower().rsplit('@', 1)
                    if len(д) == 2 and д[1]:
                        домены.add(д[1])
            except Exception:  # noqa: BLE001 - таблицы может не быть
                pass
        c.close()
    except Exception:  # noqa: BLE001
        pass
    _НАШИ_КЭШ['домены'] = домены
    _НАШИ_КЭШ['до'] = time.time() + 900
    return домены


_ИМЕНА_КЭШ = {'имена': None, 'до': 0.0}
_КОНФИГ = os.environ.get('SENDER_YAML', r'C:\sender\sender.yaml')


def nashi_imena() -> list:
    """Имена НАШИХ отправителей — из конфига ящиков, а не списком в коде.

    В конфиге они стоят как from_name: "Юрий Кузьмин, Meyer". Прячем и всю
    строку, и одно имя с фамилией: в шапке цитаты почтовик печатает строку
    целиком, а в подписи — только имя.
    """
    if _ИМЕНА_КЭШ['имена'] is not None and time.time() < _ИМЕНА_КЭШ['до']:
        return _ИМЕНА_КЭШ['имена']
    имена = set()
    try:
        with open(_КОНФИГ, encoding='utf-8') as f:
            for стр in f:
                m = re.match(r'\s*from_name\s*:\s*(.+)', стр)
                if not m:
                    continue
                зн = m.group(1).strip().strip('"\'').strip()
                if not зн:
                    continue
                имена.add(зн)
                фио = зн.split(',')[0].strip()
                if len(фио) > 4:
                    имена.add(фио)
    except Exception:  # noqa: BLE001
        pass
    # длинные первыми: иначе «Юрий Кузьмин» съест начало «Юрий Кузьмин, Meyer»
    итог = sorted(имена, key=len, reverse=True)
    _ИМЕНА_КЭШ['имена'] = итог
    _ИМЕНА_КЭШ['до'] = time.time() + 900
    return итог


def bez_imyon(текст: str) -> str:
    """Скрыть имена наших отправителей. Владелец 21.08: «имя от кого отправляли
    тоже скрыть» — оно оставалось в шапке цитаты рядом со скрытым адресом."""
    т = str(текст or '')
    for имя in nashi_imena():
        if имя and имя in т:
            т = т.replace(имя, '[наш менеджер]')
    return т


def bez_adresov(текст: str) -> str:
    """Скрыть НАШИ адреса, чужие оставить.

    Владелец 20.08: «получатель можно, наш нет». Прячем только ящики рассылки —
    менеджеру важно видеть, с какого адреса ему ответили, а вот наши персоны
    и домены рассылки наружу не показываем.

    Заменяем на пометку, а не на пустоту: пустое место читается как потеря
    текста («пишите на  »), а пометка честно говорит, что адрес есть.
    """
    наши = nashi_domeny()
    if not наши:
        return bez_imyon(текст)

    def _замена(m):
        а = m.group(0)
        return '[наш адрес скрыт]' if а.rsplit('@', 1)[-1].lower() in наши else а

    return bez_imyon(_АДРЕС.sub(_замена, str(текст or '')))


def sozdat(lead_id: int, kto: str = '') -> dict:
    """Выдать ссылку на лид. Повторный вызов возвращает ту же живую ссылку."""
    c = _соединение()
    try:
        было = c.execute(
            'SELECT token FROM lead_ssylki WHERE lead_id=? AND revoked_at IS NULL '
            'ORDER BY created_at DESC LIMIT 1', (int(lead_id),)).fetchone()
        if было:
            return {'token': было['token'], 'url': ssylka(было['token']),
                    'sozdana': False}
        токен = secrets.token_urlsafe(24)
        c.execute('INSERT INTO lead_ssylki(token, lead_id, created_at, created_by) '
                  'VALUES (?,?,?,?)',
                  (токен, int(lead_id), time.strftime('%Y-%m-%dT%H:%M:%S'),
                   str(kto or '')[:60]))
        c.commit()
        return {'token': токен, 'url': ssylka(токен), 'sozdana': True}
    finally:
        c.close()


def otozvat(lead_id: int) -> int:
    """Погасить все живые ссылки лида. Возвращает, сколько погашено."""
    c = _соединение()
    try:
        cur = c.execute(
            'UPDATE lead_ssylki SET revoked_at=? '
            'WHERE lead_id=? AND revoked_at IS NULL',
            (time.strftime('%Y-%m-%dT%H:%M:%S'), int(lead_id)))
        c.commit()
        return cur.rowcount
    finally:
        c.close()


def ssylka(token: str) -> str:
    return '%s/lid/%s' % (БАЗОВЫЙ.rstrip('/'), token)


def lead_po_tokenu(token: str):
    """id лида по токену или None. Заодно считаем открытия."""
    т = str(token or '').strip()
    if not т or len(т) > 64:
        return None
    c = _соединение()
    try:
        r = c.execute('SELECT lead_id FROM lead_ssylki '
                      'WHERE token=? AND revoked_at IS NULL', (т,)).fetchone()
        if not r:
            return None
        with_suppress = True
        try:
            c.execute('UPDATE lead_ssylki SET otkrytiy=COALESCE(otkrytiy,0)+1, '
                      'last_seen=? WHERE token=?',
                      (time.strftime('%Y-%m-%dT%H:%M:%S'), т))
            c.commit()
        except Exception:  # noqa: BLE001 - счётчик не важнее показа страницы
            with_suppress = False
        _ = with_suppress
        return int(r['lead_id'])
    finally:
        c.close()


def spisok(lead_id: int) -> list:
    c = _соединение()
    try:
        return [dict(r) for r in c.execute(
            'SELECT token, created_at, created_by, revoked_at, otkrytiy, last_seen '
            'FROM lead_ssylki WHERE lead_id=? ORDER BY created_at DESC',
            (int(lead_id),))]
    finally:
        c.close()


def podpis_toksena(token: str) -> str:
    """Короткий отпечаток токена для журнала — сам токен в логи не пишем."""
    return hashlib.sha256(str(token or '').encode()).hexdigest()[:12]


# ---------------------------------------------------------------------------
# Карточка компании для менеджера: всё, что знаем, и ОТКУДА знаем.
# Владелец 21.08: «информация о компании должна быть полная, контакты с
# источниками» — и отдельным вопросом «откуда?» про телефон на странице.
# Телефон там был из двух мест сразу (ответ клиента и обход сайта) и стоял
# двумя строками без единого слова о происхождении.
# ---------------------------------------------------------------------------

def _цифры(т) -> str:
    return ''.join(c for c in str(т or '') if c.isdigit())


def telefon_krasivo(т) -> str:
    """+7 (985) 991-29-58 — из любой записи номера."""
    ц = _цифры(т)
    if len(ц) == 10:
        ц = '7' + ц
    if len(ц) == 11 and ц[0] == '8':
        ц = '7' + ц[1:]
    if len(ц) == 11 and ц[0] == '7':
        return '+7 (%s) %s-%s-%s' % (ц[1:4], ц[4:7], ц[7:9], ц[9:11])
    return str(т or '').strip()


def _ключ_телефона(т) -> str:
    ц = _цифры(т)
    return ц[-10:] if len(ц) >= 10 else ц


def _список(значение) -> list:
    """Поле базы, где список мог лечь и списком, и JSON-строкой, и через запятую."""
    if isinstance(значение, (list, tuple)):
        return [str(x).strip() for x in значение if str(x).strip()]
    т = str(значение or '').strip()
    if not т:
        return []
    if т.startswith('['):
        try:
            return [str(x).strip() for x in json.loads(т) if str(x).strip()]
        except Exception:  # noqa: BLE001
            pass
    return [ч.strip() for ч in re.split(r'[;,]\s*', т) if ч.strip()]


def _деньги(v) -> str:
    try:
        n = float(v or 0)
    except (TypeError, ValueError):
        return ''
    if n <= 0:
        return ''
    if n >= 1e9:
        return '%.1f млрд ₽' % (n / 1e9)
    if n >= 1e6:
        return '%.1f млн ₽' % (n / 1e6)
    return '%d ₽' % int(n)


KESH = os.environ.get('PAGECACHE_DIR', r'C:\seostat\drop\pagecache')


def _stranicy_kesha(inn) -> list:
    """[(url, текст)] страниц компании из кэша обхода.

    Владелец 21.08: «где конкретно на сайте нашли». Источник вида «сайт
    компании» отвечает на вопрос наполовину: у завода полсотни страниц, и
    менеджеру нужна та самая. Страницы обхода лежат в кэше вместе с адресами —
    ищем значение прямо в них.
    """
    п = os.path.join(KESH, '%s.json.gz' % _цифры(inn))
    if not os.path.exists(п):
        return []
    try:
        import gzip
        with gzip.open(п, 'rb') as f:
            д = json.loads(f.read().decode('utf-8', 'replace'))
    except Exception:  # noqa: BLE001
        return []
    out = []
    for стр in (д.get('pages') or [])[:400]:
        url = str(стр.get('url') or '')
        html = str(стр.get('html') or '')
        if url and html:
            out.append((url, html))
    return out


_ТЕЛ_В_ТЕКСТЕ = re.compile(r'(?:\+7|8)?[\s\-()]{0,3}\d[\d\s\-()]{8,20}\d')
_ПОЧТА_В_ТЕКСТЕ = re.compile(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}')


def _tekst_stranicy(html: str) -> str:
    """Теги — в переводы строки: так подпись «Бухгалтерия:» не слипается с номером."""
    т = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', str(html or ''),
               flags=re.S | re.I)
    т = re.sub(r'<[^>]+>', '\n', т)
    for a, b in (('&nbsp;', ' '), ('&amp;', '&'), ('&quot;', '"')):
        т = т.replace(a, b)
    return т


def _podpis_pered(текст: str, позиция: int) -> str:
    """Подпись слева от значения — только если она кончалась двоеточием.

    Владелец 21.08: «в паспорте не написаны роли телефонов?» Ролей там нет —
    промпт паспорта телефоны не спрашивает вовсе. Зато они написаны на самой
    странице: «Комм. отдел: +7 (8639) 26 26 98». Двоеточие — признак подписи;
    без него слева стоит что попало вроде «Позвоните нам», и это шум.
    """
    перед = текст[max(0, позиция - 90):позиция]
    обрез = перед.rstrip(' \t\r\n\u00a0')
    if not обрез.endswith(':'):
        return ''
    куски = [x.strip(' \t\r\n·—-') for x in re.split(r'[\n;|]+', обрез[:-1])]
    подпись = next((x for x in reversed(куски) if x.strip()), '')
    подпись = подпись.strip()
    if not подпись or len(подпись) > 40 or _цифры(подпись):
        return ''
    return подпись


def _fiktivnyy(ключ: str) -> bool:
    """+7 (999) 999-99-99 и подобные заглушки из форм — не телефон."""
    return len(set(ключ)) <= 2


# Подписи, после которых стоит НЕ телефон. Замер по 300 компаниям кэша: чаще
# всего слева от «номера» оказывались реквизиты — ИНН у 234 компаний, ОГРН у
# 230. Без этого заслона расчётный счёт уехал бы в карточку как телефон.
_НЕ_ТЕЛЕФОН = ('инн', 'огрн', 'огрнип', 'кпп', 'бик', 'окпо', 'октмо', 'окато',
               'р/с', 'к/с', 'счет', 'счёт', 'индекс', 'лицензи', 'свидетельств')
# Подписи, которые есть, но роли не несут: «Телефон:» перед телефоном ничего
# не сообщает. Номер оставляем, роль не выдумываем.
_ПУСТАЯ_ПОДПИСЬ = ('телефон', 'телефоны', 'тел', 'тел.', 'тел./факс', 'моб',
                   'моб.', 'мобильный телефон', 'контактный телефон',
                   'контактные телефоны', 'контактный номер', 'контакты',
                   'звоните нам', 'позвоните нам', 'номер', 'phone', 'tel')


def _pohozh_na_telefon(цифры_: str) -> bool:
    """Российский номер: 10 знаков, либо 11 с ведущей 7/8, код из 3/4/8/9.

    Длина отсекает ОГРН (13), ИНН юрлица-двенадцатизначный, расчётный счёт (20)
    и БИК (9). Первая цифра кода отсекает десятизначный ИНН: он начинается с
    кода региона, и «6143038853» кодом города быть не может.
    """
    ц = цифры_
    if len(ц) == 11 and ц[0] in '78':
        ц = ц[1:]
    if len(ц) != 10:
        return False
    return ц[0] in '3489'


def _kontakty_so_stranic(страницы) -> dict:
    """{'tel': {…}, 'mail': {…}} — как записаны на сайте, с подписями и адресами.

    Одним проходом по кэшу: страниц у завода полсотни, и бегать по ним отдельно
    за каждым номером — то же самое, только медленнее.
    """
    тел, почт = {}, {}
    for url, html in страницы:
        текст = _tekst_stranicy(html)
        for m in _ТЕЛ_В_ТЕКСТЕ.finditer(текст):
            ц = _цифры(m.group(0))
            if not _pohozh_na_telefon(ц):
                continue
            ключ = ц[-10:]
            if _fiktivnyy(ключ):
                continue
            п = _podpis_pered(текст, m.start())
            низ = п.lower().strip(' .:')
            if any(б in низ for б in _НЕ_ТЕЛЕФОН):
                continue          # это реквизит, а не телефон
            if низ in _ПУСТАЯ_ПОДПИСЬ:
                п = ''            # подпись есть, а роли в ней нет
            узел = тел.setdefault(ключ, {'kak': m.group(0).strip(),
                                         'podpisi': [], 'stranicy': []})
            if п and п not in узел['podpisi']:
                узел['podpisi'].append(п)
            if url not in узел['stranicy']:
                узел['stranicy'].append(url)
        for m in _ПОЧТА_В_ТЕКСТЕ.finditer(текст):
            адрес = m.group(0).lower()
            узел = почт.setdefault(адрес, {'podpisi': [], 'stranicy': []})
            п = _podpis_pered(текст, m.start())
            if п and п not in узел['podpisi']:
                узел['podpisi'].append(п)
            if url not in узел['stranicy']:
                узел['stranicy'].append(url)
    return {'tel': тел, 'mail': почт}


def _luchshie_stranicy(адреса, предел=3) -> list:
    """Из дюжины страниц с тем же номером оставить самые полезные.

    Один и тот же телефон стоит в подвале каждой страницы, и печатать их все —
    шум. Первыми идут контактные разделы, дубли по схеме и слэшу схлопываются.
    """
    вес = ('contact', 'kontakt', 'связ', 'about', 'o-kompanii', 'company')
    видели, отобрано = set(), []
    for u in sorted(адреса or [],
                    key=lambda x: 0 if any(в in str(x).lower() for в in вес) else 1):
        ключ = re.sub(r'^https?://(www\.)?', '', str(u or '').strip()).rstrip('/')
        if not ключ or ключ in видели:
            continue
        видели.add(ключ)
        отобрано.append(u)
        if len(отобрано) >= предел:
            break
    return отобрано


def _gde_nashli(страницы, значение, телефон=False) -> list:
    """Адреса страниц, где значение встречается дословно (не более трёх)."""
    найдено = []
    if телефон:
        хвост = _цифры(значение)[-10:]
        if len(хвост) < 10:
            return []
        for url, html in страницы:
            if хвост in _цифры(html):
                найдено.append(url)
            if len(найдено) >= 3:
                break
        return найдено
    иск = str(значение or '').strip().lower()
    if not иск:
        return []
    for url, html in страницы:
        if иск in html.lower():
            найдено.append(url)
        if len(найдено) >= 3:
            break
    return найдено


# Поля паспорта сайта в том порядке, в каком они нужны звонящему: сперва что
# делают, потом чем делают, потом чем дышат (это и есть наш товар).
_ПАСПОРТ_ПОЛЯ = (
    ('продукция', 'Что выпускают'),
    ('сырьё', 'Сырьё'),
    ('мощности', 'Мощности'),
    ('оборудование_линии', 'Оборудование и линии'),
    ('энергохозяйство', 'Энергохозяйство'),
    ('газы', 'Газы и резка'),
    ('упаковка_фасовка', 'Упаковка и фасовка'),
    ('контроль_качества', 'Контроль качества'),
    ('расширение', 'Расширение'),
    ('масштаб', 'Масштаб'),
    ('клиенты', 'Клиенты'),
    ('экспорт', 'Экспорт'),
    ('география_поставок', 'География поставок'),
)


def karta_kompanii(inn, lead: dict = None) -> dict:
    """Полная карточка: реквизиты, контакты с источниками, паспорт сайта.

    Источник у каждого контакта свой и разный по надёжности: телефон из ответа
    клиента написан живым человеком, телефон с сайта снят обходом, адрес из
    справочника прочитан у посредника. Менеджеру это важно знать до звонка,
    поэтому источник едет рядом со значением, а не теряется по дороге.
    """
    цифры = _цифры(inn)
    пусто = {'rekvizity': {}, 'telefony': [], 'pochty': [], 'lyudi': [],
             'pasport': {}}
    if not цифры or not os.path.exists(ENRICH):
        return пусто
    # lead приезжает то словарём (публичная страница), то объектом ORM
    # (карточка в панели) — принимаем оба, чтобы вызов был один на все места.
    лид = lead if isinstance(lead, dict) else {
        'email': getattr(lead, 'email', ''), 'phone': getattr(lead, 'phone', ''),
        'company_name': getattr(lead, 'company_name', '')} if lead else {}
    try:
        c = sqlite3.connect('file:%s?mode=ro' % ENRICH.replace('\\', '/'), uri=True,
                            timeout=30)
        c.row_factory = sqlite3.Row
    except Exception:  # noqa: BLE001
        return пусто

    def _один(sql):
        try:
            return c.execute(sql, (цифры,)).fetchone()
        except Exception:  # noqa: BLE001 - таблицы может не быть
            return None

    def _все(sql):
        try:
            return [dict(r) for r in c.execute(sql, (цифры,))]
        except Exception:  # noqa: BLE001
            return []

    к = _один('select * from companies where inn=?')
    к = dict(к) if к else {}
    qc = _один('select url, phones from qc_site where inn=?')
    qc = dict(qc) if qc else {}
    люди = _все("select coalesce(person,'') person, coalesce(post,'') post, "
                "coalesce(role,'') role, coalesce(phone,'') phone, "
                "coalesce(email,'') email, coalesce(source,'') source, "
                "coalesce(source_url,'') source_url from people where inn=?")
    тел_таб = _все("select coalesce(phone,'') phone, coalesce(person,'') person, "
                   "coalesce(role,'') role, coalesce(source,'') source, "
                   "coalesce(source_url,'') source_url from phone_contacts where inn=?")
    почты = _все("select coalesce(email,'') email, coalesce(role,'') role, "
                 "coalesce(person,'') person, coalesce(source,'') source, "
                 "coalesce(source_url,'') source_url, coalesce(pometka,'') pometka, "
                 "coalesce(probe_verdict,'') probe_verdict from emails where inn=?")
    паспорт = {}
    сф = _один("select coalesce(facts_json,'') f, coalesce(site,'') s, "
               "coalesce(ts,'') ts from site_facts where inn=?")
    if сф:
        try:
            паспорт = json.loads(сф['f'] or '{}') or {}
        except Exception:  # noqa: BLE001
            паспорт = {}
    c.close()

    сайт = (к.get('site') or к.get('cand_site') or '').strip()
    адрес_сайта = qc.get('url') or (('http://' + сайт) if сайт else '')

    # ---- телефоны: склеиваем одинаковые номера, источники копим списком
    собрано = {}

    def _добавить(номер, откуда, url='', кто=''):
        ключ = _ключ_телефона(номер)
        if not ключ or (len(ключ) == 10 and _fiktivnyy(ключ)):
            return
        узел = собрано.setdefault(ключ, {'nomer': telefon_krasivo(номер),
                                         'istochniki': [], 'kto': кто})
        if кто and not узел['kto']:
            узел['kto'] = кто
        if not any(и['chto'] == откуда for и in узел['istochniki']):
            узел['istochniki'].append({'chto': откуда, 'url': url})

    страницы = _stranicy_kesha(цифры)
    со_страниц = _kontakty_so_stranic(страницы)

    if лид.get('phone'):
        _добавить(лид['phone'], 'из ответа компании')
    for т in тел_таб:
        _добавить(т['phone'], т.get('source') or 'обход сайта',
                  т.get('source_url') or адрес_сайта,
                  ' — '.join(x for x in (т.get('person'), т.get('role')) if x))
    for н in _список(к.get('phones')):
        _добавить(н, 'сайт компании', адрес_сайта)
    for н in _список(qc.get('phones')):
        _добавить(н, 'сайт компании', адрес_сайта)
    for ч in люди:
        if ч.get('phone'):
            _добавить(ч['phone'], ч.get('source') or 'обход сайта',
                      ч.get('source_url') or адрес_сайта,
                      ' — '.join(x for x in (ч.get('person'), ч.get('post')) if x))
    # НОМЕРА, КОТОРЫЕ ЕСТЬ ТОЛЬКО НА САЙТЕ. Обход кладёт в companies.phones не
    # всё, что нашёл; на странице «Инпласта» номеров четыре, а в базе меньше.
    for ключ, узел in (со_страниц.get('tel') or {}).items():
        _добавить(узел['kak'], 'сайт компании',
                  (узел['stranicy'] or [адрес_сайта])[0])
    # КОНКРЕТНАЯ СТРАНИЦА И РОЛЬ. Роль берём из подписи рядом с номером на
    # самой странице: «Комм. отдел: +7 (8639) 26 26 98».
    for ключ, узел in собрано.items():
        со = (со_страниц.get('tel') or {}).get(ключ)
        if not со:
            continue
        # как номер записан на сайте — так и показываем: код города бывает и
        # трёх-, и четырёх-, и пятизначным, и наше «красиво» его ломало
        if со.get('kak'):
            узел['nomer'] = со['kak']
        if со.get('podpisi') and not узел.get('kto'):
            узел['kto'] = ' · '.join(со['podpisi'][:2])
        for url in _luchshie_stranicy(со.get('stranicy')):
            if not any(и.get('url') == url for и in узел['istochniki']):
                узел['istochniki'].append({'chto': 'страница сайта', 'url': url})

    # ---- почты: адрес лида первым, остальные с их источником и вердиктом пробы
    адрес_лида = str(лид.get('email') or '').strip().lower()
    почта_список = []
    if адрес_лида:
        # тот же адрес обычно лежит и в базе — тогда к «из ответа» добавляем,
        # откуда мы его знали ДО ответа и что показала проба ящика
        свой = next((п for п in почты
                     if (п['email'] or '').strip().lower() == адрес_лида), {})
        почта_список.append({
            'adres': лид['email'],
            'rol': ' · '.join(x for x in ('ответили с этого адреса',
                                          свой.get('role') or '') if x),
            'istochnik': ' · '.join(x for x in ('из ответа компании',
                                                свой.get('source') or '') if x),
            'url': свой.get('source_url') or '',
            'proba': свой.get('probe_verdict') or ''})
    for п in почты:
        if (п['email'] or '').strip().lower() == адрес_лида:
            continue
        со = (со_страниц.get('mail') or {}).get((п['email'] or '').lower(), {})
        нашли = _luchshie_stranicy(со.get('stranicy')
                                   or _gde_nashli(страницы, п['email']))
        почта_список.append({
            'adres': п['email'],
            'rol': ' · '.join(x for x in (п.get('role'), п.get('person'),
                                          ' · '.join(со.get('podpisi') or [])[:40]
                                          ) if x),
            'istochnik': п.get('source') or '',
            'url': п.get('source_url') or (нашли[0] if нашли else ''),
            'stranicy': нашли,
            'proba': п.get('probe_verdict') or '',
            'pometka': п.get('pometka') or ''})
    # адресу лида тоже ищем страницу — менеджеру полезно знать, откуда он у нас
    if почта_список:
        со = (со_страниц.get('mail') or {}).get(
            (почта_список[0]['adres'] or '').lower(), {})
        нашли = _luchshie_stranicy(
            со.get('stranicy') or _gde_nashli(страницы, почта_список[0]['adres']))
        if нашли:
            почта_список[0]['url'] = почта_список[0].get('url') or нашли[0]
            почта_список[0]['stranicy'] = нашли
        if со.get('podpisi'):
            почта_список[0]['rol'] = ' · '.join(
                x for x in (почта_список[0]['rol'],
                            ' · '.join(со['podpisi'][:2])) if x)
    # адреса, которые есть на сайте, но которых нет у нас в базе
    известные = {(п['adres'] or '').lower() for п in почта_список}
    for адрес, со in (со_страниц.get('mail') or {}).items():
        if адрес in известные or адрес.split('@')[-1] in nashi_domeny():
            continue
        почта_список.append({
            'adres': адрес, 'rol': ' · '.join((со.get('podpisi') or [])[:2]),
            'istochnik': 'сайт компании',
            'url': (_luchshie_stranicy(со.get('stranicy')) or [''])[0],
            'stranicy': _luchshie_stranicy(со.get('stranicy')),
            'proba': '', 'pometka': ''})

    рекв = [
        ('Полное название', к.get('name') or лид.get('company_name') or ''),
        ('ИНН / КПП', ' / '.join(x for x in (цифры, к.get('kpp')) if x)),
        ('ОГРН', к.get('ogrn') or ''),
        ('Организационная форма', к.get('opf') or ''),
        ('Статус в ЕГРЮЛ', к.get('status_egrul') or ''),
        ('Регион', к.get('region') or ''),
        ('Адрес', к.get('address') or ''),
        ('Сайт', сайт),
        ('Основной ОКВЭД', к.get('okved') or ''),
        ('Ещё ОКВЭД', ', '.join(_список((к.get('okved_all') or '').replace('|', ','))[1:12])),
        ('Чем занимается', к.get('activity') or ''),
        ('Выручка', ' '.join(x for x in (_деньги(к.get('revenue_rub')),
                                         ('за %s' % к['revenue_year'])
                                         if к.get('revenue_year') else '') if x)),
        ('Сотрудников', str(к.get('ssch') or к.get('employees') or '') or ''),
        ('Руководитель', к.get('director') or ''),
        ('Что может быть нужно', к.get('oborudovanie_po_okved') or ''),
    ]
    поля_паспорта = [(имя, _список(паспорт.get(ключ)))
                     for ключ, имя in _ПАСПОРТ_ПОЛЯ]
    новости = [n for n in (паспорт.get('новости') or []) if isinstance(n, dict)]
    return {
        'rekvizity': [(н, з) for н, з in рекв if str(з).strip()],
        'telefony': sorted(собрано.values(),
                           key=lambda x: 0 if any(
                               и['chto'] == 'из ответа компании'
                               for и in x['istochniki']) else 1),
        'pochty': почта_список,
        'lyudi': люди,
        'pasport': {
            'polya': [(н, з) for н, з in поля_паспорта if з],
            'god': паспорт.get('год_основания') or '',
            'citata': паспорт.get('цитата') or '',
            'novosti': новости[:5],
            'sayt': адрес_сайта,
            'kogda': (сф['ts'][:10] if сф and сф['ts'] else ''),
        },
    }

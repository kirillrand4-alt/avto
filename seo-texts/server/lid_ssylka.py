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
import os
import re
import secrets
import sqlite3
import time

БД = os.environ.get('SENDER_DB', r'C:\sender\sender.db')
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
        return str(текст or '')

    def _замена(m):
        а = m.group(0)
        return '[наш адрес скрыт]' if а.rsplit('@', 1)[-1].lower() in наши else а

    return _АДРЕС.sub(_замена, str(текст or ''))


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

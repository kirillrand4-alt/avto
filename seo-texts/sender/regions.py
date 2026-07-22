"""
Маппинг регионов РФ в таймзоны IANA.

Преобразует текстовые названия субъектов РФ (из колонки «Регион» B2B-базы)
в IANA timezone для вычисления окон отправки по местному времени получателя.
"""

import re
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


# Маппинг корней названий регионов -> IANA timezone.
# Ключи отсортированы по длине (убыванию) внутри каждой зоны, чтобы избежать
# ложных срабатываний ('томск' vs 'омск').
REGION_TZ: dict[str, str] = {
    # UTC+2: Калининград
    'калининград': 'Europe/Kaliningrad',
    
    # UTC+3: Московская зона (европейская часть РФ)
    'нижегород': 'Europe/Moscow',
    'нижний новгород': 'Europe/Moscow',
    'ростов': 'Europe/Moscow',
    'москв': 'Europe/Moscow',   # голое «москва»
    'москов': 'Europe/Moscow',  # «московская область»
    'татарстан': 'Europe/Moscow',
    'казан': 'Europe/Moscow',
    'петербург': 'Europe/Moscow',
    'санкт-петербург': 'Europe/Moscow',
    'ленинград': 'Europe/Moscow',
    'архангел': 'Europe/Moscow',
    'мурман': 'Europe/Moscow',
    'вологод': 'Europe/Moscow',
    'карел': 'Europe/Moscow',
    'коми': 'Europe/Moscow',
    'ненец': 'Europe/Moscow',
    'новгород': 'Europe/Moscow',
    'псков': 'Europe/Moscow',
    'тверск': 'Europe/Moscow',
    'ярослав': 'Europe/Moscow',
    'костром': 'Europe/Moscow',
    'иванов': 'Europe/Moscow',
    'владимир': 'Europe/Moscow',
    'рязан': 'Europe/Moscow',
    'тульск': 'Europe/Moscow',
    'калуж': 'Europe/Moscow',
    'смоленск': 'Europe/Moscow',
    'брянск': 'Europe/Moscow',
    'орлов': 'Europe/Moscow',
    'курск': 'Europe/Moscow',
    'белгород': 'Europe/Moscow',
    'воронеж': 'Europe/Moscow',
    'липец': 'Europe/Moscow',
    'тамбов': 'Europe/Moscow',
    'пензен': 'Europe/Moscow',
    'мордов': 'Europe/Moscow',
    'чуваш': 'Europe/Moscow',
    'марий': 'Europe/Moscow',
    'кировск': 'Europe/Moscow',
    'кировобл': 'Europe/Moscow',
    'кирововбл': 'Europe/Moscow',
    'киров': 'Europe/Moscow',
    'краснодар': 'Europe/Moscow',
    'адыгея': 'Europe/Moscow',
    'ставропол': 'Europe/Moscow',
    'карачаево': 'Europe/Moscow',
    'кабардино': 'Europe/Moscow',
    'северная осетия': 'Europe/Moscow',
    'осетия': 'Europe/Moscow',
    'ингушет': 'Europe/Moscow',
    'чечен': 'Europe/Moscow',
    'дагестан': 'Europe/Moscow',
    
    # UTC+4: Самарская зона
    'самар': 'Europe/Samara',
    'удмурт': 'Europe/Samara',
    
    # UTC+4: Астраханская, Саратовская, Ульяновская, Волгоградская
    'астрахан': 'Europe/Astrakhan',
    'саратов': 'Europe/Saratov',
    'ульяновск': 'Europe/Ulyanovsk',
    'волгоград': 'Europe/Volgograd',
    
    # UTC+5: Уральская зона (Екатеринбург)
    'свердлов': 'Asia/Yekaterinburg',
    'екатеринбург': 'Asia/Yekaterinburg',
    'челябин': 'Asia/Yekaterinburg',
    'тюмен': 'Asia/Yekaterinburg',
    'курган': 'Asia/Yekaterinburg',
    'ханты': 'Asia/Yekaterinburg',
    'хмао': 'Asia/Yekaterinburg',
    'югра': 'Asia/Yekaterinburg',
    'ямало': 'Asia/Yekaterinburg',
    'янао': 'Asia/Yekaterinburg',
    'башкор': 'Asia/Yekaterinburg',
    'башкирия': 'Asia/Yekaterinburg',
    'оренбург': 'Asia/Yekaterinburg',
    'пермск': 'Asia/Yekaterinburg',
    
    # UTC+6: Омская зона
    'омск': 'Asia/Omsk',
    
    # UTC+7: Новосибирская зона
    'новосибир': 'Asia/Novosibirsk',
    'новокузнец': 'Asia/Novokuznetsk',
    'кемеров': 'Asia/Novokuznetsk',
    'кузбасс': 'Asia/Novokuznetsk',
    'томск': 'Asia/Tomsk',
    'барнаул': 'Asia/Barnaul',
    'алтай': 'Asia/Barnaul',
    
    # UTC+7: Красноярская зона
    'красноярск': 'Asia/Krasnoyarsk',
    'хакас': 'Asia/Krasnoyarsk',
    'тыва': 'Asia/Krasnoyarsk',
    'тува': 'Asia/Krasnoyarsk',
    
    # UTC+8: Иркутская зона
    'иркутск': 'Asia/Irkutsk',
    'бурят': 'Asia/Irkutsk',
    
    # UTC+9: Якутская зона
    'читинск': 'Asia/Chita',
    'забайкал': 'Asia/Chita',
    'чита': 'Asia/Chita',
    
    # UTC+9: Якутская
    'якутск': 'Asia/Yakutsk',
    'якут': 'Asia/Yakutsk',
    'саха': 'Asia/Yakutsk',
    'амурск': 'Asia/Yakutsk',
    'амур': 'Asia/Yakutsk',
    
    # UTC+10: Владивостокская зона
    'владивосток': 'Asia/Vladivostok',
    'приморск': 'Asia/Vladivostok',
    'хабаровск': 'Asia/Vladivostok',
    'хабар': 'Asia/Vladivostok',
    'еврейск': 'Asia/Vladivostok',
    
    # UTC+11: Сахалин, Магадан
    'сахалин': 'Asia/Sakhalin',
    'магадан': 'Asia/Magadan',
    
    # UTC+12: Камчатка, Чукотка
    'камчатск': 'Asia/Kamchatka',
    'камчатка': 'Asia/Kamchatka',
    'петропавловск': 'Asia/Kamchatka',
    'чукот': 'Asia/Anadyr',
    'анадыр': 'Asia/Anadyr',
}

# Ключи отсортированы по длине убыванию для корректного поиска
_SORTED_KEYS = sorted(REGION_TZ.keys(), key=len, reverse=True)


def region_to_tz(region: Optional[str]) -> Optional[str]:
    """
    Определяет IANA timezone по названию региона РФ.
    
    Нормализует входную строку (lower, ё->е, удаляет префиксы типа 'г.', 'обл.',
    'респ.'), затем ищет совпадение по корневым ключевым словам.
    
    Args:
        region: Название региона (может быть в произвольной форме).
    
    Returns:
        IANA timezone string или None, если регион не распознан.
    """
    if not region or not isinstance(region, str):
        return None
    
    # Нормализация: lowercase, ё->е
    normalized = region.lower().replace('ё', 'е')
    
    # Убираем типовые префиксы и суффиксы
    normalized = re.sub(r'\b(г\.|город|обл\.|область|респ\.|республика|край|ао|округ)\b', '', normalized)
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    
    if not normalized:
        return None
    
    # Поиск по ключам (длинные первыми)
    for key in _SORTED_KEYS:
        if key in normalized:
            return REGION_TZ[key]
    
    return None


def tz_valid(tz_name: str) -> bool:
    """
    Проверяет корректность IANA timezone через zoneinfo.
    
    Args:
        tz_name: Название таймзоны (например, 'Europe/Moscow').
    
    Returns:
        True, если таймзона существует и валидна, иначе False.
    """
    try:
        ZoneInfo(tz_name)
        return True
    except (ZoneInfoNotFoundError, KeyError, ValueError):
        return False

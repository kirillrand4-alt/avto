# Пересечение сайтов по поисковым запросам

Считалось по выгрузке запросов с дропа: `q_<домен>.txt` — 27 доменов,
Google + Яндекс, период **2026-05-25 — 2026-08-24**, 164 686 пар «домен × запрос».
Перекрёстная проверка — `yq.csv` (только Яндекс, 2026-06-18 — 2026-08-17,
94 980 пар): картина та же, те же пары в топе.

Запросы нормализованы: регистр, лишние пробелы, `ё → е`. После склейки
139 999 уникальных запросов на все сайты, 1 238 958 показов, 31 804 клика.

## Главное

| | запросов | показов |
|---|---|---|
| запрос есть только у одного сайта | 120 544 (86,1%) | 404 378 (32,6%) |
| запрос есть у 2+ сайтов | **19 455 (13,9%)** | **834 580 (67,4%)** |

Пересечение по номенклатуре запросов небольшое, но оно приходится ровно на
трафиковые запросы: **две трети всех показов и 68,7% кликов идут по запросам,
где стоят минимум два моих сайта.**

По поисковикам расходится сильно:

| поисковик | уник. запросов | спорных запросов | спорных показов |
|---|---|---|---|
| Google | 17 793 | 5 760 (32,4%) | 578 067 (**72,2%**) |
| Яндекс | 126 324 | 14 628 (11,6%) | 222 677 (50,8%) |

В Google сетка почти полностью наложена сама на себя; в Яндексе длинный
уникальный хвост, но половина показов всё равно спорная.

## По сайтам

`уник. показы` — доля показов сайта по запросам, которых нет ни у одного
другого моего сайта. `вторым номером` — доля показов сайта по запросам, где
соседний свой сайт стоит выше по средней позиции (порог 10 показов, чтобы
отсечь случайный хвост).

| сайт | показов | уник. показы | уник. клики | вторым номером | главный сосед (доля показов, пересечённых с ним) |
|---|---|---|---|---|---|
| prokompressor.ru | 545 433 | 42,6% | 59,2% | 29,5% | enger-air.ru (38,1%) |
| enger-air.ru | 247 773 | 25,0% | 37,5% | 17,8% | prokompressor.ru (73,8%) |
| berg-compressor.com | 97 218 | 9,0% | 7,2% | 31,6% | prokompressor.ru (77,9%) |
| berg-kompressor.ru | 49 257 | 13,9% | 76,3% | **55,9%** | berg-compressor.com (78,3%) |
| remeza-kompressor.ru | 45 710 | 32,3% | 69,1% | 18,0% | prokompressor.ru (66,7%) |
| meyer-corp.ru | 33 744 | 68,7% | 58,8% | 4,3% | vsefotoseparatory.ru (22,6%) |
| ac-kompressor.ru | 31 993 | 35,4% | 49,3% | 35,8% | prokompressor.ru (63,3%) |
| zif-kompressor.ru | 30 132 | 15,9% | 33,6% | 20,2% | prokompressor.ru (83,0%) |
| abac-kompressor.ru | 29 923 | 39,1% | 67,3% | 6,5% | prokompressor.ru (60,0%) |
| dali-kompressor.ru | 26 345 | 16,7% | 33,3% | 15,6% | prokompressor.ru (80,8%) |
| ekomak-kompressor.com | 17 545 | 19,1% | 23,3% | 19,8% | prokompressor.ru (77,7%) |
| crossair-compressor.ru | 16 948 | 24,3% | 30,5% | 38,0% | prokompressor.ru (72,6%) |
| comaro-kompressor.ru | 16 021 | 19,0% | 37,6% | 24,8% | prokompressor.ru (80,3%) |
| fini-compressor.com | 11 107 | 53,3% | 89,0% | 2,8% | prokompressor.ru (44,9%) |
| ironmac-compressor.com | 7 069 | 27,0% | 41,1% | 30,0% | prokompressor.ru (72,5%) |
| kraftmann-kompressor.com | 6 336 | 19,2% | 67,0% | 9,5% | prokompressor.ru (80,0%) |
| usort.ru | 6 247 | 25,3% | 48,4% | 27,9% | meyer-corp.ru (70,0%) |
| cmprg.ru | 5 733 | 27,5% | 76,0% | 16,8% | prokompressor.ru (69,9%) |
| vsefotoseparatory.ru | 3 164 | 13,7% | 24,1% | 36,8% | meyer-corp.ru (78,9%) |
| oil-free.ru | 2 328 | 17,1% | 27,8% | 44,3% | prokompressor.ru (70,4%) |
| dizel-compressor.ru | 2 276 | 9,0% | 10,5% | 34,4% | prokompressor.ru (85,5%) |
| ekomak-compressor.com | 1 787 | 5,0% | 6,7% | **76,7%** | ekomak-kompressor.com (91,0%) |
| nsk.prokompressor.ru | 1 646 | 11,1% | 42,9% | 31,3% | prokompressor.ru (80,4%) |
| barnaul.prokompressor.ru | 1 514 | 17,7% | 25,7% | 17,8% | prokompressor.ru (73,3%) |
| vladivostok.prokompressor.ru | 1 374 | 4,7% | 25,0% | 16,8% | prokompressor.ru (92,4%) |
| voronezh.prokompressor.ru | 210 | 24,8% | 100,0% | 31,0% | prokompressor.ru (70,5%) |
| po22.ru | 125 | 83,2% | 100,0% | 0,0% | prokompressor.ru (16,0%) |

## Значимые пары

Порог: у обоих сайтов не меньше 10 показов по запросу — так уходит случайный
хвост из опечаток и мусорных запросов. «Двойные показы» — сумма показов обеих
сторон по этим запросам.

| пара | общих запросов | перекрытие | двойные показы | доля показов A | доля B | клики A | клики B |
|---|---|---|---|---|---|---|---|
| prokompressor.ru ↔ enger-air.ru | 1 142 | 55,7% | 293 535 | 27,2% | 58,7% | 579 | 796 |
| prokompressor.ru ↔ berg-compressor.com | 324 | 45,2% | 118 600 | 11,8% | 55,8% | 233 | 9 813 |
| berg-compressor.com ↔ berg-kompressor.ru | 295 | 61,0% | 94 063 | 63,3% | 66,1% | **13 242** | **238** |
| enger-air.ru ↔ berg-compressor.com | 224 | 31,2% | 65 516 | 18,9% | 19,2% | 332 | 156 |
| prokompressor.ru ↔ remeza-kompressor.ru | 186 | 28,8% | 51 831 | 6,3% | 38,0% | 62 | 103 |
| prokompressor.ru ↔ berg-kompressor.ru | 194 | 40,1% | 41 778 | 4,0% | 40,0% | 70 | 152 |
| prokompressor.ru ↔ zif-kompressor.ru | 109 | 44,3% | 34 837 | 2,8% | 65,4% | 53 | 124 |
| prokompressor.ru ↔ ac-kompressor.ru | 148 | 45,3% | 30 591 | 3,3% | 39,3% | 102 | 133 |
| prokompressor.ru ↔ dali-kompressor.ru | 111 | 54,4% | 27 610 | 2,1% | 61,3% | 43 | 157 |
| ekomak-kompressor.com ↔ ekomak-compressor.com | 26 | 89,7% | 10 386 | 51,2% | 78,3% | 183 | 47 |
| meyer-corp.ru ↔ vsefotoseparatory.ru | 19 | 67,9% | 7 303 | 17,7% | 42,2% | 121 | 29 |
| meyer-corp.ru ↔ usort.ru | 41 | 70,7% | 4 728 | 8,4% | 30,3% | 95 | 21 |

По всей номенклатуре (без порога) самые «поглощённые» сайты — те, у кого
почти все запросы уже есть у старшего:

| пара | общих | перекрытие по меньшему сайту |
|---|---|---|
| prokompressor.ru ↔ vladivostok.prokompressor.ru | 228 | 87,0% |
| prokompressor.ru ↔ oil-free.ru | 426 | 77,9% |
| prokompressor.ru ↔ dizel-compressor.ru | 642 | 74,0% |
| prokompressor.ru ↔ nsk.prokompressor.ru | 299 | 68,4% |
| ekomak-kompressor.com ↔ ekomak-compressor.com | 161 | 63,1% |
| enger-air.ru ↔ oil-free.ru | 327 | 59,8% |
| meyer-corp.ru ↔ usort.ru | 1 689 | 57,6% |
| prokompressor.ru ↔ barnaul.prokompressor.ru | 259 | 56,3% |
| meyer-corp.ru ↔ vsefotoseparatory.ru | 541 | 56,2% |
| usort.ru ↔ vsefotoseparatory.ru | 520 | 54,0% |
| berg-compressor.com ↔ berg-kompressor.ru | 1 763 | 36,8% |

## Кластеры

Связь ставится, если общих запросов ≥ 25% от меньшего сайта пары.

1. **Ядро, 927 304 показа (75% всей сетки)** — prokompressor.ru, enger-air.ru,
   ac-kompressor.ru, zif-kompressor.ru, dali-kompressor.ru, ekomak-kompressor.com,
   crossair-compressor.ru, oil-free.ru, dizel-compressor.ru, ekomak-compressor.com
   и все четыре региональных поддомена (nsk / barnaul / vladivostok / voronezh).
2. **Berg, 146 475 показов** — berg-compressor.com + berg-kompressor.ru.
3. **Meyer, 43 155 показов** — meyer-corp.ru + usort.ru + vsefotoseparatory.ru.
4. Отдельно (пересечение ниже порога): remeza-kompressor.ru, abac-kompressor.ru,
   comaro-kompressor.ru, fini-compressor.com, ironmac-compressor.com,
   kraftmann-kompressor.com, cmprg.ru, po22.ru.

## Что из этого следует

* **Два прямых дубля.** `berg-kompressor.ru` и `ekomak-compressor.com` живут
  почти целиком на чужих запросах: 55,9% и 76,7% их показов — там, где
  парный сайт стоит выше. На значимых общих запросах berg-пары клики делятся
  13 242 против 238 — второй сайт присутствие даёт, трафик нет. В Яндексе
  перекрытие этой пары по значимым запросам 94,2% — это ровно тот профиль,
  на который смотрит аффилиат-фильтр. Оба сайта в одном Вебмастере, так что
  проверить связку стоит.
* **prokompressor.ru ↔ enger-air.ru — главная точка каннибализации по объёму.**
  7 484 общих запроса, 293 535 двойных показов на значимых, 58,7% показов
  enger-air.ru идут по запросам, которые есть и у prokompressor.ru. Обе
  стороны при этом почти не собирают кликов (579 и 796) — то есть по общим
  ВЧ-запросам вроде «винтовой компрессор» / «купить винтовой компрессор» обе
  висят на 5–17 позициях и обе не в деньгах.
* **prokompressor.ru теряет больше всех в абсолюте**: 160 791 показ (29,5%)
  приходится на запросы, где свой же сайт стоит выше — половина из них
  перехвачена enger-air.ru.
* **Региональные поддомены и мини-сайты** (oil-free.ru, dizel-compressor.ru,
  nsk/barnaul/vladivostok/voronezh) уникального спроса почти не приносят:
  75–95% их показов уже есть у головного сайта.
* **Чистые доноры без конфликта** — meyer-corp.ru (68,7% показов уникальны),
  fini-compressor.com (53,3%), abac-kompressor.ru (39,1%), remeza-kompressor.ru
  (32,3%). Их можно наращивать, не задевая ядро.

## Файлы

* `svodka-po-saytam.csv` — таблица по сайтам целиком.
* `peresechenie-matrica.csv` — все пары: общие запросы, Жаккар, коэффициент
  перекрытия, доля показов каждой стороны.
* `peresechenie-kvadrat.csv` — квадратная матрица «доля показов сайта-строки
  на запросах, которые есть и у сайта-столбца».
* `spornye-zaprosy-top2000.csv` — топ-2000 спорных запросов с показами,
  кликами и позициями всех участников. Полный список (19 455 строк) лежит на
  дропе как `PERESECHENIE-spornye-zaprosy.csv`.
* `report.txt`, `deep.txt` — полный вывод скриптов.

## Как пересчитать

```bash
# скачать с дропа q_*.txt (и yq.csv для сверки) в рабочий каталог, затем:
python3 build_overlap.py  <каталог>            # только загрузка и агрегация
python3 report_overlap.py <каталог> <куда>     # профиль, пары, спорные запросы
python3 report_deep.py    <каталог> <куда>     # значимые пары, «вторым номером», кластеры
python3 summary_table.py  <каталог> <куда>     # сводка по сайтам
```

# План выкладки волны: 24 статьи за 7 недель

Сгенерирован 20.08.2026 скриптом `plan_placements.py`, зерно `20260820` — план
воспроизводится точь-в-точь. Даты это ориентир для закупки, а не обязательство:
площадки публикуют с задержкой, и это нормально. Держать надо не конкретные числа,
а правила ниже — именно они, а не календарь, защищают кампанию.

## Правила, которые план соблюдает

| | Правило | Что закрывает |
|---|---|---|
| 1 | ≤2 статьи в неделю на **один акцепторный домен** | Решение владельца 20.08; совпадает с лимитом «≤2 новых домена на сайт/нед» из `FINAL-ACCEPTORS.md` |
| 2 | Темп рандомный: 1 или 2 в неделю, в среднем 1,8 | Ровный ритм «каждый вторник и пятницу» узнаваем сам по себе |
| 3 | ≤2 публикации в календарный день по всей кампании | Четыре поста в один день на четырёх донорах со ссылками на одну сеть читаются как одна закупка, даже если по каждому домену лимит соблюдён |
| 4 | Один URL акцептора — не чаще раза в 14 дней | Семь URL волны получают по две ссылки; они разведены |
| 5 | ≥2 дня между статьями на один акцептор | Две ссылки подряд в понедельник и вторник — тот же рисунок в миниатюре |
| 6 | Только будни | Публикация в выходной у большинства площадок уезжает на понедельник и ломает раскладку |
| 7 | Жанровые и тематические чередуются | Пять жанровых подряд — это пять нетематических площадок со ссылками на компрессоры за неделю |
| 8 | У каждого домена, кроме prokompressor, одна статья придержана на вторую половину | Иначе последние недели идут подряд на один акцептор |

Скрипт проверяет все восемь инвариантов сам и падает, если план их нарушил.

## Почему в начале плотно

Акцепторные домены не мешают друг другу: лимит «2 в неделю» считается на каждый
отдельно. В волне их шесть, и в первую неделю они стартуют параллельно — отсюда восемь
размещений. Дальше маленькие домены выбирают запас, и темп падает до пары в неделю
на одном prokompressor.

```
неделя:   1   2   3   4   5   6   7
статей:   8   4   2   2   3   2   3
         ████████  ████  ██  ██  ███  ██  ███
```

## Статей у акцептора

| Акцептор | Статей | Ссылок | Недель при 2/нед |
|---|---|---|---|
| prokompressor.ru | 12 | 14 | 6 |
| berg-compressor.com | 4 | 5 | 2 |
| enger-air.ru | 3 | 6 | 2 |
| ac-kompressor.ru | 2 | 2 | 1 |
| abac-kompressor.ru | 2 | 2 | 1 |
| dali-kompressor.ru | 1 | 2 | 1 |

## Календарь


### Неделя 1 — 8 размещений

| Дата | Акцептор | Донор | Тип | Статья |
|---|---|---|---|---|
| 24.08 пн | berg-compressor.com | gorod24.online | жанровая | `krymskie-predpriyatiya-rossijskoe-oborudovanie` |
| 24.08 пн | enger-air.ru | perekos.net | тематическая | `modulnye-kompressornye-stantsii-vs-samosbornye` |
| 25.08 вт | dali-kompressor.ru | fgisrf.ru | тематическая | `podbor-vintovogo-kompressora-dlya-proizvodstva` |
| 25.08 вт | prokompressor.ru | citaty.info | жанровая | `tsitaty-o-masterstve-i-professionalizme` |
| 27.08 чт | ac-kompressor.ru | truckmix.ru | тематическая | `dizelnye-peredvizhnye-kompressory-dlya-vyezdnykh-rabot` |
| 27.08 чт | enger-air.ru | moluch.ru | тематическая | `azotnyye-generatory-princip-raboty-i-primeneniye` |
| 28.08 пт | abac-kompressor.ru | factories.kz | тематическая | `vybor-vintovogo-kompressora-dlya-proizvodstva` |
| 28.08 пт | prokompressor.ru | ess-ltd.ru | тематическая | `vybor-vintovogo-kompressora-dlya-tsekha` |

### Неделя 2 — 4 размещения

| Дата | Акцептор | Донор | Тип | Статья |
|---|---|---|---|---|
| 31.08 пн | berg-compressor.com | afk-arena.com | жанровая | `ot-peska-do-rtx-kak-proizvodyat-videokarty` |
| 01.09 вт | prokompressor.ru | 4tololo.ru | жанровая | `szhatyy-vozdukh-ubivaet` |
| 03.09 чт | prokompressor.ru | metallicheckiy-portal.ru | тематическая | `azotnye-stantsii-v-metallurgii` |
| 04.09 пт | berg-compressor.com | topclimat.ru | тематическая | `kompressor-s-osushitelem-dlya-montazha-ventilyatsii` |

### Неделя 3 — 2 размещения

| Дата | Акцептор | Донор | Тип | Статья |
|---|---|---|---|---|
| 07.09 пн | prokompressor.ru | kakoj-segodnja-prazdnik.com | жанровая | `den-mashinostroitelya-oborudovanie-otrasli` |
| 10.09 чт | prokompressor.ru | flotenk.ru | тематическая | `vozdukhosnabzhenie-ochistnykh-sooruzheniy` |

### Неделя 4 — 2 размещения

| Дата | Акцептор | Донор | Тип | Статья |
|---|---|---|---|---|
| 15.09 вт | prokompressor.ru | nashaplaneta.net | жанровая | `vysokogornye-oteli-kislorod-dlya-turistov` |
| 18.09 пт | prokompressor.ru | get-color.ru | жанровая | `ral-industrial-color-system-for-designers` |

### Неделя 5 — 3 размещения

| Дата | Акцептор | Донор | Тип | Статья |
|---|---|---|---|---|
| 21.09 пн | berg-compressor.com | koch-market.ru | тематическая | `kompressor-dlya-pokrasochnogo-uchastka` |
| 22.09 вт | prokompressor.ru | tvcenter.ru | жанровая | `stars-before-fame-jobs` |
| 24.09 чт | abac-kompressor.ru | lada-granta.ru | тематическая | `kompressory-dlya-avtoservisa-vybor-oborudovaniya` |

### Неделя 6 — 2 размещения

| Дата | Акцептор | Донор | Тип | Статья |
|---|---|---|---|---|
| 30.09 ср | prokompressor.ru | berkat.ru | жанровая | `rabota-na-proizvodstve-vostrebovannye-spetsialnosti` |
| 02.10 пт | prokompressor.ru | satom.ru | жанровая | `kak-delayut-metallicheskuyu-mebel-dlya-dachi` |

### Неделя 7 — 3 размещения

| Дата | Акцептор | Донор | Тип | Статья |
|---|---|---|---|---|
| 08.10 чт | enger-air.ru | mplast.by | тематическая | `oilless-compressors-plastic-production` |
| 08.10 чт | prokompressor.ru | twizz.ru | жанровая | `kak-delayut-veshchi-udivitelnye-fakty-proizvodstva` |
| 09.10 пт | ac-kompressor.ru | galan.ru | тематическая | `vintovye-kompressory-dlya-proizvodstvennogo-zdaniya` |

## Перед каждой закупкой

1. Записать строку в `PLACEMENTS-LOG.md` **до** оплаты. Источник истины по числу ссылок
   на акцептор — журнал, а не этот план.
2. Сверить, что с прошлой ссылкой на тот же URL прошло 14 дней.
3. После публикации проверить, что ссылка **dofollow**: площадка может молча поставить
   `rel="nofollow"`, и тогда размещение теряет смысл.
4. Площадка задержала выход — двигать только эту статью на ближайший свободный день,
   где не нарушены потолки, а не весь хвост плана.

## Пересобрать

```bash
cd seo-texts/guest-posts
JOBS_MODULE=wave-jobs python3 plan_placements.py              # тот же план
JOBS_MODULE=wave-jobs python3 plan_placements.py --seed 777   # другая раскладка
JOBS_MODULE=wave-jobs python3 plan_placements.py --start 2026-09-01
```

Последовательность типов по датам: `ЖТТЖТТТТЖЖТТЖТЖЖТЖТЖЖТЖТ` (Т — тематическая, Ж — жанровая).


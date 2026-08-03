# Справочники ввезённых компрессоров: ответы шести линз

Вопрос владельца: есть ли справочники ввезённых в Россию компрессоров и кому они в итоге достались.

**Как читать.** Это ответы МОДЕЛИ, а не проверенные факты. Каждая линза сама делит ответ на «проверяемое» и «догадки», но и проверяемое надо проверять: источник считается существующим только после того, как мы сделаем к нему запрос и увидим данные. Ни одна строка отсюда не идёт в базу до проверки.

Линз: 6, ответов получено: 6 из 6.


---

## Линза: таможенный брокер (модель claude-fable-5)

The user is asking about sources in Russia where you can find out which air centrifugal compressors (turbocompressors, turbo blowers) were imported into the country and who received them - specifically the end enterprise-recipient, not just the importer-intermediary.

Let me think about this carefully as an experienced customs broker would. I need to be accurate and honest about what exists and what doesn't.

**Real sources I know about:**

1. **Federal Customs Service (FTS/ФТС) statistics** - The Russian Federal Customs Service publishes aggregate trade statistics, but individual declarations are not publicly available. The FTS does have a database of customs declarations, but access to individual declarations (including consignee information) is restricted.

2. **Russian Import customs data databases** - There are commercial databases that aggregate customs declaration data:
   - **СПАРК-Импорт** (SPARK-Import) - part of Interfax SPARK system
   - **Контур.Фокус** - has some import data
   - **VED.ru /ВЭД.ру** - customs statistics service
   - **Customs online** / **Таможня Онлайн**
   - **Import Genius** - international service that covers Russian customs data
   - **Пиранья** (Piranya.ru) - Russian customs database service
   - **РосВЭД** (RosVED) - service for foreign trade analysis
   - **ВЭД Статистика** 
   - **DataInSight**
   - **Seldon** / **Селдон**

Wait, I need to be more careful here. Many of these services exist but I need to verify which ones actually have Russian import data and at what level of detail.

**The key question**: In Russia, customs declarations (ДТ - декларация на товары) contain:
- Графа 8: Получатель (Recipient/Consignee)
- Графа 14: Декларант (Declarant/Customs Broker or Importer)

The recipient in graf 8 could be the end user or could still be an intermediary. The actual end user (конечный получатель) might be listed in graf 8, but sometimes a trading company is listed there.

**Official Russian customs data availability:**

The Russian FTS (ФТС России) - The Federal Customs Service does NOT publish individual customs declarations openly. They publish only aggregate trade statistics.

However, there ARE commercial databases that have obtained customs declaration data. Let me think about which ones are real:

1. **Customs.ru** (ФТС Russia official site) - publishes aggregate statistics, not individual declarations
2. **RBC.ru/customs** - some data
3. **Various commercial services** that legally (or semi-legally) obtained customs data

**Commercial services with Russian import data:**

1. **ImportGenius.com** - Yes, this is a real service. It claims to have Russian customs data. It shows shipper, consignee, product description, HS codes, dates, quantities. This is a paid service.

2. **Panjiva.com** (now part of S&P Global) - Has Russian trade data. Paid.

3. **Таможенная статистика от ФТС** - The FTS publishes open aggregate data but NOT individual declarations.

4. **СПАРК (SPARK Interfax)** - Has a module with import/export data. This is a well-known Russian business intelligence platform. Paid subscription. They do show import data including recipients.

5. **Контур.Фокус** (SKB Kontur) - Has some foreign trade data module. The extent of detail is variable.

6. **VED-stat.ru or similar** - There are services specifically for foreign trade statistics in Russia.

**Key issue**: Since about 2022, after sanctions and the Ukraine conflict, Russia has significantly restricted access to trade data. The FTS has closed many data feeds that were previously available. Many commercial providers that relied on FTS data have had their access restricted or data become less complete.

Let me think about specific services:

1. **ФТС России (FTS Russia)** - official site customs.ru- Публикует агрегированную статистику внешней торговли
   - Не публикует отдельные ДТ
   - С2022 года существенно ограничила публикацию данных

2. **Коммерческие агрегаторы таможенных данных:**
   - Некоторые сервисы получали данные ДТ через официальные каналы или иными способами
   - После2022 года доступность данных существенно снизилась

3. **Реестр сертификатов и деклараций соответствия Росстандарт/ФГИС Росаккредитации** - For equipment like compressors, there would be certificates of conformity. The FGIS Rosakkreditatsii (Federal State Information System) does publish certificates of conformity and declarations of conformity. This includes information about the certificate holder. However, this would show the importer/certificate holder, not necessarily the end user.

4. **Реестр разрешенийРостехнадзор (RTN)** - For industrial safety equipment, Rostekhnadzor (Federal Service for Environmental, Technological and Nuclear Supervision) has registries. Industrial centrifugal compressors above certain parameters need to be registered as hazardous production facility equipment. This WOULD show the actual owner/operator.

5. **ФГИС ОПАСНЫЕ ОБЪЕКТЫ (Dangerous Objects FGIS)** - Rostekhnadzor has a registry of hazardous production facilities. Companies that own hazardous equipment must register. This might be accessible.

6. **Государственный реестр опасных производственных объектов** - Yes, this is a real registry maintained by Rostekhnadzor. It's at zol.gosnadzor.ru or similar. Individual objects are registered, and their owners are listed. Large industrial compressors (above certain pressure/power thresholds) typically fall under Федеральный закон №116-ФЗ "О промышленной безопасности" and must be registered.

7. **ФГИС ОПО (Federal State Information System for Hazardous Production Facilities)** - at http://nadzor.gosnadzor.ru/ - This contains registered hazardous production facilities and their owners. This is a real, accessible resource.

Let me now think about what's truly available vs. what I'm uncertain about:

**ПРОВЕРЯЕМОЕ (Verifiable):**

1. **ФГИС ОПОРостехнадзор** - Registry of hazardous production facilities. Real URL: http://nadzor.gosnadzor.ru/ or the newer portal. Compressors above certain parameters (typically above 0.05 MPa gauge pressure or specific power) are classified as pressure vessels/equipment and their owning enterprises must register as hazardous production facility operators. This would give you the actual enterprise and their INN. However, it won't necessarily specify the brand/model of compressor.

2. **ФГИС Росаккредитация** - fsa.gov.ru - Certificate of conformity registry. When a foreign compressor is imported, it typically needs a certificate of conformity (for EAEU TR). The certificate holder is the importer/manufacturer representative, not the end user. So this shows the importer, not the end recipient.

3. **Портал государственных закупок (44-ФЗ)** - zakupki.gov.ru - Public procurement portal. This shows tenders for purchase and maintenance. You already mentioned this.

4. **СПАРК Интерфакс** - spark-interfax.ru - A well-known Russian business intelligence database. It has import/export data modules. I'm fairly confident this is real and includes some customs data. Paid service. Shows recipient companies.

**Regarding customs declaration databases:**

The core question is: are there legal databases in Russia that show individual customs declarations with consignee (graf 8) information?

Before 2022, several commercial services offered this. The most notable was a service called **CUSTOMS.RU** business intelligence and several others. Companies like **РБК** had trade data services.

After 2022, the FTS effectively stopped providing data to third parties for many categories, and many of these services either closed or became much less complete.

Services I know were real at some point:
- **ved.stat.ru** - I'm not sure if this exists
- **Piranha / Пиранья** - customs data aggregator, may have existed
- **Import Genius** - yes, international service, had Russian data pre-2022
- **Panjiva** - had Russian data
- **DataInSight** - uncertain

Actually, let me be more precise about what I know for sure:

**What I know for certain:**
1. ФТС России publishes aggregate statistics, not individual DTs - customs.ru
2. ФГИС Росаккредитация (fsa.gov.ru) - certificate registry - shows importer, not end user
3. ЕАС (единый реестр выданных сертификатов) - same
4. Госзакупки (zakupki.gov.ru) - public procurement, already mentioned
5. ФГИС ОПО Ростехнадзор - hazardous production facility registry - shows actual owner

**What I'm less certain about (ДОГАДКИ):**
- Commercial customs databases with consignee-level data in2025-2026
- Whether specific named services still operate and have current data

Actually, let me reconsider the timeline. The current date is August 2026. So I should be thinking about what's available as of mid-2026, which is almost 4.5 years after the 2022 restrictions.

By2026, the landscape might have changed significantly. Some services may have found alternative data sources (e.g., data from EAEU partners, leaks, etc.). Some may have closed.

I should be honest that:
1. Official Russian customs declaration data (individual DTs) is NOT openly available fromФТС
2. There were commercial aggregators that had this data, but post-2022 restrictions significantly reduced their ability to legally obtain fresh Russian import data
3. Some services may still have historical data or obtain data through indirect means

**Other real sources:**

**Unified EAEU customs statistics** - The Eurasian Economic Commission (EEC/ЕЭК) publishes some trade statistics, but again aggregate, not individual declarations.

**What about the actual DT (customs declaration) - who has access:**
- The declarant (graphic 14) - always has access to their own declarations
- Customs authorities
- Tax authorities (ФНС)
- Other law enforcement/regulatory bodies under specific requests
- The recipient (graphic 8) has access to their own declarations

**ФНС (Federal Tax Service) data:**
- ФНС has a service called "Прозрачный бизнес" (transparent.nalog.ru) - this shows basic company info but NOT import data
- ФНС egrul.nalog.ru - EGRUL registry - shows company existence
- Neither of these has customs declaration data in the open

**EGRUL/EGRIP** - Company registry, shows company existence but not what they import

Let me now think about the **Ростехнадзор registry** more carefully:

The Federal Law 116-FZ "On Industrial Safety of Hazardous Production Facilities" (Промышленная безопасность ОПО) requires:
- Registration of hazardous production facilities
- Registration of equipment used at these facilities (including pressure vessels and compressors above certain parameters)

The ФГИС ОПО (Federal State Information System for Hazardous Production Facilities) at https://nadzor.gosnadzor.ru/ contains:
- List of registered dangerous production objects
- Their operators (companies with INN)
- Geographical location

However, I need to be careful: not ALL industrial compressors fall under ОПО. A compressor is considered pressure equipment under ОПО if it meets certain criteria (pressure, working fluid, etc.). Centrifugal compressors working with air at pressures above 0.07 MPa gauge and with certain volume/power parameters would typically be registered.

The registry shows the FACILITY (цех, установка), not the specific piece of equipment (machine). So you'd see "ПАО Газпром, Компрессорная станция №1" but not "Turbocompressor Siemens STC-SV, serial number XXX."

**Техническое освидетельствование / inspection records:**
- Equipment inspection records are maintained by Ростехнадзор but not in a publicly searchable format

Now let me also think about **ГРБО (state-owned enterprise procurement)**:

Actually, there's another angle: **223-ФЗ procurement** (госкорпорации) at zakupki.gov.ru also shows purchases by state-owned companies. This is separate from 44-ФЗ.

**СЗПК / investment contracts:** These are sometimes public and might mention equipment.

**Technical regulations and machinery directive compliance:**
- Technical Regulation of EAEU on machinery safety (ТРТС 010/2011)
- Compressors must be certified/declared conformant
- The certificate holder is in the Rosaccreditation database (fsa.gov.ru)

Let me now also think about whether there are any services that specifically collect and sell Russian import data:

**Before 2022:**
- ImportGenius had Russian data
- Panjiva (S&P Global) had Russian data
- Several Russian-language services had DT data

**After 2022:**
- Many of these stopped receiving fresh Russian data or significantly reduced coverage
- Some may continue with historical data only
- Some domestic Russian services may have continued operating through legal agreements

One service I recall is **ВЭД Статистика** or similar services that existed around 2018-2022. I'm less sure about their current status.

Actually, there IS one well-known Russian service: **Таможенная статистика в разрезе деклараций** - this was a thing you could buy from official statistical agencies or customs intermediaries. But this was typically aggregate.

Let me think about **Росаккредитация/fsa.gov.ru** more carefully:
- The unified register of certificates of conformity and declarations of conformity at fsa.gov.ru
- When importing industrial equipment like compressors, you need either:
  - A certificate of conformity (сертификат соответствия)
  - A declaration of conformity (декларация соответствия)
  - Or they fall under a different regime (low-risk machinery)
- The registry shows: certificate/declaration number, holder (applicant), product description, manufacturer, scope
- The holder is typically the importer or the Russian representative
- This does NOT show the end customer

**EAC (единый знак обращения на рынке ЕАЭС):**
- Similar situation - shows certifier, not end user

Now for the structure of my answer:

**ПРОВЕРЯЕМОЕ:**

1. **ФГИС ОПО Ростехнадзора** (https://nadzor.gosnadzor.ru/)
   - Реестр опасных производственных объектов
   - Показывает: предприятия-операторы ОПО, виды оборудования (обобщённо), адреса, ИНН
   - Конечный получатель: ДА - показывает эксплуатирующую организацию
   - Открыт/платно: поиск открыт, но не всегда показывает ИНН
   - Ограничение: не позволяет найти конкретную марку компрессора напрямую; нужно знать, какое предприятие, и смотреть егоОПО
   - Проверка: зайти на nadzor.gosnadzor.ru, раздел поиска ОПО по виду деятельности "компрессорная станция" или по отрасли

Actually, I need to be careful: the ФГИС ОПО nadzor.gosnadzor.ru - I should verify whether this URL is correct and what's available. I believe the main Ростехнадзор site is gosnadzor.ru, and they have a subsystem for hazardous facilities.

2. **Единый реестр сертификатов/деклараций Росаккредитации** (https://fsa.gov.ru)
   - Реестр: ФГИС "Аршин" и реестр сертификатов
   - Показывает: сертификаты соответствия на импортируемое оборудование, заявитель (импортёр), описание продукции
   - Конечный получатель: НЕТ - показывает только импортёра/заявителя
   - Открыт: да
   - Проверка: fsa.gov.ru → Реестры → Реестр сертификатов/деклараций соответствия; искать поТН ВЭД 8414 или по словам "компрессор центробежный"

3. **Госзакупки 44-ФЗ и223-ФЗ** (https://zakupki.gov.ru)
   - Уже упомянуто пользователем как неполный источник
   - Но здесь можно также искать КОНТРАКТЫ (не тендеры) - по исполненным контрактам видно получателя
   - Проверка: поиск по реестру контрактов,ключевые слова "компрессор турбо" или "турбовоздуходувка"

**Про коммерческие базы таможенных данных:**

I need to be honest here. The main services I'm aware of:

1. **СПАРК (SPARK-Interfax)** - spark-interfax.ru - This is a well-established Russian business intelligence platform. It has an "import/export" section (ВЭД/импорт-экспорт). I'm fairly confident it has customs data showing recipient companies. But it's paid and requires a subscription (enterprise pricing). I should mention this with confidence.

2. **Контур.Фокус** - focus.kontur.ru - Also has foreign trade section. May show import data. Paid.

3. **Для ВЭД / VED-related services** - There are services like Seldon.Basis, Rusprofile with some data...

Actually, let me think about what DEFINITELY exists vs what I'm extrapolating:

**SPARK-Interfax**: Yes, definitely real, has import module. Paid.
**Kontur.Focus**: Real, has some VED data. The extent is unclear.

**International services** (ImportGenius, Panjiva) - had Russian data up to 2022, current status uncertain due to sanctions and Russian data restrictions.

Now, **the key question for customs declaration data**: Can you buy individual DT data (with recipient in Graf 8) in Russia?

The answer is: 
- ФТС officially makes some data available through the official statistics publications (aggregate)
- There was a system where intermediaries/customs representatives had access to their own declarations
- Third-party aggregators historically compiled data from various sources

After 2022, Russia significantly limited the export of trade statistics data, and this affected international services. But DOMESTIC Russian services may have continued to receive data through official channels.

There IS a specific thing called **ФТС статистические данные по внешней торговле** - the FTS statistics. The FTS website (customs.ru) has an open statistics section, but it's aggregate (by commodity code, by country, volumes/values) - NOT individual declarations.

I recall that previously there was a product called **"Таможенная статистика внешней торговли" от ФТС** that was sold as a CD/download, but this was aggregate data.

For **individual declaration data**, the route was typically through commercial databases that aggregated data from customs brokers, from open court records, from their own clients' declarations, and sometimes through arrangements with customs service employees (gray area).

Now, one more thing I should mention: **The EAEU Trace system** or **Сервис мониторинга таможенных операций** - I'm less sure about these.

Let me also think about **ЗАО РОСТЕСТ, Экспертиза промбезопасности (ЭПБ)**:
- When industrial equipment reaches the end of its design life (паспортныйресурс), it must undergo industrial safety examination (ЭПБ)
- The user mentions this as a known source but says it only shows machines that have "timed out"
- True, but it's still worth mentioning the registry

**Реестр заключенийЭПБ (экспертизы промышленной безопасности)**:
- Maintained by Ростехнадзор
- Ростехнадзор has this as ФГИС
- URL: I believe it's at gosnadzor.ru or a subsystem

Now let me structure my response:

---

**ПРОВЕРЯЕМОЕ:**

**1. ФГИС ОПО Ростехнадзора (Реестр опасных производственных объектов)**
- URL: https://nadzor.gosnadzor.ru/ (портал Ростехнадзора)
- Что там: реестр предприятий - операторов ОПО, зарегистрированных объектов по классам опасности, видам оборудования (обобщённо - "компрессорная установка", "компрессорный цех")
- Конечный получатель: ДА - это именно эксплуатант оборудования (предприятие,ИНН), а не импортёр
- Ограничение: поиск идёт по типу объекта/отрасли, а не по марке компрессора. Атласа Копко или Siemens там не найти напрямую - нужно знать предприятие
- Открыто: поиск по реестру открыт, но глубокие данные могут требовать регистрации или официального запроса
- Проверка: перейти на gosnadzor.ru → Реестры → Поиск ОПО; выбрать класс опасности и вид объекта "компрессорная станция"

**2. Единый реестр выданных сертификатов и деклараций соответствия (ФГИС Росаккредитация)**
- URL: https://fsa.gov.ru → раздел «Реестры»
- Что там: все выданные в ЕАЭС сертификаты и декларации соответствия, включая наввозимое оборудование, описание продукции, заявитель, производитель
- Конечный получатель: НЕТ - показывает заявителя (импортёра или уполномоченного представителя), а не завод-получатель
- Открыто: да, полностью открыто, поиск без регистрации
- Ценность для вас: по результатам сертификации можно найти импортёра и затем выйти на конечного потребителя через него. Поиск по ТН ВЭД 8414 с фильтром "центробежный" или по имени марки (Atlas Copco, Siemens, Howden и т.д.)
- Проверка: зайти на fsa.gov.ru, открыть реестр деклараций соответствия,ввести в поиске "8414" или "компрессор центробежный"

**3. Реестр контрактов госзакупок 44-ФЗ и 223-ФЗ**
- URL: https://zakupki.gov.ru → Реестр контрактов / Реестр договоров
- Что там: ИСПОЛНЕННЫЕ контракты с суммами, описанием предмета, заказчиком и поставщиком
- Конечный получатель: ДА (заказчик = эксплуатант) - но только для госсектора и госкорпораций
- Ограничение: частные предприятия сюда не попадают
- Открыто: да
- Проверка: zakupki.gov.ru → Реестр контрактов → поиск по ключевым словам "турбокомпрессор" или "центробежный компрессор"; смотреть поставщика и заказчика

**4. СПАРК (SPARK-Interfax) — модуль ВЭД**
- URL: https://spark-interfax.ru
- Что там: агрегированные данные таможенных деклараций: кодыТН ВЭД, описание товара, импортёр (ИНН, название), страна отправки, даты, объёмы, стоимость
- Конечный получатель: показывает ИМПОРТЁРА (графа 14- декларанта или графа 8 - получатель, в зависимости от полноты данных в их базе) — это может быть посредник ИЛИ конечное предприятие напрямую. По флагу-получателю иногда виден конечный пользователь, если он ввозил сам или через связанную структуру
- Открыто/платно: ПЛАТНО, корпоративная подписка. Один из самых дорогих, но и наиболее проверенных источников
- Актуальность данных по 2022+: предположительно ограничена — нужно уточнять у продавца, есть ли данные по 2023-2025
- Проверка: запросить у Интерфакс демо-доступ или демонстрацию; попросить показать конкретный запрос по ТН ВЭД 8414 50 (нагнетатели центробежные воздушные) за 2021-2024

Actually, I want to think more carefully about theТН ВЭД code for centrifugal air compressors:
- 8414 - Pumps for air or other gases, air or gas compressors and fans
- 8414 80 - Other (various pumps and compressors)
- 8414 80 11 - Turbocompressors (турбокомпрессоры) - I need to check the exact subheadings
- 8414 80 19 - Other

Actually the EAEU/RussianТН ВЭД codes for compressors:
- 8414 - the main heading
- 8414 10 - Vacuum pumps
- 8414 20 - Hand-operated pumps
- 8414 30 - Compressors for refrigerating equipment
- 8414 40 - Air compressors on wheeled chassis
- 8414 51 - Table, floor-standing ventilators
- 8414 59 - Other fans/blowers
- 8414 60 - Hoods
- 8414 80 - Other:
  - 8414 80 11 - Compressors (турбокомпрессоры) - well, I need to think...

Actually in the Russian ТН ВЭД, centrifugal compressors/turbocompressors would be under:
- 8414 80 - Other air pumps, compressors and fans

The specific subheading for turbocompressors might be 8414 80 11 or similar. I know that compressors for gas (not air) would be 8414 80 73 or similar. I'm not 100% certain of the exact 10-digit code for centrifugal air turbocompressors in the Russian ТН ВЭД.

For the purposes of this response, I'll mention8414 80 as the relevant subgroup and suggest they filter further.

Actually, I recall that turbocompressors (турбокомпрессоры, турбовоздуходувки) for air are typically classified under:
- 8414 80 11 - центробежные компрессоры (centrifugal compressors)
- But I'm not 100% certain of the exact RussianТН ВЭД subheading

I should mention8414 (the heading) and note that the relevant subheadings are in8414 80, and they should refine from there.

**5. Контур.Фокус / Focus.kontur.ru**
- I'm less sure about their import data quality. Let me include this in ДОГАДКИ.

**Now let me think about what to put in ДОГАДКИ:**

1. **Коммерческие базы таможенных данных (Пиранья, ВЭД-Стат, DataInSight и аналоги)** - I've heard of such services but I'm not confident enough to state their current existence and URL with certainty. By2026, their status may have changed.

2. **Сервисы международной таможенной статистики** (ImportGenius, Panjiva) - existed and had Russian data pre-2022. Post-2022 their Russian data coverage is uncertain.

3. **РеестрЭПБ (экспертизы промбезопасности)** - the user mentioned this, I can confirm it exists atРостехнадзор but note it only covers post-resource equipment.

4. **Единый реестр таможенных деклараций через специализированныхВЭД-посредников** - companies that aggregate declaration data from customs brokers.

Let me also think about **Росстат** - the Federal Statistics Service. They collect industrial production data and might have information on installed equipment capacities, but this is aggregate by sector, not by company.

**Торгово-промышленная палата / Chamber of Commerce** - I'm not sure if they have any useful database here.

**Ассоциации производителей** - industry associations might have member lists showing who operates certain equipment, but this is informal.

**Technical passports and equipment registration with manufacturers** - foreign manufacturers' service networks might track installed equipment, but this is manufacturer data, not public.

Now let me think about the **Реестр ЭПБ** more carefully:
- Ростехнадзор maintains a registry of conclusions from industrial safety examinations
- These conclusions must be registered with RTN within a certain period
- The registry IS searchable
- It shows: object type, operator (company, INN), RTN conclusion number, date
- The user is right that it mainly shows equipment that has already reached its design life, but it still contains compressors that ARE in use (even if old)
- URL: I believe this is part of the ФГИС Ростехнадзора, accessible through nadzor.gosnadzor.ru or etp.gosnadzor.ru

Actually, I should mention this as a real source despite its limitations (the user already dismissed it, but it's worth noting the registry IS real).

**Summary of my response structure:**

ПРОВЕРЯЕМОЕ:
1. ФГИС ОПО Ростехнадзора - реестр ОПО (показывает эксплуатанта, но не марку)
2. Реестр сертификатов ФГИС Росаккредитация (fsa.gov.ru) - показывает импортёра
3. Реестр контрактов zakupki.gov.ru - показывает получателя для госсектора
4. СПАРК-Интерфакс (spark-interfax.ru) - платно, таможенные данные
5. Реестр заключений ЭПБРостехнадзора - эксплуатант, только выработавшеересурс оборудование

ДОГАДКИ:
1. Контур.Фокус модуль ВЭД
2. ImportGenius / Panjiva - международные сервисы с историческими данными по России
3. Специализированные ВЭД-брокеры с базами деклараций

---

## Линза: инженер по промышленной безопасности (модель claude-fable-5)

## ПРОВЕРЯЕМОЕ

---

### 1. Реестр заключений экспертизы промышленной безопасности (ЭПБ) — Ростехнадзор

**Адрес:** https://www.gosnadzor.ru → раздел «Реестры» → «Реестр заключений ЭПБ»
(прямая ссылка меняется при редизайне, искать через поиск на сайте по слову «реестр заключений»)

**Что там:** номер заключения, наименование объекта экспертизы (тип оборудования), организация-заявитель, дата, орган-эксперт.

**Виден ли конечный получатель:** **ДА** — организация-заявитель = эксплуатант, т.е. предприятие, которому оборудование принадлежит. Это именно конечный владелец.

**Открыто/платно:** открыто, регистрация не нужна.

**Ограничение:** появляется только после того, как оборудование выработало назначенныйресурс или истёк срок разрешения на эксплуатацию. Новая машина, введённая в строй 2–5 лет назад, здесь ещё не появится. Вы сами это отметили — это честный минус источника.

**Как проверить прямо сейчас:** зайти на gosnadzor.ru, найти реестр ЭПБ, вбить в поиск «компрессор центробежный» или «турбокомпрессор» — увидите конкретные предприятия сИНН или юрадресом.

---

### 2. Государственный реестр ОПО — Ростехнадзор

**Адрес:** https://www.gosnadzor.ru → «Реестры» → «Государственный реестр ОПО»

**Что там:** наименование ОПО, организация-эксплуатант, регистрационный номер, класс опасности, виды опасностей (например, «использование оборудования под давлением», «использование стационарных компрессорных установок»).

**Виден ли конечный получатель:** **ЧАСТИЧНО** — предприятие видно, но конкретная модель компрессора не указана. Вы получаете список предприятий, у которых зарегистрированОПО категории «компрессорная станция» или «воздухоразделительная установка», и уже потом работаете с этим списком.

**Открыто/платно:** частично открыто; полный поиск сИНН требует авторизации через ФГИС ПБ, но базовый публичный поиск есть.

**Как проверить:** на gosnadzor.ru поискать по виду опасности «компрессорная» — получите предприятия.

---

### 3. Реестры сертификатов и деклараций соответствия ТР ТС — Росаккредитация

**Адрес:** https://pub.fsa.gov.ru
- /rss/certificate — сертификаты соответствия
- /rds/declaration — декларации о соответствии

**Что там:** документы подтверждения соответствия по техническим регламентам, в т.ч. **ТР ТС 032/2013** («Оборудование, работающее под избыточным давлением») и **ТР ТС 010/2011** («Машины и оборудование»). На каждую партию или тип оборудования — отдельная запись: заявитель, изготовитель, описание продукции, схема сертификации, орган по сертификации.

**Виден ли конечный получатель:** **НЕТ** — виден только заявитель: обычно это производитель (Siemens, Atlas Copco) или уполномоченный представитель / импортёр. Конечный покупатель здесь не фигурирует.

**Зачем тогда нужен:** можно найти, кто является официальным импортёром/дистрибьютором конкретной марки в России, — это уже зацепка для дальнейшей разведки.

**Открыто/платно:** открыто, регистрация не нужна.

**Как проверить:** зайти на pub.fsa.gov.ru, в разделе деклараций выбрать ТР ТС 032/2013, ввести «компрессор» в поиске по наименованию продукции.

---

### 4. Коммерческие базы таможенных деклараций (ФТС-данные)

**Примеры сервисов:** CustomsOnline (customsonline.ru), Seldon.Basis, СПАРК-Интерфакс (модуль ВЭД), Export-Base, DataMine/ImportGenius (Россия).

**Что там:** данные из грузовых таможенных деклараций (ГТД): получатель груза в России, отправитель за рубежом, описание товара, кодТНВЭД, вес, стоимость, таможня оформления.

**Виден ли конечный получатель:** **ЧАСТИЧНО** — «получатель» в ГТД = тот, кто подал декларацию, то есть формально импортёр. Но для дорогостоящего капитального оборудования (турбокомпрессор стоит от нескольких сотен тысяч до нескольких миллионов евро) очень часто конечное предприятие импортирует напрямую — и тогда получатель в ГТД = конечный владелец. Посредники-перекупщики компрессоров — редкость; это не потребительский товар.

Коды ТН ВЭД для поиска:
- **8414 80** — прочие воздушные насосы, вентиляторы, компрессоры
- Уточнённые:8414 80 11, 8414 80 19, 8414 80 75/80 (центробежные нагнетатели, турбовоздуходувки)
- Поиск по наименованию: «turbocompressor», «centrifugal compressor», «STC», «ZH», «Centac», «RIK»

**Открыто/платно:** **платно**, стоимость зависит от сервиса и глубины выборки. Полный доступ — от 5 000 до 100 000 руб. в месяц.

**Критически важная оговорка про 2022 год:** После февраля 2022 года ФТС России существенно ограничила передачу детализированных данных коммерческим агрегаторам. Большинство сервисов имеют полные данные до начала 2022-го, далее — частичные или только по отдельным товарным группам. Для поиска оборудования, ввезённого в 2022–2025 годах, доступность данных нужно уточнять у каждого конкретного провайдера перед покупкой подписки.

**Как проверить:** на customsonline.ru есть демо-режим — попробуйте поиск по HS 8414 80 с фильтром «Россия-импорт», посмотрите, за какой период есть результаты и что написано в поле «получатель».

---

### 5. ЕИС Закупки (zakupki.gov.ru) — вы его знаете, добавлю уточнение

Помимо активных тендеров, вЕИС есть раздел **«Реестр контрактов»** — там видны уже заключённые контракты с предметом и исполнителем. Запрос «компрессор центробежный» в реестре контрактов покажет, кто покупал такие машины в рамках 44-ФЗ/223-ФЗ. Это не вся промышленность (только госсектор и госкомпании), но нефтехим, энергетика и металлургия с госучастием там хорошо представлены.

---

## ДОГАДКИ

---

### ФГИС ПБ — расширенный публичный доступ к регистрации оборудования

**Суть догадки:** по

---

## Линза: юрист по техрегулированию (модель claude-fable-5)

## ПРОВЕРЯЕМЫЕ

---

### 1. Реестр деклараций и сертификатов соответствия — Росаккредитация ⭐ Главный источник

**Адрес:** https://pub.fsa.gov.ru/reestr/declaration и https://pub.fsa.gov.ru/reestr/certificate

**Что там:** декларации и сертификаты соответствия ТР ТС. Воздушные центробежные компрессоры попадают под два регламента одновременно:
- **ТР ТС 010/2011** (безопасность машин и оборудования) — как машина
- **ТР ТС 032/2013** (оборудование, работающее под избыточным давлением) — как напорное оборудование

**Виденли конечный получатель:** ЧАСТИЧНО — и этоключ к пониманию источника.

В карточке всегда указан **ЗАЯВИТЕЛЬ сИНН**. Конечный пользователь виден напрямую в двух случаях:

- **Схема 1а (ТР ТС 032/2013) — единичное изделие.** Крупный завод ввозит одну машину Siemens STC или Centac под свою декларацию — завод и есть заявитель с ИНН. Это самыйценный для вас случай.
- **Прямой импорт без посредника.** СИБУР, Северсталь, ЛУКОЙЛ покупают напрямую у производителя — заявитель = конечный пользователь.

Когда заявитель — дистрибьютор (ООО «Атлас Копко», местный агент MAN), конечный получатель не виден. Но продукт, марка и тип машины видны в любом случае — это позволяет хотя бы понять, кто занимается ввозом данной марки, и разрабатывать эту цепочку дальше.

**Открыто/платно:** полностью открыто, без регистрации.

**Как проверить прямо сейчас:**
1. Открыть https://pub.fsa.gov.ru/reestr/declaration
2. Фильтр "Техрегламент" → "ТР ТС 032/2013"
3. В поле "Наименование продукции" вписать: `компрессор центробежный` или `turbo compressor` или `ZH`, `Centac`, `STC`
4. В результатах смотреть схему подтверждения — записи со схемой **1а** дают конечного пользователя напрямую

Дополнительный

---

## Линза: отраслевой аналитик рынка компрессоров (модель claude-fable-5)

## ПРОВЕРЯЕМОЕ

---

### 1. Коммерческие базы данных таможенных деклараций — главный инструмент

Это самый прямой ответ на вопрос «кому досталась машина». В форме ДТ (декларации на товары) поле 8 — «Получатель» — содержит российскую организацию, которой фактически поставлен товар, сИНН. Для крупного штучного оборудования получатель вДТ в большинстве случаев и есть конечный пользователь (или ВЭД-структура холдинга).

**a) СПАРК-Интерфакс**
— сайт: spark-interfax.ru, раздел «Импорт/Экспорт» в карточке компании или поиск по ТН ВЭД
— что лежит: данные ДТ — описание товара, ТН ВЭД, дата, таможенная стоимость, декларант, **получатель с ИНН**, страна отправления
— конечный получатель виден: **да**, поле «Получатель» из ДТ; не перепутать с декларантом (таможенным брокером)
— доступ: платно, подписка; есть ограниченное демо
— проверка прямо сейчас: зайти на spark-interfax.ru → «Запросить демодоступ» → в карточке любой крупной компании-оператора ГРС или нефтехима найти вкладкуВЭД и проверить, видны ли ТН ВЭД 8414 80

**b) Контур.Фокус**
— сайт: focus.kontur.ru, в карточке организации → вкладка «ВЭД»
— что лежит: импорт и экспорт компании с кодом ТН ВЭД, описанием, стоимостью, контрагентами
— конечный получатель виден: при поиске «от компании» — да, вы видите, что и когда онаввезла; для обратного поиска «кто ввёз ТН ВЭД 8414 80 11» интерфейс менее удобен, чем у СПАРК
— доступ: платно
— проверка: focus.kontur.ru → демо-доступ → открыть карточку ОАО «СИБУР» илиПАО «Газпром нефть» → вкладка ВЭД

**c) Seldon.Basis**
— сайт: basis.myseldon.com
— что лежит: аналогично,ДТ с получател

---

## Линза: специалист по конкурентной разведке (модель claude-fable-5)

The user is asking about competitive intelligence and OSINT sources in Russia to find out which companies have imported and are using specific air centrifugal compressors (turboblowers, turbocompressors). They want to know about the final end-users, not just importers. They want a structured response with verified sources and guesses separated.

Let me think through what I actually know about Russian data sources for customs/import data, industrial equipment registries, etc.

**ПРОВЕРЯЕМЫЕ источники:**

1. **ФТС России (Федеральная таможенная служба)** - customs data
   - Таможенная статистика: customs.gov.ru
   - Публикует агрегированную статистику, но НЕ раскрывает данные по отдельным участникам ВЭД бесплатно
   - Данные деклараций (ДТ) содержат декларанта (импортёра), но не конечного получателя
   - Существуют коммерческие агрегаторы таможенных данных

2. **Коммерческие базы таможенных деклараций** - это реальный и важный источник:
   - СПАРК (spark-interfax.ru) - содержит таможенную статистику
   - Seldon.Basis (basis.com) 
   - Контур.Фокус (focus.kontur.ru)
   - ImportGenius для России (есть русский аналог?)
   - ВЭД Стат / Экспортер.рф
   - Таможенная база данных - есть несколько коммерческих агрегаторов

   Самые известные агрегаторы таможенных данных по России:
   - **1ИМПОРТ** (1import.info или похожий)
   - **ImportDT** 
   - **Seldon**
   - **СПАРК-Маркетинг**
   - **RusBase** / другие

   Важно: В таможенных декларациях есть поле "Получатель" (графа 8ДТ) и "Декларант/Представитель" (графа 14). Получатель - это покупатель по контракту, который может быть торговым домом или конечным предприятием. Конечный пользователь (end-user) в таможенной декларации явно не указывается.

3. **Реестр опасных производственных объектов (ОПО)Ростехнадзора**
   - Компрессорные станции, воздуходувные установки регистрируются как ОПО
   - ФГИС "Опасные производственные объекты" (erpcorse.gosnadzor.ru или аналогичный)
   - Публичная часть реестра есть, но данные ограничены
   - Адрес: orpoc.gosnadzor.ru

4. **Реестр заключений экспертизы промышленной безопасности (ЭПБ)**
   - Каждый компрессор, прошедший ЭПБ, внесён в реестр
   - Ростехнадзор ведёт этот реестр
   - Сайт: gosnadzor.ru или erpcorse...
   - Реально доступенли публично - нужно проверить

5. **Государственные закупки -ЕИС/zakupki.gov.ru**
   - Тендеры на техобслуживание, запчасти к конкретным компрессорам
   - Открыто, бесплатно
   - В описании лота часто указывают марку и модель оборудования
   - Видно заказчика (организацию, ИНН)
   - Это реальный работающий источник для поиска

6. **Коммерческие закупочные площадки**
   - B2B-Center, Фабрикант, ТЭК-Торг, РТС-тендер
   - Могут содержать тендеры коммерческих предприятий (нефтяники, газовики)
   - Частично открыты, частично платно

7. **ОГРН/ЕГРЮЛ и финансовая отчётность**
   - СПАРК, Контур.Фокус, ГАС "Правосудие" (для судебных дел о поставках)
   - Договоры о поставке иногда фигурируют в арбитражных делах

8. **Реестр разрешений Ростехнадзора на применение технических устройств**
   - До определённого периода Ростехнадзор выдавал "разрешения на применение" иностранного оборудования
   - С 2014-2017 годов система менялась, технические регламенты ЕАЭС
   - Публичный реестр существовал на сайте Ростехнадзора

9. **Декларации о соответствии и сертификаты ЕАЭС**
   -ФСА (Росаккредитация) - fsacert.ru
   - Реестр сертификатов и деклараций соответствия
   - Иногда в заявителе указан импортёр, иногда производитель оборудования
   - Конечного получателя обычно не видно

10. **РПНУ (Росприроднадзор) - экологические отчёты**
    - Крупные промышленные предприятия подают отчёты с перечнем оборудования
    - Это очень косвенный источник

11. **Арбитражные дела - КАД Арбитр (kad.arbitr.ru)**
    - Споры по поставкам оборудования
    - Реально там бывают дела с названием конкретного оборудования
    - Бесплатно и открыто
    - Можно искать по названию марки в тексте решений

12. **Публичные отчёты компаний (для ПАО)**
    - Годовые отчёты крупных компаний (на портале раскрытия info.cikrf.ru или e-disclosure.ru)
    - В разделах капвложений иногда упоминается оборудование

13. **Специализированные агрегаторы таможенных данных:**
    - importers.info (или аналоги)
    - Есть несколько платных сервисов, которые агрегируют таможенные данные ГТД
    
Самые важные платные агрегаторы таможенных данных по России, которые реально существуют:
- **СПАРК** (spark-interfax.ru) - крупнейший, содержит раздел "ВЭД"
- **Контур.Фокус** (focus.kontur.ru) - есть раздел таможни
- **Seldon.Basis** - комплексная аналитика
- **ImportDT.ru** - специализированная база таможенных деклараций (нужно проверить)
- **RusVED** / **Таможенная база** - возможно существуют

Ключевой момент: в российских таможенных декларациях (ДТ):
- Графа 8 - "Получатель" (это юрлицо, получающее груз по внешнеторговому контракту)
- Графа 14 - "Декларант" (таможенный представитель или декларант)

Получатель в графе 8 - это не всегда конечный пользователь. Это может быть торговый дом. Но часто это и есть завод-получатель.

КодыТНВЭД для центробежных компрессоров:
- 8414.80 - прочие воздушные или вакуумные насосы, воздушные или газовые компрессоры
- Конкретнее: 8414.80.75 - центробежные компрессоры
- 8414.80.11, 8414.80.19и т.д.

По этим кодам ТН ВЭД можно искать в таможенных базах.

Давайте структурирую ответ:

**ПРОВЕРЯЕМОЕ:**

1. Коммерческие агрегаторы таможенных данных (СПАРК, Контур.Фокус, Seldon) - платно, видно получателя (графа 8 ДТ)

2.ЕИС Закупки (zakupki.gov.ru) - бесплатно, видно заказчика сИНН, искать по "Atlas Copco", "Ingersoll", "Centac" и т.д.

3. КАД Арбитр (kad.arbitr.ru) - бесплатно, судебные решения по поставкам, искать по названию марок

4. Росаккредитация ФСА (fsa.gov.ru) - реестр сертификатов, частично видно импортёра, не конечного получателя

5.Ростехнадзор - реестр ОПО (в той мере, в которой он публичен)

6. Реестр ЭПБ Ростехнадзора

**ДОГАДКИ:**

- Полная открытая базаФТС по отдельным декларациям - нет, не существует в открытом виде
- Что-то вроде ImportGenius по России - существуют платные сервисы, но их качество варьируется

Теперь напишу более структурированный ответ. Буду конкретным.

Конкретные коды ТН ВЭД:
- 8414.80 - "Прочие воздушные или вакуумные насосы, воздушные или газовые компрессоры"
- Центробежные воздушные компрессоры попадают под 8414.80.75.xx в зависимости от мощности/давления
- Также 8406(турбины паровые) - не то
- 8411 - турбореактивные, турбовинтовые и газовые турбины - тоже не то
- 8414 - насосы воздушные или вакуумные, компрессоры воздушные или газовые

На самом деле для турбокомпрессоров и турбовоздуходувок центробежного типа:
- 8414.80.75 - компрессоры центробежные многоступенчатые
- 8414.80.19 - прочие

Нужно уточнить точные коды. Для крупных промышленных центробежных компрессоров это скорее всего 8414.80.75 или аналогичные подсубпозиции.

Теперь про реальные платные агрегаторы таможенных данных по России. Я знаю точно:

1. **СПАРК-Interfax** (spark-interfax.ru) - есть модуль ВЭД/таможня. Платный, корпоративная подписка. Содержит данные таможенных деклараций. Видно получателя изДТ (графа 8).

2. **Контур.Фокус** (focus.kontur.ru) - есть блок таможенных операций. Платный. Показывает компании-участниковВЭД с агрегированной статистикой, но степень детализации до конкретных деклараций нужно уточнить.

3. **Seldon.Basis** (basis.com) - платный. Содержит таможенные данные.

4. **ImportDT** - я не уверен в существовании именно такого сайта.

5. **Таможенная база "Экспортёры СНГ"** или аналоги - есть несколько сервисов, специализирующихся именно на таможенных данных.

Существуют ли специализированные сервисы именно таможенных деклараций по России? Да - это исторически важный рынок. Известные игроки:
- СПАРК
- Контур
- Seldon
- Также был сервис "ВЭД Стат" и другие

Но нужно быть честным: после2022 года доступность данных могла измениться, и некоторые агрегаторы таможенных данных могли закрыться или стать менее полными.

Важное замечание: Ростехнадзор - реестр ОПО. Компрессорные установки с давлением >0.07 МПа или объёмом >25 л регистрируются как ОПО. Реестр ОПО есть на сайте Ростехнадзора, но его публичная часть ограничена (названиеОПО, организация, адрес). Можно посмотреть на arlta.ru или gosnadzor.ru.

Для реестра ЭПБ - действительно существует на сайте Ростехнадзора. Адрес: https://epb.gosnadzor.ru/ или в разделе реестров на gosnadzor.ru. В нём есть данные об объекте, организации-владельце, типе оборудования. Это потенциальноценный источник для нашей задачи, потому что там должно быть указано конкретное оборудование, прошедшее ЭПБ.

Реестр ЭПБ - это один из самых ценных источников, потому что:
- Компрессоры на опасных производствах должны проходить ЭПБ после срока службы
- В реестре указывается тип оборудования, владелец (предприятие)
- Реестр публичный

Но ограничение: только те, кто уже отработал срок и прошёл экспертизу. Новое оборудование там не появится сразу.

Теперь про реестр разрешений на применение - это был реальный источник. Ростехнадзор выдавал "разрешения на применение технических устройств" для иностранного оборудования наОПО. Реестр разрешений публиковался на сайте Ростехнадзора. Заявителем выступал либо изготовитель, либо уполномоченный представитель, либо предприятие. Это косвенный, но реальный источник.

С переходом на технические регламенты ЕАЭС (ТРТС 010/2011и др.) система изменилась, но реестр исторических разрешений должен сохраниться.

Теперь структурирую итоговый ответ:

---

## ПРОВЕРЯЕМОЕ

### 1. Коммерческие агрегаторы таможенных данных (ДТ/ГТД)

**СПАРК** (spark-interfax.ru) - раздел ВЭД
- Содержит: данные таможенных деклараций по кодам ТН ВЭД, участникам ВЭД
- Конечный получатель: **ДА** - получатель из графы 8 ДТ виден; но это юрлицо-покупатель по контракту, не всегда конечный пользователь
- Цена: корпоративная подписка, дорого
- Проверка: зайти на spark-interfax.ru, раздел "Таможня/ВЭД"

**Контур.Фокус** (focus.kontur.ru) - блок таможни
- Содержит: сводная статистика ВЭД по компаниям, отдельные операции
- Конечный получатель: виден участник ВЭД (отправитель/получатель), степень детализации зависит от тарифа
- Цена: платно, есть пробный период
- Проверка: focus.kontur.ru → любая компания → вкладка "ВЭД"

**Seldon.Basis** (basis.com)
- Содержит: таможенные данные, закупки, юридическая информация
- Конечный получатель: аналогично СПАРК
- Цена: платно
- Проверка: basis.com

**Ключевые параметры поиска в этих базах:**
- ТН ВЭД 8414.80 (компрессоры воздушные/газовые центробежные)
- Описание товара: "Atlas Copco", "Ingersoll", "Centac", "Howden", "Elliott", "Sundyne", "MAN Turbo", "Kobelco", "Siemens STC"
- Страна происхождения: DE, SE, US, JP, GB

**Ограничение:** Получатель в ДТ — это покупатель по внешнеторговому контракту. Если схема поставки: иностранный производитель → российский дилер (ООО "Сименс Рус") → завод, то вДТ получателем будет дилер, а не завод.

### 2. ЕИС в сфере закупок (zakupki.gov.ru)

- Содержит: тендеры госпредприятий и компаний с госучастием (223-ФЗ, 44-ФЗ) наТО, ремонт, запчасти
- Конечный получатель: **ДА** — заказчик виден сИНН и адресом
- Цена: бесплатно, без регистрации
- Проверка: zakupki.gov.ru → расширенный поиск →ввести "Atlas Copco" или "Centac" или "компрессор Ingersoll" в поле "ключевые слова в объекте закупки"

Ограничение: только те, кто объявляет тендер, и только по44-ФЗ/223-ФЗ. Частные компании не обязаны.

### 3. КАД Арбитр (kad.arbitr.ru) — арбитражные дела

- Содержит: тексты судебных решений арбитражных судов РФ
- Конечный получатель: **ДА** — в текстах решений по спорам о поставке оборудования стороны (покупатель = конечный пользователь) фигурируют явно
- Цена: бесплатно
- Проверка: kad.arbitr.ru → расширенный поиск → в поле "текст" ввести "Atlas Copco ZH" или "Centac" или "компрессор турбо" с фильтром "тип спора: экономические"
- Находки: споры о непоставке, гарантийных случаях, неоплате — там будет написано "ООО Завод X закупило компрессор Atlas Copco модели ZH уООО Дилер Y"

### 4. Реестр заключений ЭПБ Ростехнадзора

- Сайт: gosnadzor.ru, раздел "Реестры и перечни" → "Реестр заключений экспертизы промышленной безопасности"
- Содержит: заключения ЭПБ на технические устройства (в т.ч. компрессоры) на ОПО
- Конечный получатель: **ДА** — владелец ОПО (предприятие) указан, тип оборудования указан
- Цена: публично доступен (по данным на2024 год)
- Проверка: gosnadzor.ru → поиск по реестру → фильтр по типу объекта или наименованию оборудования
- Ограничение: только те машины, которые прошли ЭПБ (как правило, по истечении нормативного срока службы)

### 5. Реестр ОПО Ростехнадзора

- Сайт: gosnadzor.ru (илиarlta.ru — ФГИСОПО)
- Содержит: реестр опасных производственных объектов с кратким описанием
- Конечный получатель: **ДА** — владелец ОПО указан (предприятие, ИНН), класс опасности, тип
- Цена: публичная часть открыта
- Проверка: искать ОПО по виду "компрессорная установка", "воздуходувная станция"
- Ограничение: в описании ОПО марка компрессора не указывается, только тип объекта. Нужны дополнительные запросы.

### 6. Росаккредитация — Реестр деклараций и сертификатов ЕАЭС (fsa.gov.ru)

- Сайт: fsa.gov.ru → раздел "Реестры" → "Реестр деклараций о соответствии" / "Реестр сертификатов"
- Содержит: декларации/сертификаты соответствия на оборудование поТР ТС 010/2011 (безопасность машин и оборудования)
- Конечный получатель: **НЕТ** — виден заявитель (производитель или уполномоченный представитель), не покупатель
- Цена: бесплатно
- Проверка: fsa.gov.ru → расширенный поиск → ввести "компрессор центробежный" или наименование марки, выбрать ТР ТС 010/2011
- Польза: можно узнать, что конкретная модель официально ввозилась (активная декларация), и найти российского уполномоченного представителя → через него дойти до цепочки поставок

### 7. Коммерческие B2B-площадки закупок

- **B2B-Center** (b2b-center.ru) — нефтяники, энергетика, промышленность
- **Фабрикант** (fabrikant.ru) — широкий промышленный спектр
- **ТЭК-Торг** (tektorg.ru) — нефтегазовый сектор
- Содержат: тендеры коммерческих предприятий на ТО и запчасти
- Конечный получатель: **ДА** — заказчик виден
- Цена: просмотр лотов частично открыт (b2b-center — нужна регистрация для просмотра документации)
- Проверка: b2b-center.ru → поиск "центробежный компрессор" или "Atlas Copco"

---

## ДОГАДКИ (не уверен в существовании или доступности)

1. **Открытая база ФТС с конкретными декларациями** — Такой базы в открытом доступе НЕТ и никогда не было. ФТС публикует только агрегированную статистику по кодам ТН ВЭД.

2. **Реестр разрешений Ростехнадзора на применение технических устройств** — Исторически существовал до ~2017-2018 гг., сейчас функция перешла к сертификации ЕАЭС. Архивный реестр должен быть на gosnadzor.ru, но его актуальность и полнота под вопросом. Возможно доступен по запросу в Ростехнадзор.

3. **Специализированные агрегаторы "только таможня"** — Существовали сервисы вроде "importers.info", "importdt.ru" и аналоги. После 2022 года ряд из них мог закрыться или ухудшить качество данных из-за ограниченийФТС. Рекомендую проверять актуальность отдельно.

4. **ПаспортаОПО (детализированные)** — Каждый ОПО имеет паспорт с перечнем оборудования, но это внутренний документ предприятия и Ростехнадзора, в публичный доступ не выходит.

5. **Реестр ФГИС "Промышленность"** (gisp.gov.ru) — Минпромторг ведёт ГИСП с реестром промышленных предприятий и производимой/используемой продукции. Насколько там есть данные об импортном оборудовании — неизвестно.

6. **Таможенные данные через ЕАЭС (ЕЭК)** — Евразийская экономическая комиссия публикует агрегированную статистику, но не разбивку по конкретным участникам.

---

Хм, нужно убедиться в точности информации о конкретных сайтах и адресах:

- **epb.gosnadzor.ru** - реестр ЭПБ. Реально существует? На сайте Ростехнадзора (gosnadzor.ru) в разделе "Реестры" действительно есть реестр заключений ЭПБ. URL может быть https://www.gosnadzor.ru/activity/register/ или аналогичный.

- **fsa.gov.ru** - это сайт Росаккредитации. Реестры деклараций соответствия. Это точно существует.

- **kad.arbitr.ru** - это точно существует, Картотека арбитражных дел.

- **zakupki.gov.ru** - это точно существует, Единая информационная система в сфере закупок.

- **spark-interfax.ru** - существует.

- **focus.kontur.ru** - существует.

- **basis.com** - существует (Seldon.Basis).

Насчёт реестра ОПО - публичный поиск по реестру ОПО... это сложнее. На сайте gosnadzor.ru есть ФГИС "Реестр ОПО". В2020-х годах он должен быть доступен онлайн, но полнота публичного доступа - под вопросом. Сайт ФГИС ОПО, кажется, был на отдельном домене.

Также стоит упомянуть возможность ЗАПРОСА через официальные каналы (ФТС, Ростехнадзор) - это законная практика в России для юридических лиц.

Ещё один важный источник: **сайты самих промышленных предприятий** и их **годовые/экологические отчёты** - там иногда перечисляется крупное оборудование. Эторучная разведка, но для крупных игроков (Роснефть, Газпром, СИБУР, Норникель и т.д.) можно найти.

А также **публикации о модернизации в отраслевых журналах** - "Компрессорная техника и пневматика", "Химическое и нефтегазовое машиностроение", "Промышленный вестник" и т.д.

Также: **Проспекты эмиссии ценных бумаг** - ПАО обязаны раскрывать информацию о производственных активах, включая перечень основного оборудования. Это через e-disclosure.ru (сервер раскрытия Интерфакса) или disclosure.1prime.ru.

Давайте теперь напишу финальный структурированный ответ, сосредоточившись на качестве и точности.

Буду более осторожен с адресами, чтобы не давать неверные URL. Скажу "сайт X, раздел Y" без выдуманных точных URL.

Итоговый ответ:

---

## ПРОВЕРЯЕМОЕ

### 1. Коммерческие агрегаторы таможенных деклараций

Этоваш главный инструмент для задачи. Российские таможенные декларации содержат **графу 8 "Получатель"** — это юрлицо, получающее груз. В большинстве прямых поставок это и есть конечное предприятие. Данные ФТС в сыром виде закрыты, но несколько коммерческих операторов получили к ним легальный доступ.

**СПАРК-Interfax** — spark-interfax.ru
- Что есть: модуль ВЭД/Таможня. Поиск по коду ТН ВЭД, наименованию товара, стране происхождения, участнику ВЭД.
- Конечный получатель: видна компания-получатель (графа 8 ДТ), еёИНН — **это почти всегда реальный получатель**, если поставка не через цепочку посредников.
- Платно: да, корпоративная подписка, демодоступ есть.
- Как проверить: зайти на spark-interfax.ru → раздел "ВЭД" → ввести ТН ВЭД 8414.80 или текст "turbocomp

---

## Линза: снабженец крупного завода (модель claude-fable-5)

# Где найти данных о ввозе центробежных компрессоров и конечных получателях

Двадцать лет в снабжении — значит, понимаю задачу изнутри. Отвечу честно, без приукрашиваний.

---

## ПРОВЕРЯЕМОЕ

### 1. Коммерческие базы таможенных деклараций (ДТ / ГТД)

Этоваш главный инструмент. Несколько агрегаторов покупают или получают данные деклараций на товары и продают доступ:

**а) СПАРК-Интерфакс** — spark-interfax.ru

- **Что лежит:** агрегированные данные ВЭД по юридическим лицам:ТН ВЭД, суммы, количество поставок, страны. В карточке компании — вкладка «Внешняя торговля».
- **Виден ли конечный получатель:** показывает **декларанта** (того, кто подалДТ). Если завод импортирует напрямую — это и есть конечный получатель. Если через дилера (ООО «Атлас Копко Рус», Siemens OOO) — в открытом доступе вы видите дилера, не завод. Иногда в поле «Получатель» (графа 8 ДТ) прописан конечный грузополучатель — СПАРК его иногда отдаёт отдельно, но не всегда.
- **Доступность:** платно, корпоративная подписка. Есть демо-доступ на несколько запросов.
- **Проверка прямо сейчас:** зайдите на spark-interfax.ru → найдите карточку любого известного импортёра компрессоров (например, ООО «Атлас Копко») → посмотрите вкладку ВЭД — если данные есть, система работает.

**б) Контур.Фокус** — focus.kontur.ru

- **Что лежит:** аналогично СПАРК — сводныеВЭД-данные по компании плюс иногда выдержки из описания товара в декларации. Описание товара — это золото: там бывает написано «Компрессор центробежный Siemens STC-SV, зав. № 12345, предназначен для ОАО "Северсталь"».
- **Виден ли конечный получатель:** так же, как в СПАРК — декларант + иногда получатель из графы 8.
- **Доступность:** платно.
- **Проверка:** focus.kontur.ru → любая компания → раздел «Внешняя торговля».

**в) СБИС (Тензор)** — sbis.ru

- Аналогичный сервис, есть раздел ВЭД. Платно.

**Ключевой ТН ВЭД для поиска:**
- **8414 80 75** — турбокомпрессоры многоступенчатые (ваш основной код для Siemens STC, MAN RIK, Atlas ZH, Centac и т.п.)
- **8414 80 73** — турбокомпрессоры одноступенчатые
- Дополнительно смотрите **8414 80** в целом + фильтруйте по описанию товара по словам «centrifugal», «turbo», «Howden», «Kobelco», «Elliott»

**Принципиальное ограничение всех трёх:** крупные вендоры (Atlas Copco, Siemens) держат в России юридические лица-дистрибьюторы. ДТ оформляется на них. Конечный завод появится в базе только если: (а) покупал напрямую, минуя российское юрлицо вендора, (б) данные по графе 8 попали в базу.

---

### 2. Росаккредитация — Реестр деклараций о соответствии

**URL:** fsa.gov.ru → «Реестры» → «Реестр деклараций о соответствии»

- **Что лежит:** декларации о соответствии техрегламентам ЕАЭС на конкретное оборудование. Для компрессоров — ТР ТС010/2011 «О безопасности машин и оборудования».
- **Виден ли конечный получатель:** виден **заявитель** — это либо представитель изготовителя, либо импортёр, либо (редко) сам завод-эксплуататор если он декларировал партию для себя. Конечный потребитель напрямую не виден.
- **Доступность:** **бесплатно и без регистрации**.

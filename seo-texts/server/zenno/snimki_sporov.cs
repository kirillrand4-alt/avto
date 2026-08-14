// Кубик ZennoPoster 7.9: СНИМКИ спорных мест на живых сайтах.
//
// Зачем. Судья ролей размечает адрес по куску страницы, мы — правилами; на 1486
// адресах согласие 83,5%, и 245 споров надо разбирать глазами. Открывать каждый
// сайт руками — часы. Кубик открывает сам и снимает ровно то место, где стоит
// адрес.
//
// Почему не из песочницы Claude: там Chromium наружу не ходит (агентский прокси
// рвёт CONNECT, ERR_CONNECTION_RESET, при том что curl через тот же прокси даёт
// 200). Браузер есть здесь — этот и снимает.
//
// API взят рефлексией по ZennoLab.CommandCenter.dll, а не по памяти:
//   HtmlElement.DrawAsBitmap(bool isImage, string hash) -> Bitmap
//   HtmlElement.ScrollIntoView(), HtmlElement.ParentElement
//   Tab.FindElementByXPath(string xpath, int number)
//
// ОБМЕН (папка C:\seostat\drop\zenno):
//   snimki_zadanie.txt — строки «id;url;адрес», наполняет spory_snimki.py
//   snimki\<id>.png    — что сняли
//   snimki_itog.txt    — «id;ok» или «id;причина» построчно
//
// Настройки проекта (необязательны): snimkov_za_raz (по умолчанию 40).

var papka = @"C:\seostat\drop\zenno";
var fajl_zadaniya = System.IO.Path.Combine(papka, "snimki_zadanie.txt");
var papka_snimkov = System.IO.Path.Combine(papka, "snimki");
var fajl_itoga = System.IO.Path.Combine(papka, "snimki_itog.txt");
System.IO.Directory.CreateDirectory(papka_snimkov);
var bez_bom = new System.Text.UTF8Encoding(false);

Func<string, string, string> nastroyka = delegate(string imya, string po_umolchaniyu)
{
    try
    {
        string z = project.Variables[imya].Value;
        if (!string.IsNullOrEmpty(z)) return z;
    }
    catch { }
    return po_umolchaniyu;
};

int za_raz = 40;
if (!int.TryParse(nastroyka("snimkov_za_raz", "40"), out za_raz) || za_raz <= 0) za_raz = 40;

// прокси берём те же, что у обхода: сайты, закрытые от датацентра, закрыты и здесь
var proxy_spisok = new List<string>();
try
{
    string pp = System.IO.Path.Combine(papka, "proxy.txt");
    if (System.IO.File.Exists(pp))
        foreach (string s in System.IO.File.ReadAllLines(pp))
            if (s.Trim().Length > 0 && !s.Trim().StartsWith("#")) proxy_spisok.Add(s.Trim());
}
catch { }
var sluchay = new Random(Environment.TickCount ^ System.Threading.Thread.CurrentThread.ManagedThreadId);

// Экономим на том же, на чём обход: картинки страницы нам нужны (это снимок!),
// а вот шрифты, медиа и счётчики — нет.
try
{
    var maski = new List<string> {
        @"\.(?:mp4|webm|avi|mov|mp3|wav|ogg)(?:[?#]|$)",
        @"(?:googletagmanager|google-analytics|mc\.yandex|top-fwz1)"
    };
    foreach (var m in instance.GetType().GetMethods())
    {
        if (m.Name != "SetContentPolicy" || m.GetParameters().Length != 3) continue;
        m.Invoke(instance, new object[] { "BlockList", new List<string>(), maski });
        break;
    }
}
catch { }

// Задание разбираем ПОД ЗАМКОМ и сразу переписываем остаток: два потока иначе
// снимают одно и то же место, а это оплаченный трафик и время.
var vzyato = new List<string>();
lock (SyncObjects.ListSyncer)
{
    if (!System.IO.File.Exists(fajl_zadaniya))
    {
        project.SendInfoToLog("задания нет: " + fajl_zadaniya, true);
        return -1;
    }
    var vse = new List<string>(System.IO.File.ReadAllLines(fajl_zadaniya));
    var ostatok = new List<string>();
    foreach (string s in vse)
    {
        string t = s.Trim().TrimStart('\uFEFF');
        if (t.Length == 0) continue;
        if (vzyato.Count < za_raz) vzyato.Add(t); else ostatok.Add(t);
    }
    System.IO.File.WriteAllLines(fajl_zadaniya, ostatok.ToArray(), bez_bom);
}
if (vzyato.Count == 0)
{
    project.SendInfoToLog("задание пусто — снимать нечего", true);
    return 0;
}

Func<string, bool> godnaya = delegate(string h)
{
    return h != null && h.Length > 600;
};

// ПУСТОЙ КАДР ЛОВИМ ПО ПИКСЕЛЯМ, А НЕ ПО ВЕСУ ФАЙЛА. Первая версия считала
// белым всё, что меньше трёх килобайт, — и пропустила снимок на 4030 байт,
// который оказался таким же белым листом: большая одноцветная картинка жмётся
// в те же килобайты. Считаем небелые точки по сетке 40x40.
Func<System.Drawing.Bitmap, bool> pustoy_kadr = delegate(System.Drawing.Bitmap b)
{
    if (b == null || b.Width < 40 || b.Height < 30) return true;
    int shag_x = Math.Max(1, b.Width / 40), shag_y = Math.Max(1, b.Height / 40), tochek = 0;
    for (int x = 0; x < b.Width; x += shag_x)
    {
        for (int y = 0; y < b.Height; y += shag_y)
        {
            var c = b.GetPixel(x, y);
            // ПРОЗРАЧНАЯ ТОЧКА — ЭТО ПУСТО, А НЕ ЧЁРНОЕ. У прозрачного пикселя
            // A=0, а R/G/B нули, и проверка «темнее 235» засчитывала его как
            // содержимое: 21 белый кадр из 119 прошли мимо первой версии
            // (посчитано по скачанным снимкам с наложением на белый фон).
            if (c.A > 32 && (c.R < 235 || c.G < 235 || c.B < 235)) tochek++;
            if (tochek >= 12) return false;
        }
    }
    return true;
};

int snyato = 0, ne_nashli = 0, ne_otkrylos = 0;
var itogi = new List<string>();

foreach (string stroka in vzyato)
{
    var chasti = stroka.Split(';');
    if (chasti.Length < 3) continue;
    string id = chasti[0].Trim();
    string url = chasti[1].Trim();
    string adres = chasti[2].Trim();
    if (url.Length == 0 || adres.Length == 0) continue;
    if (!url.StartsWith("http")) url = "http://" + url;

    instance.ClearCookie();
    instance.ClearCache();
    if (proxy_spisok.Count > 0)
        instance.SetProxy(proxy_spisok[sluchay.Next(proxy_spisok.Count)]);

    string html = "";
    try
    {
        instance.ActiveTab.Navigate(url, "");
        instance.ActiveTab.WaitDownloading();
        var he = instance.ActiveTab.FindElementByTag("html", 0);
        if (he != null && !he.IsVoid) html = he.GetAttribute("outerhtml");
    }
    catch (Exception e)
    {
        itogi.Add(id + ";не открылась: " + e.Message.Replace(';', ',').Replace('\n', ' '));
        ne_otkrylos++;
        continue;
    }
    if (!godnaya(html))
    {
        itogi.Add(id + ";пустая страница");
        ne_otkrylos++;
        continue;
    }

    // Ищем сам адрес: сперва ссылкой mailto (там он ровно один), потом текстом.
    var el = instance.ActiveTab.FindElementByXPath(
        "//a[contains(translate(@href,'ABCDEFGHIJKLMNOPQRSTUVWXYZ'," +
        "'abcdefghijklmnopqrstuvwxyz'),'mailto:" + adres.ToLower() + "')]", 0);
    if (el == null || el.IsVoid)
        el = instance.ActiveTab.FindElementByXPath(
            "//*[contains(text(),'" + adres + "')]", 0);
    if (el == null || el.IsVoid)
    {
        itogi.Add(id + ";адреса на странице нет");
        ne_nashli++;
        continue;
    }

    // Поднимаемся к родителю, пока блок не станет читаемым куском: у самой ссылки
    // высота в одну строку, и снимок выходит полоской. Размер берём по
    // BoundingClient*: обычные Height/Width у части элементов отдают ноль, и
    // подъём обрывался на первом же шаге — снимок выходил белым (три из пяти на
    // первом прогоне 14.08, владелец показал их в Paint).
    var blok = el;
    for (int i = 0; i < 5; i++)
    {
        int v = 0, sh = 0;
        try { v = blok.BoundingClientHeight; sh = blok.BoundingClientWidth; } catch { }
        if (v <= 0 || sh <= 0)
        {
            try { v = blok.Height; sh = blok.Width; } catch { }
        }
        if (v >= 120 && sh >= 320) break;
        var roditel = blok.ParentElement;
        if (roditel == null || roditel.IsVoid) break;
        blok = roditel;
    }

    string put = System.IO.Path.Combine(papka_snimkov, id + ".png");
    // ПУСТОЙ СНИМОК — ОТДЕЛЬНЫЙ СЛУЧАЙ, а не успех: белая картинка весит меньше
    // трёх килобайт, и по этому признаку мы её и ловим. Пробуем по очереди:
    // выбранный блок -> его родитель -> тело страницы целиком.
    bool vyshlo = false;
    string prichina_sboya = "";
    for (int popytka = 0; popytka < 3 && !vyshlo; popytka++)
    {
        if (popytka == 1)
        {
            var roditel = blok.ParentElement;
            if (roditel != null && !roditel.IsVoid) blok = roditel; else continue;
        }
        else if (popytka == 2)
        {
            var telo = instance.ActiveTab.FindElementByTag("body", 0);
            if (telo != null && !telo.IsVoid) blok = telo; else break;
        }
        try { blok.ScrollIntoView(); } catch { }
        // 900 мс, а не 400: за 400 ленивая подгрузка после прокрутки не успевает,
        // и в кадр попадает ещё не отрисованная область
        System.Threading.Thread.Sleep(900);
        try
        {
            var bmp = blok.DrawAsBitmap(false, "");
            if (bmp == null) { prichina_sboya = "пустой bitmap"; continue; }
            if (pustoy_kadr(bmp))
            {
                prichina_sboya = "белый кадр " + bmp.Width.ToString() + "x" + bmp.Height.ToString();
                continue;
            }
            bmp.Save(put, System.Drawing.Imaging.ImageFormat.Png);
            vyshlo = true;
        }
        catch (Exception e)
        {
            prichina_sboya = e.Message.Replace(';', ',').Replace('\n', ' ');
        }
    }
    if (vyshlo)
    {
        itogi.Add(id + ";ok");
        snyato++;
    }
    else
    {
        itogi.Add(id + ";снимок не вышел: " + prichina_sboya);
    }
}

lock (SyncObjects.ListSyncer)
{
    var bylo = new List<string>();
    if (System.IO.File.Exists(fajl_itoga))
        bylo.AddRange(System.IO.File.ReadAllLines(fajl_itoga));
    bylo.AddRange(itogi);
    System.IO.File.WriteAllLines(fajl_itoga, bylo.ToArray(), bez_bom);
}

project.SendInfoToLog("снимков " + snyato.ToString() + ", адрес не найден " +
                      ne_nashli.ToString() + ", страница не открылась " +
                      ne_otkrylos.ToString(), true);
return snyato;

# RD CONTROL

Bitta bot: zaderjka nazorati, stavka, «доброе утро», tanaffus, jarimalar, kassa va haftalik oyliklar, Push, hisobotlar.

## Nima qiladi

- **🚨 Nazorat.** Mijoz (vositachi bot) yozsa va 20 daqiqada javob bo'lmasa, «Проёб»ga «задержка» va
  «✅ Выполнено» tugmasi boradi. Faqat ish vaqtida hisoblanadi: kechasi kelgan xabarlar sanalmaydi.
  Javob — har qanday xodim xabari, papka akkauntidan yozilgani ham (Push yuborgan xabarlar sanalmaydi).
  Xodim yozgandan keyin bot yozsa — bu mijozning yangi xabari, unga ham javob kerak.
  Ish vaqtida guruhlar har 2 soniyada tekshiriladi (akkaunt «online» qilinmaydi): bot jonli kelgan har xabar
  raqamini eslab qoladi, guruhda tushib qolgan raqam bo'lsa — faqat o'sha xabarlarni olib, tartib bilan ishlaydi.
  Xodim javobi kech topilsa — kutish javob vaqtida yopiladi (noto'g'ri «задержка» va jarima bo'lmaydi).
  Lid xabarini qayta ishlash «Проёб»ga yozishni kutmaydi: Telegram botni sekinlashtirsa ham xabarlar o'z vaqtida.
  Bir-biriga yaqin kechikkan lidlar — 40 soniya kutib (yana 10 soniyada kechikadiganlar ham), ko'pi bilan ~1 daqiqada
  bitta xabarda; keyingisi — pastga yangi xabar.
  Mijoz ketma-ket yozsa (birinchi xabaridan 5 daqiqa ichida) — zaderjka oxirgi xabaridan hisoblanadi
  (🚨 Nazorat → 🔁 Ketma-ket: 3/4/5/7/10 daqiqa yoki o'chiq).
  «Проёб»ga kim yozadi: 🤖 bot yoki 🔑 asosiy akkaunt (⚙️ → ✍️). Asosiy akkaunt guruhda anonim admin bo'lsa —
  xabarlar «Проёб» nomidan. Bunda «✅ Выполнено» tugmasi bo'lmaydi (zaderjka javob bilan o'zi yopiladi).
  Lid statusi ⚡/💊 (Клоун, Мариновка) — zaderjka emas: status qo'yilsa kutish bekor, ochiq zaderjka yopiladi.
  Xodimning `/status` buyrug'i va vositachi botning status menyusi mijoz xabari hisoblanmaydi.
  **Papkalar:** 🚨 Nazorat → 📁 Papkalar — asosiy akkauntdagi papkalar ro'yxati; ➕ — qo'shish (guruhlari o'zi
  keladi), ✅ — ochish: 👤 javob beradigan xodimlar, nazorat, o'chirish. Har papkada 🔥 lidlar soni.
- **🎬 Stavka.** Yangi chatda birinchi stavka 20 daqiqada, keyingilari ham 20 daqiqada kelishi kerak.
  Kelmasa, «ставка» deb eslatadi (eng ko'pi 3 marta). Xodimning o'z videosi ham stavka hisoblanadi.
  3 ta stavka kelsa — stavka tugaydi. Kelmasa — 3-eslatmadan keyin stavka tugaydi va keyingi xabarlar oddiy
  zaderjka hisoblanadi (vaqt chegarasi yo'q). Stavka paytida lid ham, xodim ham nima yozsa — zaderjka emas.
  Topik ma'lumoti kech kelsa ham (yangi lid aniqlanmay qolsa) — birinchi stavka videosi kelganda yoki topik
  ochilgan vaqti bilinganda stavka o'sha paytdan boshlanadi. Stavka videosi kech topilsa ham (Telegram kech bersa) —
  stavka sifatida sanaladi. (Eski versiyada «🔒 Qattiq rejim» tugmasi aslida
  stavkani o'chirardi — yangilangach stavka bir marta o'zi qayta yoqiladi.)
- **🔔 Eslatmalar** (🚨 Nazorat → 🔔), faqat xodimlarga, «Проёб»da, faqat ish vaqtida:
  - 🆕 **Yangi lid jim** — bugun kelgan yangi lidga stavkadan keyin 2 soat hech kim yozmasa (lid ham, xodim ham,
    Push ham) — har RD alohida xabar, o'sha kuni ishdagi xodimlar belgilanadi.
  - 💳 **To'lov eslatmasi** — xodim kartani yubordi (/rek /dep /cash), keyin 15 daqiqa hech kim yozmadi —
    kartani yuborgan xodim belgilanadi: «уточните у клиента оплату». Mijozga hech narsa ketmaydi.
  Vaqtlar (yoki o'chirish) — shu ekranda.
- **🌙 Kun oxiri.** Ish vaqti tugagach (23:01) javobsiz chatlar ro'yxati «Проёб»ga boradi:
  «доведите работу до конца». Ertalab ular uchun zaderjka yozilmaydi.
- **💸 Jarimalar** (🚨 Nazorat → 💸 Jarimalar). Summalarni o'zingiz yozasiz va o'zgartirasiz.
  - ⏰ **Zaderjka** — «zinapoya», masalan `0 5 10 20`: 1-si 0 $, 2-si 5 $, 3-si 10 $, 4-si va keyingilari 20 $
    (oxirgisi takrorlanadi). Har kuni noldan. 1 ta zaderjka = «задержка» → eslatma (3/5/10/15/20/30 daqiqa) → muhlat
    (3/5/10/15) → javob bo'lmasa. Bir vaqtda va keyingi 30 daqiqada kechikkan lidlar — o'sha 1 ta (5 lid ≠ 5 jarima).
    Eslatma: «⏰ Ответьте в течение 5 мин — иначе штраф 5 $ (каждому)» (summalar har xil bo'lsa — har kimniki
    alohida). Jarima: «💸 @xodim, вам штраф 10 $ за задержку (2-я за сегодня)».
  - 🕘 **Kech qolish** — necha daqiqa kech qolganiga qarab (🚨 Nazorat → 💸 Jarimalar → 🕘 → ✏️ Jadvalni
    o'zgartirish). Hozirgi jadval: 30 daq → 10 $, 40 daq → 15 $, 1 soat → 25 $, 2 soat → 50 $. Har summa o'sha
    daqiqadan boshlab (35 daq → 10 $); birinchisidan kam (masalan, 20 daq) — 0 $, faqat xabar. 15 daqiqadan kam —
    xabar ham yo'q. Jadvalni shunday yozasiz: `30-10`, `40-15`, `60-25`, `2ч-50` (har biri yangi qatorda), `0` — o'chirish.
    «🕘 @xodim, вы опоздали на 40 мин — вам штраф 15 $ (2-е опоздание за неделю)» (haftadagi nechanchisi — dushanbadan).
  - ✍️ **Qo'lda** — «Проёб»da `@xodim штраф 5` (yoki xodim xabariga javob qilib `штраф 5`).
  Bitta RD — bitta xodim (📅 Bugun kim qayerda). Tanaffusdagi xodimga jarima yo'q.
  Jarimalar o'chiq bo'lsa — «штраф» so'zi hech qayerda chiqmaydi va hech narsa sanalmaydi.
  Guruhdagi e'lon yoki qoida (masalan «bugun 10 000 kassa qilganga 20 $ бонус») jarima/bonus deb o'qilmaydi —
  faqat xodim ko'rsatilgan qisqa buyruq.
- **🧹 «Проёб»ni tozalash.** Zaderjka xabari — xodim javob berganidan 10 daqiqa keyin o'chadi; boshqa avtomat
  xabarlar (soviyotgan va jim yangi lidlar, to'lov eslatmasi, kechikish, Push tugadi, jarima ogohlantirishi,
  stavka) — 1 soatdan keyin. Vaqtni o'zingiz
  tanlaysiz: 🚨 Nazorat → 🧹 Tozalash (0 — o'chmaydi). Jarima yozilgan xabar («💸 штраф», jarimali
  kechikish) o'chmaydi. Buyruqqa javoblar va doska ham o'chmaydi; hisob botda qoladi. Botga guruhda «Xabarlarni
  o'chirish» huquqi kerak.
- **📌 Doska.** «Проёб» tepasida qadalgan «Задержки сейчас», har RD alohida: 🟢 — 15 daqiqadan ko'p kutayotgan lid
  yo'q, 🟡 — 15–19 daqiqa kutayotgani bor, 🔴 — 20+ daqiqa (zaderjka). Pul yo'q. Taxminan har 10 soniyada o'z joyida
  yangilanadi (boshqa xabarlar uni to'xtatmaydi); Telegram «kuting» desa — kutib davom etadi; doska o'chirilsa —
  qayta yozib, qadaydi. 🚨 Nazorat → 📌 Doska (yoqish / o'chirish). Botga guruhda «Xabarlarni qadash» huquqi kerak.
- **🙋 Ishga kelish.** «Проёб»ga istalgan xabari (kechki kassa hisobotidan tashqari) YOKI lidga birinchi yozuvi —
  ishga keldi (qaysi biri oldin bo'lsa). 15+ daqiqa kech kelsa «Проёб»ga:
  «🕘 @xodim, вы опоздали на 25 мин …» (tagida mayda: «начало в 10:25 · по графику 10:00»).
  Ish boshlanib 15 daqiqada hali ko'rinmaganlarga eslatma boradi; dam olayotganlar belgilanmaydi.
- **☕ Tanaffus.** «атайду», «отойду 30», «перерыв», «obedga», «perekur» va h.k. (o'z so'zlaringizni ham qo'shasiz:
  ⚙️ → ☕ Tanaffus → ➕ Boshlash so'zlari / ➕ Qaytish so'zlari) — bot javob beradi: «☕ @xodim — перерыв до 14:30». Zaderjka xabarida:
  «☕ Baxa на перерыве до 14:30». Tanaffus vaqtida lidga yozsa — tanaffus davom etadi; vaqt tugagach lidga yoki
  «Проёб»ga yozsa — qaytdi; «тут» / «keldim» — istalgan payt qaytdi (bot 👍 bosadi). Vaqt tugab 3 daqiqa
  hech qayerga yozmasa — «☕ перерыв · @xodim — время перерыва вышло!» (tanaffus oxirida lidga yozib turgan bo'lsa —
  eslatma yo'q, u allaqachon ishlayapti).
  Xodim tanaffusda bo'lsa — uning RD si bo'yicha «задержка», eslatma va jarima chiqmaydi (vaqt to'xtab turadi).
  Qaytgach 8 daqiqa beriladi (⚙️ → ☕ Tanaffus → ⚡): tanaffusda kutib qolgan chatlar shunda ham javobsiz bo'lsa —
  «⚡ @xodim, ускорьтесь — 2 чата ждут ответа» (jarimasiz). Tanaffusdan oldin chiqqan «задержка»ning eslatmasi ham
  shu vaqtgacha suriladi, keyin odatdagidek: 5 daqiqada javob bo'lmasa — jarima.
- **👥 Hozir ishda** (bosh menyu). Har 3 soniyada o'zi yangilanadi. Har xodim: 🟢 ishda · ☕ tanaffus (qachongacha) ·
  ⚪ hali kelmagan · 🛌 dam olishda; ⏱ uning RD sida javob kutayotgan lidlar (🔴 — zaderjka); ✍️ lidga oxirgi
  yozgani; 🚨 bugungi «задержка»lar.
- **📅 Bugun kim qayerda** (bosh menyu yoki 👥 Xodimlar). Har RD da bugun bitta xodim. «🛌 Kim ishlamaydi» (shu kunga) va
  bo'sh qolgan RD ga boshqa xodimni qo'yish. Belgilash, jarima, eslatmalar shu ro'yxat
  bo'yicha. Bo'sh qolgan RD menyudagi «📅 Bugun kim qayerda» tugmasida ❗ bilan ko'rinadi.
- **🏆 Haftalik ball** (👥 Xodimlar → 🏆). Har xodimga 0–100: ⚡ tezlik · 🚨 zaderjka · 💳 karta · 🕘 intizom (har
  biri 25). 🔥 — ketma-ket zaderjkasiz ish kunlari, bir qator maslahat. Haftada 20 tadan kam javob — ball yo'q.
  «Проёб»da /statistika — ball bo'yicha 🥇🥈🥉; xodim o'z balini haftalik zp xabarida ko'radi. Pulga bog'lanmagan.
- **💵 Kassa.** Kassa — cheklar yig'indisi (1950 + 2600 = 4 550); zp — $ da. «Проёб»dagi cheklar, jarima, bonus, avanslar.
  - **Hisobotni botning o'ziga yozish mumkin:** tepasida ism bilan, masalan `Baxa` / `rd 19.10` / `1950` / `2600`.
    Ism bo'lmasa yoki bot tanimasa — «Kimning hisoboti?» deb so'raydi, tagida «➕ Yangi xodim» tugmasi bor
    (ism yozilgan bo'lsa — o'sha ism bilan qo'shadi, bo'lmasa — ismni so'raydi).
    Telefon raqami (`+998 90 123 45 67`, `998901234567`, `90 123 45 67`) hisobot hisoblanmaydi.
    Ism notanish bo'lsa — «➕ Yangi xodim: Baxa» tugmasi chiqadi (shunday tanishtirasiz). Jarima ham:
    `@ivan штраф 5`. Guruhda ham xuddi shunday.
  - Bosh menyuda — 💰 **Cash**: dushanbadan beri jami kassa ($, faqat egaga) va «Задержки сейчас» — har RD
    da hozir nechta zaderjka (🟢 yo'q · 🟡 bor · 🔴 ko'p). Menyu o‘z joyida yangilanadi (5 soniyada bir; tugma
    bosilgan paytda tegmaydi).
    Kassa bo'limida — cheklar yig'indisi, har birining $ i va jami, 🏆 top 3.
  - **Kassa menyusi — 6 tugma** (ishlatilish tartibida): ❓ Savollar · ✅ Kunni yopish · 📊 Hisobot ·
    🧮 Haftalik zp · 👥 Xodimlar · ⚙️ Sozlamalar. Hech qaysi funksiya o'chmagan — joyi o'zgargan:
    🗓 Oy yakuni, 🏆 Reyting, 📄 PDF — 📊 Hisobot ichida; 📋 To'lov ro'yxati — 🧮 Haftalik zp ichida;
    💲 Prays, 🤝 Ulushlar, 📜 Tarix, ⚙️ Zp hisoblash usuli — ⚙️ Sozlamalar ichida.
  - **📊 Hisobot.** Davr (bugun / kecha / hafta / oy / sana) → kassa; ichida 📅 Kunlar, 🏆 Reyting, 📄 PDF, oy
    tanlansa — 🗓 Oy yakuni. O'tgan hafta bilan solishtirish (↑ / ↓ %), kunlar → akkauntlar → cheklar.
  - **🏆 Umumiy reyting** — 📊 Hisobot → «🏆 Reyting — boshidan»: boshlang'ich (oldingi haftalar) kassa + 19.10 dan
    keyingi cheklar. Guruhda `/topall`. Boshlang'ich raqamlar: o'sha ekranda 📌.
  - **🧮 Haftalik zp** — bitta joyda 2 qadam. 1) Hafta (Du–Ya) tugagach bosasiz, bot o'tgan haftadagi foizlarni
    ko'rsatadi: «Bayzed: Bayzed 41% · Siz 14% · Artur qolgani». O'zgarmagan bo'lsa — «✅ O'zgarmadi — hisoblash».
    O'zgargan bo'lsa — ismni bosib yangi sonni yozasiz (masalan `41 14`). Yangi xodim bo'lsa, bot o'zi so'raydi.
    O'zgarish faqat shu haftadan: o'tgan haftalar buzilmaydi. 2) **📋 To'lov ro'yxati** — kimga qancha,
    «✅ To'landi». Keyingi hafta noldan.
  - **👥 Xodimlar** (kassa ichida) — shu / o'tgan hafta har xodim bir qatorda: kassa · Кол-во рд · $ · zp
    («≈» — hafta hali hisoblanmagan). Ismni bosing — xodim kartasi (jarima, bonus, cheklar, PDF).
  - **🤝 Ulushlar** (⚙️ Sozlamalar). Masalan «Baxa oyligidan 5% → Bayzed». Kim to'laydi: xodimdan ushlanadi, siz yoki Artur.
  - **✅ Kunni yopish.** Hamma hisobot tushgach bosasiz. Ro'yxatda faqat cheki bor kunlar: «⏳ 29.10 — 5 chek ·
    10 550». Yopilgan kunni faqat siz o'zgartira olasiz. Yopilgan kunga yangi hisobot kelsa, sizga xabar keladi.
  - **📜 Tarix** (⚙️ Sozlamalar). Kim, qachon, nimani o'zgartirgani (eski → yangi).
  - **🧮 Tekshiruv.** Hisobotda: Kassa = Artur + xodimlar + ulushlar + sizga ✅.
  - Zp hisoblash usuli: **tugma bilan** (odatiy) / **avtomatik** / **o'chiq** (o'zingiz hisoblaysiz).
  - Har hisobotdan keyin sizga xodimning shu kungi xulosasi keladi (eski kassa botidagidek):
    `Adam` / `Дата: 19.10` / `Касса: 17,100` / `Кол-во рд: 8` / `Касса ($): 64$`. Shu kunga yana hisobot kelsa —
    eskisi o'chadi, kunning jami bilan yangisi keladi.
  - Pul amallari (to'landi, avans, ulushlar, foizlar) — faqat siz. Adminlar cheklarni tuzatadi.
  - Xodim faqat o'z zp sini ko'radi, so'rov avval sizga keladi. Daromadingizni faqat siz ko'rasiz.
  - **👤 Xodim kabineti** (👥 Xodimlar → xodim): kassa, Кол-во рд, Kassa ($), bonus, jarimalar va zp — 🧮 hafta
    hisoblanmagan bo'lsa ham «≈ taxminiy» (foizlar yozilmagan bo'lsa ham), 📄 PDF.
  - **📅 Sana xatosi.** Hisobotda bitta chek boshqa (eski) sanada bo'lsa yoki hamma cheklar eski sanada bo'lsa —
    bot yozishdan oldin so'raydi: «1 950 — 25.10 ga yozilgan, qolgan cheklar esa 29.10. Xato emasmi?».
  - Hisobot qabul qilinsa «Проёб»da: «✅ Baxa · 29.10 · 3 чека · 8 550».
  - **💵 Faqat zp** admini (⚙️ → 👮 Adminlar): faqat jami kassa, jami zp va har xodimning kassa / $ / zp si.
    Foizlar, PDF, o'zgartirish, sizning va Arturning ulushi — ko'rinmaydi.
- **📣 Push.** Har papka o'z akkauntidan, faqat qo'lda: «🌅 Ertalabki» yoki «☀️ Kunduzgi» tugmasi (soatga
  qaramaydi — 15:00 da ham ertalabki bo'lishi mumkin).
  🌅 ertalabki — bugun gaplashmaganlar: kecha yozganlar → eskiroqlar (lidning oxirgi yozgani, yangisi oldin);
  ☀️ kunduzgi — avval bugungilar, tugasa — kecha → eskiroqlar. Har papkaga aynan siz yozgan son.
  **📚 Kutubxona:** har Push — raqam (nomini bot beradi: «№7 · 🎤 ovozli · 29.10 14:30»), mazmuni o'qilmaydi.
  Bitta raqam bitta lidga HECH QACHON ikki marta ketmaydi; boshqa raqam — ketishi mumkin (3 soat oraliq bilan).
  Tahrirlash — raqam o'sha; «🆕 Yangi Push» — yangi raqam; aynan bir xil matn/fayl — eski raqam deb taniladi.
  Tasdiqlashda: «shu Push'ni oldin olgan — N». 🧾 Natija — har raqam bo'yicha.
  🧪 Haqiqiy ta'sir (⚙️, ixtiyoriy): har 10 lidning 1 tasiga yuborilmaydi (taqqoslash uchun), o'rniga boshqasi —
  son kamaymaydi.
  Baza — 28.08.2026 dan keyin o'zi yozgan har bir lid (yangi kelgani ham, eskisi ham). Bot ularni bir marta to'liq
  tekshiradi (tugagach xabar keladi; qayta: 📣 Push → ⚙️ → 🔍 Bazani tekshirish). Sana: 📣 Push → ⚙️.
  CRM'ning o'z xabarlari («Статус: …», «Реквизиты отправлены», /rek /status buyrug'iga javob va menyusi) «lid o'zi
  yozdi» hisoblanmaydi.
  ⏹ bosilsa — Push to'xtaydi va darhol «▶️ Davom ettirish» chiqadi: faqat hali olmaganlarga, ikki marta yuborilmaydi.
  Papkaga akkaunt: 📣 Push → 📁 Papkalar → papka → 📲 Akkaunt (➕ yangisini shu yerning o'zida ulash mumkin).
  Push ketayotganda sonini o'zgartirsangiz (⚙️ → 🔢 Soni yoki papkaning o'z soni) — darhol shu son bilan davom etadi.
  «Проёб»da Push paneli (hamma ko'radi): nima ketyapti (matn / ovozli …), har RD — nechtadan nechtasi. Tugagach —
  shu xabarga javob qilib xodimlar belgilanadi («Пуш завершён … будьте на связи»), panel 5 daqiqada o'chadi.
  O'chirish: 📣 Push → ⚙️ → 👥 Guruhda panel.
  Push paytida bot yangilansa (GitHub'ga yuklasangiz) yoki qayta ishga tushsa — Push o'zi joyidan davom etadi:
  yuborilganlarga qayta yubormaydi, son o'sha. ⏹ bilan to'xtatilgani davom etmaydi.
  Telegram akkauntga «kuting» desa (FloodWait) — o'sha papka kutadi (30 daqiqagacha), ekranda «⏳ RD 9 → 12:44»,
  keyin o'zi davom etadi (sekinroq); boshqa papkalar to'xtamaydi. Kutish uzoqroq bo'lsa — papka to'xtaydi va Push
  ekranida «▶️ Davom ettirish — qolgan N ta» chiqadi: faqat yetmay qolgan papkalar o'z sonigacha yuboriladi.
- **📊 Hisobotlar.** Faqat buyruq bilan: shaxsiy chatda `/hisobot`, guruhda `/statistika` (🥇🥈🥉 bilan).
- **📊 Lid bazasi** (📊 Hisobotlar → 📊 Lid bazasi). Har RD: 📦 jami (baza sanasidan keyin o'zi yozganlar), 🆕 bugun va
  shu hafta yangi; 💬 bugun va 7 kunda yozganlar, 💤 qotib qolgan, 📉 soviyotgan; ⏱ javob kutyapti (🔴 zaderjka),
  🎬 stavkada, ⚡💊 chiqarilgan. RD ni bossangiz — qotib qolgan va soviyotgan lidlar havolalari bilan.
- **📈 Tahlil** (📊 Hisobotlar → 📈). Hammasi faqat vaqt va kim yozgani bo'yicha — matn o'qilmaydi:
  - 🕐 Soatlar — har soatda nechta lid yozdi va nechtasi zaderjkaga tushdi (bugun / 7 kun, RD bo'yicha).
  - 💤 Qotib qolgan — N kun (3) hech kim yozmagan lidlar; 📉 Soviyotgan — mijoz odatdagidan 3 barobar uzoq jim.
    Soviyotganlarni bot «Проёб»da o'zi eslatadi (har RD alohida, xodim belgilanadi). Faqat kecha va undan oldin
    kelgan lidlar — bugun kelgan yangi lid «soviyotgan» hisoblanmaydi.
  - 💳 Kartalar — xodim topikda `/rek /dep /cash` yozsa, «lidga karta ketdi». Har RD: necha marta, qaysi lidga.
  - ⚡ Tezlik → karta va 🏆 G'oliblar — javob tezligi kartaga qanday ta'sir qiladi, eng yaxshi xodimlar formulasi.
  - 📣 Push natijasi (📣 Push → 🧾) — har raqam bo'yicha: 90 daqiqada nechta lid yozdi, 24 soatda nechtasiga karta.
  - 📈 G'ayrioddiy o'zgarish — har dushanba ertalab sizga: o'tgan hafta oldingi 3 haftadan keskin farq qilgan narsalar
    (javob tezligi, zaderjka, kech qolish, karta, kassa; RD bo'yicha — yangi lidlar, karta, zaderjka).
  - Hammasini yoqish/o'chirish, kunlar va karta buyruqlari: ⚙️ Sozlamalar → 🧩 Qo'shimcha funksiyalar.
- **🛡 Akkaunt himoyasi.** Har kuni 09:00 dan keyin Push akkauntlar @SpamBot da tekshiriladi. Cheklov bo'lsa —
  o'sha akkauntdan Push to'xtaydi va sizga xabar keladi; cheklov olinsa — o'zi qaytadi.
  Akkaunt ulanmasa — aniq sababi: «Telegram serveri javob bermayapti — hech narsa qilmang, o'zi ulanadi» /
  «seans o'chgan — 🔑 Qayta kirish» / «akkaunt bloklangan — boshqa akkaunt ulang». O'chgan va bloklangan seansga bot
  qayta-qayta urinmaydi. Asosiy akkaunt 3 daqiqa, Push akkaunt 10 daqiqa ulanmasa — sizga xabar; ulansa — xabar
  o'chadi. 🔑 Qayta kirish — Push akkauntda ham (papkaga bog'langani saqlanadi).
  «🆕 Yangi lidlar» — shu kuni ochilgan topiklar (eski lid bugun yozsa, yangi hisoblanmaydi).
- **🌐 Til.** Har admin o'z tilini tanlaydi (bosh menyuning pastida). Savol va ogohlantirishlar ham har kimga
  o'z tilida boradi.
- **🧼 Toza chat.** Chatda doim bitta panel. «‹ Orqaga» — oldingi ekranga. Savol bir nechta egaga borsa —
  biringiz javob bersangiz, boshqalardagi nusxa o'chadi. Har hisobotga alohida xabar kelmaydi (guruhda 👌).
- **👥 Xodimlar.** Bot xodimni @username bo'yicha taniydi (guruh a'zolaridan ham), topikda ham, «Проёб»da ham.
  Bitta odamning 2 yozuvi bo'lsa (kassadagi «Baxa» va nazoratdagi «@baxa») — bot so'raydi, «🔗 Birlashtirish» tugmasi bilan.
  ➕ qo'shish, ⚙️ → 🗑 O'chirish (yoki 🗄 Arxiv). ⚙️ Sozlamalar → 🧹 Tozalash: kassa / xodimlar /
  Push akkauntlarni o'chirib, boshidan kiritish (prays va boshlang'ich kassa qoladi).

Bot mijoz va xodim xabarlarining matnini o'qimaydi va saqlamaydi. Faqat kim yozgani va qachon yozgani
olinadi.

## O'rnatish — yangi bot sifatida (iPhone, taxminan 30 daqiqa)

Eng yaxshi vaqt — kechasi, ish vaqtidan tashqari.

**A. Eski botlardan ma'lumot olish (ular hali ishlab turadi)**
1. Kassa botining GitHub repozitoriyasida `bot.py` ni `kassa_bot_uchun/bot.py` bilan almashtiring
   (Add file → Upload files → Commit). 1–2 daqiqa kuting.
2. Kassa botga `/export` yozing → `kassa.db` fayli keladi.
3. Eski zaderjka botida: 📈 Hisobotlar → 💾 Zaxira nusxa → `.sqlite3` fayli keladi.

**B. Yangi bot va kod**
1. @BotFather → `/newbot` → nom → username → **token**ni nusxa oling.
2. Yangi botni oching va **Start** ni bosing (shunda u sizga yoza oladi).
3. iPhone «Fayllar» ilovasida ZIP ni bosing — papka ochiladi.
4. github.com → ➕ → New repository → nom (masalan `rdcontrol`) → Private → Create.
5. «uploading an existing file» → papkadagi hamma fayllarni tanlang (`kassa_bot_uchun` dan tashqari) → Commit.

**C. Eski botlarni to'xtatish** (bir akkaunt ikki joyda ishlamasligi kerak)
- Railway → eski zaderjka servisi → Deployments → oxirgi deploy → ⋮ → Remove.
- Kassa servisi uchun ham shunday. Volume'lar o'chmaydi, ma'lumot saqlanadi.

**D. Railway**
1. New Project → Deploy from GitHub repo → yangi repozitoriyani tanlang.
2. Variables:
   - `BOT_TOKEN` — yangi token
   - `ADMIN_IDS` — sizning Telegram ID (eski servis Variables'idan oling)
   - `API_ID`, `API_HASH` — eski zaderjka servisidan nusxa oling
   - `DATA_DIR` = `/data`
   - `TZ_NAME` = `Asia/Tashkent`
3. Volume: loyiha ekranida ➕ → Volume → shu servisga → Mount path `/data`.
4. Deploy tugagach bot sizga «✅ RD CONTROL ishga tushdi» deb yozadi.

**E. Yangi botda**
1. ⚙️ Sozlamalar → 📥 Ko'chirish → eski zaderjka botining zaxira faylini yuboring (forward).
2. Yana 📥 Ko'chirish → `kassa.db` ni yuboring.
3. ⚙️ → 🔑 Asosiy akkaunt → telefon, kod (va parol) bilan kiring. Zaxira faylda bu seans bo'lmaydi.
   Push akkauntlar fayl bilan birga keladi — ularga qayta kirish shart emas.
4. Yangi botni «Проёб» guruhiga qo'shing va **admin** qiling.
5. Bosh menyuda tekshiring: 🟢 Akkaunt · 🟢 Push · 🟢 «Проёб».
6. 👥 Xodimlar: bir odam ikki marta chiqsa — uni oching → ⚙️ → 🔗 Birlashtirish.
7. 💵 Kassa → 🧮 Haftalik zp: shu hafta foizlarini bir marta kiriting.
8. Xodimlarga ayting: yangi botda **Start** ni bossin (oylik so'rash uchun).

> `ADMIN_IDS` dagi odamlar «ega» hisoblanadi va hamma narsani ko'radi, sizning daromadingizni ham.
> Boshqa adminlarni bot ichidan qo'shing: ⚙️ → 👮 Adminlar. Darajalar: 👑 ega · to'liq · faqat ko'radi ·
> 💵 faqat zp.

## Egalikni yo'qotmaslik

- **Zaxira ega.** Railway → Variables → `ADMIN_IDS` ga ikkinchi akkauntingiz ID sini vergul bilan qo'shing:
  `111111111,222222222`. Ikkalasi ham to'liq ega.
- **Botning o'zidan:** ⚙️ → 👮 Adminlar → ➕ ID bo'yicha admin → nomini bosib 👑 ega darajasiga o'tkazing.
- **🔐 Tiklash kodi:** ⚙️ → 👮 Adminlar → 🔐 Tiklash kodi → kamida 8 belgili kod yozing va qog'ozga yozib qo'ying.
  Akkauntingiz yo'qolsa — yangi akkauntdan botga `/ega KOD` yozasiz va ega bo'lasiz. Kod bir marta ishlaydi.
  Noto'g'ri urinishlar haqida egalarga xabar boradi.
- Akkaunt o'g'irlangan bo'lsa: Railway → `ADMIN_IDS` dan eski ID ni olib tashlang (ma'lumot o'chmaydi).

## Buyruqlar

- Shaxsiy chat: `/menu` — panel, `/hisobot` — bugungi hisobot, `/id` — Telegram ID.
- «Проёб» guruhi:
  - `/proyob` — shu guruhni «Проёб» qilish
  - `/statistika` — hafta xulosasi va eng yaxshilar
  - `/topweek` — shu hafta kassasi, `/toplast` — o'tgan hafta, `/topall` — shu kungacha (boshlang'ich kassa bilan)
  - `/frozen` — 💤 qotib qolgan lidlar, `/cooling` — 📉 soviyotgan lidlar (har RD alohida xabar)
  - `/clean` — 🧹 javob berilgan «задержка» xabarlarini o'chirish (javob kutayotganlari qoladi)
    (bularni faqat ega yoki admin yoza oladi)
  - `/id` — guruh ID si

Bot guruhda xabarlarni ko'rishi uchun uni guruhda admin qiling.

## 🔒 Panel qulfi

- Kod: ⚙️ Sozlamalar → 👮 Adminlar → 🔒 Qulf kodi (4–32 belgi, hamma ega akkauntlari uchun bitta). Bazada faqat
  shifrlangan izi saqlanadi.
- Bosh menyuda «🔒 Qulflash» — faqat shu akkauntdagi panel yopiladi; ikkinchi ega akkaunti ishlayveradi. Bot o'z ishini
  davom ettiradi (zaderjka, jarima, Push, «Проёб»).
- Qulf paytida shu chatda /start, tugma yoki matn — faqat «Бот сейчас не работает.». Xato kod — o'sha matn turaveradi.
- To'g'ri kodni yozsangiz — panel qaytadi va qulf paytida kelgan xabarlar (savollar, ogohlantirishlar, haftalik baza
  nusxasi) keladi. Yozgan kodingiz chatdan darhol o'chadi.
- Kodni unutsangiz: ikkinchi (ochiq) akkauntdan 🔒 Qulf kodini almashtiring.

## 🫀 Bot tirikligi

Ichki qism (zaderjka nazorati, doska, panel) 5 daqiqa qotib qolsa — sizga xabar keladi; qayta ishlasa — o'sha xabar
«✅ qayta ishlayapti» ga almashadi. Bot butunlay o'chib, keyin qayta yonsa (5 daqiqadan ko'p to'xtagan bo'lsa) —
«⚠️ Bot 14:05–14:12 orasida to'xtab turdi (7 daq)». Qisqa o'chishlar (yangi versiya yuklanganda) — xabarsiz.

## Zaxira

Har hafta sizga baza nusxasi keladi. Uni istalgan vaqtda olish mumkin: ⚙️ → 💾 Zaxira nusxa.

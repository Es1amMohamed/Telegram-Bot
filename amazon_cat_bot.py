import logging
import asyncio
import locale
from playwright.async_api import async_playwright
from langdetect import detect
from deep_translator import GoogleTranslator

from telegram import (
    InputMediaPhoto, Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)


COUNTRIES_CONFIG = {
    "Egypt": {
        "domain": "amazon.eg", "currency": "EGP", "lang": "ar", "flag": "🇪🇬", "locale": "ar-EG",
        "names": {"ar": "مصر", "en": "Egypt", "fr": "Égypte", "de": "Ägypten", "it": "Egitto", "es": "Egipto"}
    },
    "Saudi Arabia": {
        "domain": "amazon.sa", "currency": "SAR", "lang": "ar", "flag": "🇸🇦", "locale": "ar-SA",
        "names": {"ar": "السعودية", "en": "Saudi Arabia", "fr": "Arabie Saoudite", "de": "Saudi-Arabien", "it": "Arabia Saudita", "es": "Arabia Saudí"}
    },
    "Emirates": {
        "domain": "amazon.ae", "currency": "AED", "lang": "ar", "flag": "🇦🇪", "locale": "ar-AE",
        "names": {"ar": "الإمارات", "en": "UAE", "fr": "Émirats", "de": "VAE", "it": "EAU", "es": "EAU"}
    },
    "United States": {
        "domain": "amazon.com", "currency": "USD", "lang": "en", "flag": "🇺🇸", "locale": "en-US",
        "names": {"ar": "الولايات المتحدة", "en": "USA", "fr": "États-Unis", "de": "USA", "it": "USA", "es": "EE. UU."}
    },
    "Germany": {
        "domain": "amazon.de", "currency": "EUR", "lang": "de", "flag": "🇩🇪", "locale": "de-DE",
        "names": {"ar": "ألمانيا", "en": "Germany", "fr": "Allemagne", "de": "Deutschland", "it": "Germania", "es": "Alemania"}
    },
    "Italy": {
        "domain": "amazon.it", "currency": "EUR", "lang": "it", "flag": "🇮🇹", "locale": "it-IT",
        "names": {"ar": "إيطاليا", "en": "Italy", "fr": "Italie", "de": "Italien", "it": "Italia", "es": "Italia"}
    },
    "France": {
        "domain": "amazon.fr", "currency": "EUR", "lang": "fr", "flag": "🇫🇷", "locale": "fr-FR",
        "names": {"ar": "فرنسا", "en": "France", "fr": "France", "de": "Frankreich", "it": "Francia", "es": "Francia"}
    }
}

MESSAGES = {
    "ar": {
        "welcome": "مرحباً 👋 أرسل رابط منتج، أو صفحة فئة، أو أفضل المبيعات من أمازون",
        "fetching": "🔍 جاري جلب بيانات...",
        "price": "السعر الحالي",
        "old_price": "السعر الأصلي",
        "discount": "الخصم",
        "home": "الرئيسية 🏠",
        "btn_country": "🌍 تغيير الدولة",
        "btn_lang": "🌐 اللغة / Language",
        "btn_help": "❓ مساعدة",
        "help": "أرسل رابط منتج، فئة، أو أفضل مبيعات من أمازون 🛒",
        "error": "❌ حدث خطأ أثناء جلب البيانات",
        "updated": "✅ تم التحديث",
        "unavailable_extra": "المنتج غير متوفر في مخازن أمازون {country} حالياً."
    },
    "en": {
        "welcome": "Welcome 👋 Send an Amazon product, category, or best seller link",
        "fetching": "🔍 Fetching data...",
        "price": "Current Price",
        "old_price": "Original Price",
        "discount": "Discount",
        "home": "Home 🏠",
        "btn_country": "🌍 Change Country",
        "btn_lang": "🌐 Language / اللغة",
        "btn_help": "❓ Help",
        "help": "Send an Amazon product, category, or best seller link 🛒",
        "error": "❌ Error fetching data",
        "updated": "✅ Updated successfully",
        "unavailable_extra": "The product is currently not available in Amazon {country} warehouses."
    },
    "it": {
        "welcome": "Benvenuto 👋 Invia un link Amazon per prodotto, categoria o best seller",
        "fetching": "🔍 Recupero dati...",
        "price": "Prezzo attuale",
        "old_price": "Prezzo originale",
        "discount": "Sconto",
        "home": "Home 🏠",
        "btn_country": "🌍 Cambia Paese",
        "btn_lang": "🌐 Lingua / Language",
        "btn_help": "❓ Aiuto",
        "help": "Invia un link di un prodotto, categoria o best seller Amazon 🛒",
        "error": "❌ Errore nel recupero dei dati",
        "updated": "✅ Aggiornato con successo",
        "unavailable_extra": "Il prodotto non è attualmente disponibile nei magazzini Amazon {country}."
    },
    "fr": {
        "welcome": "Bienvenue 👋 Envoyez un lien Amazon pour produit, catégorie ou best seller",
        "fetching": "🔍 Récupération des données...",
        "price": "Prix actuel",
        "old_price": "Prix d'origine",
        "discount": "Remise",
        "home": "Accueil 🏠",
        "btn_country": "🌍 Changer de pays",
        "btn_lang": "🌐 Langue / Language",
        "btn_help": "❓ Aide",
        "help": "Envoyez un lien de produit, catégorie ou best seller Amazon 🛒",
        "error": "❌ Erreur lors de la récupération",
        "updated": "✅ Mis à jour avec succès",
        "unavailable_extra": "Le produit n'est pas disponible actuellement dans les entrepôts Amazon {country}."
    },
    "de": {
        "welcome": "Willkommen 👋 Amazon-Link für Produkt, Kategorie oder Bestseller senden",
        "fetching": "🔍 Produktdaten werden geladen...",
        "price": "Aktueller Preis",
        "old_price": "Originalpreis",
        "discount": "Rabatt",
        "home": "Startseite 🏠",
        "btn_country": "🌍 Land ändern",
        "btn_lang": "🌐 Sprache / Language",
        "btn_help": "❓ Hilfe",
        "help": "Senden Sie einen Amazon-Produkt-, Kategorie- oder Bestseller-Link 🛒",
        "error": "❌ Fehler beim Abrufen der Daten",
        "updated": "✅ Erfolgreich aktualisiert",
        "unavailable_extra": "Das Produkt ist derzeit nicht in den Amazon-Lagern in {country} verfügbar."
    }
}

async def parse_product_egypt(page):
    return await page.evaluate("""() => {
        const getPrice = (selector) => {
            const el = document.querySelector(selector);
            if (!el) return null;
            const text = el.innerText.replace(/[\\n\\r]/g, '').trim();
            const match = text.match(/\\d{1,3}(?:,\\d{3})*(?:\\.\\d+)?/);
            return match ? match[0] : null;
        };

        let current = getPrice('.priceToPay .a-offscreen') || 
                      getPrice('.apexPriceToPay .a-offscreen') || 
                      getPrice('#price_inside_buybox') ||
                      getPrice('.a-price-whole');

        let old = getPrice('.basisPrice .a-offscreen') || 
                  getPrice('.a-text-price .a-offscreen');

        let disc = document.querySelector('.savingsPercentage')?.innerText.trim() || 
                   document.querySelector('.reinventPriceSavingsPercentageMargin')?.innerText.trim() || "";

        return {
            title: document.querySelector("#productTitle")?.innerText.trim() || "",
            img: document.querySelector("#landingImage")?.src || document.querySelector("#imgBlkFront")?.src || "",
            currentPrice: current ? current : "",
            oldPrice: old ? old : "",
            discount: disc
        }
    }""")

async def parse_product_saudi(page):
    return await page.evaluate("""() => {
        const getPrice = (selector) => {
            const el = document.querySelector(selector);
            if (!el) return null;
            const text = el.innerText.replace(/[\\n\\r]/g, '').trim();
            const match = text.match(/\\d{1,3}(?:,\\d{3})*(?:\\.\\d+)?/);
            return match ? match[0] : null;
        };

        const availText = document.querySelector("#availability")?.innerText.toLowerCase() || "";
        const isOut = availText.includes("غير متوفر") || availText.includes("currently unavailable");

        let current = "";
        if (!isOut) {
            current = getPrice('.priceToPay .a-offscreen') || 
                      getPrice('.apexPriceToPay .a-offscreen') || 
                      getPrice('.a-price-whole') ||
                      getPrice('#price_inside_buybox');
        }

        let old = getPrice('.basisPrice .a-offscreen') || 
                  getPrice('.a-text-price .a-offscreen');

        let disc = document.querySelector('.savingsPercentage')?.innerText.trim() || 
                   document.querySelector('.reinventPriceSavingsPercentageMargin')?.innerText.trim() || "";

        return {
            title: document.querySelector("#productTitle")?.innerText.trim() || "",
            img: document.querySelector("#landingImage")?.src || document.querySelector("#imgBlkFront")?.src || "",
            currentPrice: current || "",
            oldPrice: old || "",
            discount: disc
        }
    }""")

async def parse_product_uae(page):
    return await page.evaluate("""() => {
        const get = s => document.querySelector(s)?.innerText.trim() || "";
        const cleanToNum = (txt) => {
            if (!txt) return null;
            let n = txt.replace(/[^\d.]/g, '');
            return n ? parseFloat(n) : null;
        };

        const availText = get("#availability").toLowerCase();
        const isOut = availText.includes("غير متوفر") || availText.includes("غير متاح") || availText.includes("currently unavailable");
        
        let currentPriceStr = "";
        if (!isOut) {
            const priceContainer = document.querySelector(".priceToPay span[aria-hidden='true']") ||
                                   document.querySelector(".apex_on_twister_price span[aria-hidden='true']");
            if (priceContainer) {
                currentPriceStr = priceContainer.innerText.replace(/[\\n\\r]/g, '').trim();
            } else {
                let rawPrice = get(".priceToPay .a-offscreen") || get(".a-price .a-offscreen");
                currentPriceStr = rawPrice.includes("with") ? rawPrice.split("with")[0].trim() : rawPrice;
            }
        }

        let oldPriceStr = get(".basisPrice .a-offscreen") || 
                          get(".a-text-price[data-a-strike='true'] .a-offscreen") ||
                          get("#listPrice");

        let discount = get(".savingsPercentage") || 
                       get(".reinventPriceSavingsPercentageMargin") || 
                       get(".priceBlockSavingsString");

        if (!discount) {
            let currNum = cleanToNum(currentPriceStr);
            let oldNum = cleanToNum(oldPriceStr);
            if (currNum && oldNum && oldNum > currNum) {
                let diff = ((oldNum - currNum) / oldNum) * 100;
                discount = "-" + Math.round(diff) + "%";
            }
        }

        const img = document.querySelector("#landingImage") || document.querySelector("#imgTagWrapperId img");
        
        return {
            title: document.querySelector("#productTitle")?.innerText.trim() || "",
            img: img?.getAttribute('data-old-hires') || img?.src || "",
            currentPrice: currentPriceStr || "",
            oldPrice: oldPriceStr || "",
            discount: discount || ""
        }
    }""")

async def parse_product_usa(page):
    return await page.evaluate('''() => {
        const get = (s) => document.querySelector(s)?.innerText?.trim() || "";
        const availText = get("#availability").toLowerCase();
        const isOut = availText.includes("currently unavailable");
        let currentPrice = "";
        if (!isOut) {
            const p = document.querySelector(".a-price .a-offscreen") ||
                      document.querySelector("#price_inside_buybox") ||
                      document.querySelector(".apexPriceToPay .a-offscreen");
            currentPrice = p ? p.innerText.trim() : "";
        }
        return {
            title: get("#productTitle"),
            currentPrice: currentPrice,
            img: document.querySelector("#landingImage")?.src || "",
            oldPrice: get(".basisPrice .a-offscreen") || get(".a-text-price .a-offscreen"),
            discount: get(".savingsPercentage")
        };
    }''')

async def parse_product_europe_common(page):
    return await page.evaluate('''() => {
        const get = (s) => document.querySelector(s)?.innerText?.trim() || "";
        
        const extractPrice = (selector) => {
            const el = document.querySelector(selector);
            if (!el) return null;
            let text = el.innerText.replace(/[\\n\\r€$£\\s]/g, '').replace(',', '.').trim();
            const match = text.match(/\\d+(?:\\.\\d+)?/);
            return match ? match[0] : null;
        };

        let currentPrice = extractPrice('.priceToPay') || 
                           extractPrice('.apexPriceToPay') || 
                           extractPrice('.a-price:not(.a-text-price) span[aria-hidden="true"]') ||
                           extractPrice('.a-price .a-offscreen');

        let oldPrice = extractPrice(".basisPrice .a-offscreen") || 
                       extractPrice(".a-text-price .a-offscreen") ||
                       extractPrice(".a-text-strike");

        let discount = get(".savingsPercentage") || 
                       get(".reinventPriceSavingsPercentageMargin") || 
                       "";
        
        if (!discount && currentPrice && oldPrice) {
            const curr = parseFloat(currentPrice);
            const old = parseFloat(oldPrice);
            if (old > curr) {
                discount = "-" + Math.round(((old - curr) / old) * 100) + "%";
            }
        } else if (discount && !discount.startsWith('-')) {
            discount = '-' + discount;
        }

        return {
            title: get("#productTitle"),
            img: document.querySelector("#landingImage")?.src || document.querySelector("#imgBlkFront")?.src || "",
            currentPrice: currentPrice || "",
            oldPrice: oldPrice || "",
            discount: discount || ""
        };
    }''')

async def parse_product_france(page):
    return await parse_product_europe_common(page)

async def parse_product_germany(page):
    return await parse_product_europe_common(page)

async def parse_product_italy(page):
    return await parse_product_europe_common(page)

async def parse_product_general(page):
    return await page.evaluate("""() => {
        const get = s => document.querySelector(s)?.innerText.trim() || "";
        const availText = get("#availability").toLowerCase();
        const isOut = availText.includes("unavailable");
        let currentPrice = "";
        if (!isOut) {
            currentPrice = get(".a-price .a-offscreen") || get(".priceToPay");
        }
        return {
            title: document.querySelector("#productTitle")?.innerText.trim() || "",
            img: document.querySelector("#landingImage")?.src || "",
            currentPrice: currentPrice,
            oldPrice: get(".a-text-price .a-offscreen"),
            discount: get(".savingsPercentage")
        }
    }""")

async def parse_list_common(page, base_url):
    return await page.evaluate('''(base_url) => {
    const products = [];
    const seenUrls = new Set();
    
    let items = Array.from(document.querySelectorAll([
        '.s-result-item[data-asin]',
        '.s-card-container',
        '.p13n-sc-uncoverable-faceout',
        '.s-product-image-container',
        '.puis-card-container'
    ].join(', ')));

    for (let item of items) {
        if (products.length >= 4) break;

        const linkEl = item.querySelector('a[href*="/dp/"], a[href*="/gp/product/"]');
        let href = linkEl ? linkEl.getAttribute('href') : '';
        if (href) {
            href = href.split('/ref=')[0].split('?')[0];
            if (!href.startsWith('http')) href = base_url + href;
        }
        if (!href || seenUrls.has(href)) continue;

        let title = "";
        
        const titleSelectors = [
            'h2.a-text-normal', 
            '.p13n-sc-truncate-desktop-type2', 
            'h2 a span', 
            'h2 span',
            '.a-size-base-plus.a-color-base.a-text-normal'
        ];

        for (let s of titleSelectors) {
            let el = item.querySelector(s);
            if (el) {
                let text = el.innerText.trim();
                if (text.length > 15) {
                    title = text;
                    break; 
                } else if (text.length > 0) {
                    title = text;
                }
            }
        }

        if (title.length < 15) {
            const ariaEl = item.querySelector('h2[aria-label]');
            if (ariaEl && ariaEl.getAttribute('aria-label').length > title.length) {
                title = ariaEl.getAttribute('aria-label');
            }
        }

        title = title.replace(/\\n/g, ' ').trim();

        const extractPrice = (elText) => {
            if (!elText) return null;
            let txt = elText.replace(/[\\s]|SAR|EGP|AED/g, '').replace(',', '.');
            let match = txt.match(/\\d+(?:\\.\\d+)?/);
            return match ? match[0] : null;
        };

        let currentPrice = "";
        const priceSelectors = [
            '.a-price:not(.a-text-price) span[aria-hidden="true"]', 
            '.a-price .a-offscreen', 
            '._cDEzb_p13n-sc-price_3mJ9Z',
            '.a-color-price'
        ];
        
        for (let s of priceSelectors) {
            let el = item.querySelector(s);
            if (el) {
                let p = extractPrice(el.innerText);
                if (p) { currentPrice = p; break; }
            }
        }

        if (!currentPrice) {
            const currencyRegex = /([€$£]|EGP|SAR|AED)\\s?(\\d{1,3}(?:[.,]\\d{3})*(?:[.,]\\d{2})?)/;
            const match = item.innerText.match(currencyRegex);
            if (match) currentPrice = extractPrice(match[0]);
        }

        if (!currentPrice || parseFloat(currentPrice) <= 0) continue;

        seenUrls.add(href);
        products.push({
            title: title.substring(0, 100),
            img: item.querySelector('img')?.src || "",
            currentPrice: currentPrice,
            oldPrice: extractPrice(item.querySelector('.a-text-price .a-offscreen, .a-text-strike')?.innerText) || "", 
            discount: "",
            product_url: href
        });
    }
    return products;
}''', base_url)

async def scrape_page(url, country):
    product_country_info = COUNTRIES_CONFIG.get(country, COUNTRIES_CONFIG["United States"])
    locale_code = product_country_info.get("locale", "en-US")
    domain = product_country_info.get("domain", "amazon.com")
    currency = product_country_info.get("currency", "USD")
    base_url = f"https://www.{domain}"

    PARSERS_MAP = {
        "Egypt": parse_product_egypt,
        "Saudi Arabia": parse_product_saudi,
        "Emirates": parse_product_uae,
        "United States": parse_product_usa,
        "France": parse_product_europe_common,
        "Germany": parse_product_europe_common,
        "Italy": parse_product_europe_common,
    }

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True, 
            args=["--disable-blink-features=AutomationControlled"]
        )
        
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            locale=locale_code,
            extra_http_headers={"Accept-Language": f"{product_country_info['lang']},en-US;q=0.9"},
            viewport={'width': 1280, 'height': 800}
        )
        
        await context.add_cookies([{
            'name': 'i18n-prefs',
            'value': currency,
            'domain': f".{domain}",
            'path': '/'
        }])
        
        page = await context.new_page()
        
        try:
            logging.info(f"Navigating to {country} URL: {url}...")
            await page.goto(url, timeout=80000, wait_until="domcontentloaded")
            
            await page.evaluate("window.scrollBy(0, 600)")
            await asyncio.sleep(2)
            
            try:
                await page.wait_for_selector(
                    "#productTitle, .s-result-item, [data-asin], .s-card-container, .puis-card-container", 
                    timeout=20000
                )
            except:
                logging.warning(f"Timeout waiting for {country} selectors, trying to parse anyway...")

            product_title_el = await page.query_selector("#productTitle")
            
            if product_title_el:
                logging.info(f"Detected single product page for {country}.")
                parser_func = PARSERS_MAP.get(country, parse_product_general)
                data = await parser_func(page)
                
                if data:
                    data['product_url'] = url
                    return [data] if data.get('currentPrice') else None
            else:
                logging.info(f"Detected list/category page for {country}.")
                products = await parse_list_common(page, base_url)
                
                if not products:
                    logging.info("Products not found, performing deep scroll...")
                    await page.evaluate("window.scrollBy(0, 1200)")
                    await asyncio.sleep(2)
                    products = await parse_list_common(page, base_url)
                
                return products

        except Exception as e:
            logging.error(f"Scrape Error for {country}: {str(e)}")
            return None
        finally:
            await browser.close()
def get_target_lang(context):
    display_choice = context.user_data.get("display_lang", "local")
    country = context.user_data.get("country", "United States")
    
    if display_choice == "en":
        return "en"
    
    return COUNTRIES_CONFIG[country]["lang"]

def get_ui_text(context):
    lang = get_target_lang(context)
    return MESSAGES.get(lang, MESSAGES["en"])

def main_keyboard(context):
    txt = get_ui_text(context)
    return ReplyKeyboardMarkup([
        [KeyboardButton(txt["btn_country"]), KeyboardButton(txt["btn_lang"])],
        [KeyboardButton(txt["btn_help"]), KeyboardButton(txt["home"])]
    ], resize_keyboard=True)

def translate_text(text, target):
    try:
        if not text: return ""
        if detect(text) == target: return text
        return GoogleTranslator(source="auto", target=target).translate(text)
    except: return text

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.setdefault("country", "United States")
    context.user_data.setdefault("display_lang", "local")
    txt = get_ui_text(context)
    await update.message.reply_text(txt["welcome"], reply_markup=main_keyboard(context))

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = get_ui_text(context)
    text = update.message.text.strip()

    if text == txt["home"]:
        await start(update, context)
    elif text == txt["btn_country"]:
        kb = [[InlineKeyboardButton(f"{v['flag']} {k}", callback_data=f"c_{k}")] for k, v in COUNTRIES_CONFIG.items()]
        await update.message.reply_text(txt["btn_country"], reply_markup=InlineKeyboardMarkup(kb))
    elif text == txt["btn_lang"]:
        lang_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("اللغة الأصلية للدولة 🌐", callback_data="lang_local")],
            [InlineKeyboardButton("English 🇬🇧", callback_data="lang_en")]
        ])
        await update.message.reply_text("اختر لغة العرض / Choose Display Language:", reply_markup=lang_kb)
    elif text == txt["btn_help"]:
        await update.message.reply_text(txt["help"])
    elif "amazon." in text.lower() or "amzn.to" in text.lower():
        await handle_amazon(update, context)

async def handle_amazon(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = get_ui_text(context)
    target_lang = get_target_lang(context)
    country = context.user_data.get("country", "United States")
    config = COUNTRIES_CONFIG[country]
    
    status = await update.message.reply_text(txt["fetching"])
    products = await scrape_page(update.message.text, country)

    if not products:
        await status.edit_text(txt["error"])
        return

    local_country_name = config["names"].get(target_lang, country)
    media_group = []

    for data in products:
        # 1. تجهيز النص (Caption) لكل منتج على حدة
        title = translate_text(data["title"], target_lang)
        
        caption = f"📦 <b>{title}</b>\n\n"
        if not data.get("currentPrice"):
            caption += f"⚠️ {txt['unavailable_extra'].format(country=local_country_name)}\n"
        else:
            caption += f"💰 <b>{txt['price']}:</b> {data['currentPrice']} {config['currency']}\n"
            if data.get("oldPrice"): 
                caption += f"<s>{txt['old_price']}: {data['oldPrice']} {config['currency']}</s>\n"
            if data.get("discount"): 
                caption += f"📉 <b>{txt['discount']}:</b> {data['discount']}\n"

        caption += f"\n📍 {config['flag']} {local_country_name}\n"
        caption += f"🔗 <a href='{data['product_url']}'>رابط المنتج</a>"

        # 2. إضافة الصورة مع الـ Caption الخاص بها إلى القائمة
        if data.get("img"):
            media_group.append(
                InputMediaPhoto(
                    media=data["img"], 
                    caption=caption, 
                    parse_mode="HTML"
                )
            )
        else:
            # إذا لم توجد صورة، نرسلها كنص (اختياري)
            # ملحوظة: MediaGroup يجب أن يحتوي على صور فقط
            pass

    # 3. إرسال المجموعة كاملة في رسالة واحدة (ألبوم)
    if media_group:
        try:
            await update.message.reply_media_group(media=media_group)
        except Exception as e:
            logging.error(f"Error sending media group: {e}")
            await update.message.reply_text("❌ حدث خطأ أثناء إرسال مجموعة الصور.")
    else:
        await update.message.reply_text("❌ لم يتم العثور على صور للمنتجات.")

    await status.delete()

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data.startswith("c_"):
        context.user_data["country"] = query.data.replace("c_", "")
    elif query.data == "lang_local":
        context.user_data["display_lang"] = "local"
    elif query.data == "lang_en":
        context.user_data["display_lang"] = "en"

    txt = get_ui_text(context)
    await query.edit_message_text(txt["updated"])
    await query.message.reply_text(txt["welcome"], reply_markup=main_keyboard(context))

if __name__ == "__main__":
    TOKEN = "YOUR_BOT_TOKEN"
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    print("Bot is running... 🚀")
    app.run_polling()
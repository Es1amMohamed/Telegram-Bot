import logging
import asyncio
import locale
from playwright.async_api import async_playwright
from langdetect import detect
from deep_translator import GoogleTranslator

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
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
        "welcome": "مرحباً 👋 أرسل رابط منتج من أمازون",
        "fetching": "🔍 جاري جلب بيانات المنتج...",
        "price": "السعر الحالي",
        "old_price": "السعر الأصلي",
        "discount": "الخصم",
        "home": "الرئيسية 🏠",
        "btn_country": "🌍 تغيير الدولة",
        "btn_lang": "🌐 اللغة / Language",
        "btn_help": "❓ مساعدة",
        "help": "أرسل رابط منتج من أمازون 🛒",
        "error": "❌ حدث خطأ أثناء جلب المنتج",
        "updated": "✅ تم التحديث",
        "unavailable_extra": "المنتج غير متوفر في مخازن أمازون {country} حالياً."
    },
    "en": {
        "welcome": "Welcome 👋 Send an Amazon link",
        "fetching": "🔍 Fetching product data...",
        "price": "Current Price",
        "old_price": "Original Price",
        "discount": "Discount",
        "home": "Home 🏠",
        "btn_country": "🌍 Change Country",
        "btn_lang": "🌐 Language / اللغة",
        "btn_help": "❓ Help",
        "help": "Send an Amazon product link 🛒",
        "error": "❌ Error fetching product",
        "updated": "✅ Updated successfully",
        "unavailable_extra": "The product is currently not available in Amazon {country} warehouses."
    },
    "it": {
        "welcome": "Benvenuto 👋 Invia un link Amazon",
        "fetching": "🔍 Recupero dati prodotto...",
        "price": "Prezzo attuale",
        "old_price": "Prezzo originale",
        "discount": "Sconto",
        "home": "Home 🏠",
        "btn_country": "🌍 Cambia Paese",
        "btn_lang": "🌐 Lingua / Language",
        "btn_help": "❓ Aiuto",
        "help": "Invia un link di un prodotto Amazon 🛒",
        "error": "❌ Errore nel recupero del prodotto",
        "updated": "✅ Aggiornato con successo",
        "unavailable_extra": "Il prodotto non è attualmente disponibile nei magazzini Amazon {country}."
    },
    "fr": {
        "welcome": "Bienvenue 👋 Envoyez un lien Amazon",
        "fetching": "🔍 Récupération des données...",
        "price": "Prix actuel",
        "old_price": "Prix d'origine",
        "discount": "Remise",
        "home": "Accueil 🏠",
        "btn_country": "🌍 Changer de pays",
        "btn_lang": "🌐 Langue / Language",
        "btn_help": "❓ Aide",
        "help": "Envoyez un lien de produit Amazon 🛒",
        "error": "❌ Erreur lors de la récupération",
        "updated": "✅ Mis à jour avec succès",
        "unavailable_extra": "Le produit n'est pas disponible actuellement dans les entrepôts Amazon {country}."
    },
    "de": {
        "welcome": "Willkommen 👋 Amazon-Link senden",
        "fetching": "🔍 Produktdaten werden geladen...",
        "price": "Aktueller Preis",
        "old_price": "Originalpreis",
        "discount": "Rabatt",
        "home": "Startseite 🏠",
        "btn_country": "🌍 Land ändern",
        "btn_lang": "🌐 Sprache / Language",
        "btn_help": "❓ Hilfe",
        "help": "Senden Sie einen Amazon-Produktlink 🛒",
        "error": "❌ Fehler beim Abrufen des Produkts",
        "updated": "✅ Erfolgreich aktualisiert",
        "unavailable_extra": "Das Produkt ist derzeit nicht in den Amazon-Lagern in {country} verfügbar."
    }
}

async def parse_egypt(page):

    return await page.evaluate("""() => {

        const get = s => document.querySelector(s)?.innerText.trim() || "";

        const availText = get("#availability").toLowerCase();

        const isOut = availText.includes("غير متوفر") || availText.includes("غير متاح") || availText.includes("currently unavailable");

        let currentPrice = "";

        if (!isOut) {

            const priceContainer = document.querySelector(".priceToPay span[aria-hidden='true']") ||

                                   document.querySelector(".apex_on_twister_price span[aria-hidden='true']");

            if (priceContainer) {

                currentPrice = priceContainer.innerText.replace(/[\\n\\r]/g, '').trim();

            } else {

                let rawPrice = get(".priceToPay .a-offscreen") || get(".a-price .a-offscreen");

                currentPrice = rawPrice.includes("with") ? rawPrice.split("with")[0].trim() : rawPrice;

            }

        }

        const img = document.querySelector("#landingImage") || document.querySelector("#imgTagWrapperId img");

        return {

            title: document.querySelector("#productTitle")?.innerText.trim() || "",

            img: img?.getAttribute('data-old-hires') || img?.src || "",

            currentPrice: currentPrice || "",

            oldPrice: get(".basisPrice .a-offscreen") || get(".a-text-price[data-a-strike='true'] .a-offscreen"),

            discount: get(".savingsPercentage") || get(".reinventPriceSavingsPercentageMargin") || get(".savingPriceOverride")

        }

    }""")

async def parse_saudi(page):

    return await page.evaluate("""() => {

        const get = s => document.querySelector(s)?.innerText.trim() || "";

        const availText = get("#availability").toLowerCase();

        const isOut = availText.includes("غير متوفر") || availText.includes("غير متاح") || availText.includes("currently unavailable");

       

        let currentPrice = "";

        if (!isOut) {

            const priceContainer = document.querySelector(".priceToPay span[aria-hidden='true']") ||

                                   document.querySelector(".apex_on_twister_price span[aria-hidden='true']");

            if (priceContainer) {

                currentPrice = priceContainer.innerText.replace(/[\\n\\r]/g, '').trim();

            } else {

                let rawPrice = get(".priceToPay .a-offscreen") || get(".a-price .a-offscreen");

                currentPrice = rawPrice.includes("with") ? rawPrice.split("with")[0].trim() : rawPrice;

            }

        }



        let oldPrice = "";

        const oldPriceElement = document.querySelector("#corePriceDisplay_desktop_feature_div .a-text-price span.a-offscreen") ||

                                document.querySelector(".basisPrice .a-offscreen");

        oldPrice = oldPriceElement ? oldPriceElement.innerText.trim() : "";



        return {

            title: document.querySelector("#productTitle")?.innerText.trim() || "",

            img: document.querySelector("#landingImage")?.src || "",

            currentPrice: currentPrice || "",

            oldPrice: oldPrice,

            discount: get(".savingsPercentage") || get(".reinventPriceSavingsPercentageMargin")

        }

    }""")

async def parse_uae(page):

    return await page.evaluate("""() => {

        const get = s => document.querySelector(s)?.innerText.trim() || "";

        const availText = get("#availability").toLowerCase();

        const isOut = availText.includes("غير متوفر") || availText.includes("غير متاح") || availText.includes("currently unavailable");

        let currentPrice = "";

        if (!isOut) {

            const priceContainer = document.querySelector(".priceToPay span[aria-hidden='true']") ||

                                   document.querySelector(".apex_on_twister_price span[aria-hidden='true']");

           

            if (priceContainer) {

                currentPrice = priceContainer.innerText.replace(/[\\n\\r]/g, '').trim();

            } else {

                let rawPrice = get(".priceToPay .a-offscreen") || get(".a-price .a-offscreen");

                currentPrice = rawPrice.includes("with") ? rawPrice.split("with")[0].trim() : rawPrice;

            }

        }



        const img = document.querySelector("#landingImage") || document.querySelector("#imgTagWrapperId img");

       

        return {

            title: document.querySelector("#productTitle")?.innerText.trim() || "",

            img: img?.getAttribute('data-old-hires') || img?.src || "",

            currentPrice: currentPrice || "",

            oldPrice: get(".basisPrice .a-offscreen") || get(".a-text-price[data-a-strike='true'] .a-offscreen"),

            discount: get(".savingsPercentage") || get(".reinventPriceSavingsPercentageMargin")

        }

    }""")

async def parse_usa(page):
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

async def parse_europe_common(page):
    return await page.evaluate('''() => {
        const get = (s) => document.querySelector(s)?.innerText?.trim() || "";
        const availText = get("#availability span").toLowerCase();
        const isOut = availText.includes("indisponible") ||
                      availText.includes("non disponible") ||
                      availText.includes("nicht verfügbar") ||
                      availText.includes("non disponibile") ||
                      availText.includes("unavailable");
        let currentPrice = "";
        let oldPrice = "";
        let discount = "";
        if (!isOut) {
            const symbol = get(".a-price-symbol");
            const whole = get(".a-price-whole");
            const fraction = get(".a-price-fraction");
            if (symbol && whole) {
                currentPrice = symbol + whole.replace(/\\D/g, '') + (fraction ? ',' + fraction : '');
            } else {
                currentPrice = get(".a-price .a-offscreen") ||
                               get("#price_inside_buybox .a-offscreen") ||
                               get(".apexPriceToPay .a-offscreen") ||
                               get(".a-color-price.a-text-price");
            }
            oldPrice = get(".basisPrice .a-text-price .a-offscreen") ||
                       get(".a-price.a-text-price .a-offscreen") ||
                       get(".a-text-strike .a-offscreen");
            discount = get(".savingsPercentage") ||
                       get(".savingPriceOverrideEdlp") ||
                       get(".reinventPriceSavingsPercentageMargin") ||
                       get("#savingsPercentage") ||
                       "";
            if (discount && !discount.startsWith('-')) {
                discount = '-' + discount;
            }

        }
        return {
            title: get("#productTitle"),
            currentPrice: currentPrice || "",
            img: document.querySelector("#landingImage")?.src ||
                  document.querySelector("#imgBlkFront")?.src || "",
            oldPrice: oldPrice || "",
            discount: discount || ""
        };

    }''')


async def parse_france(page):
    return await parse_europe_common(page)


async def parse_germany(page):
    return await parse_europe_common(page)


async def parse_italy(page):
    return await parse_europe_common(page)


async def parse_general(page):
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

async def scrape_product(url, country):
    product_country_info = COUNTRIES_CONFIG.get(country, COUNTRIES_CONFIG["United States"])
    locale_code = product_country_info.get("locale", "en-US")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            locale=locale_code,
            timezone_id="UTC"
        )

        await context.set_extra_http_headers({
            "Accept-Language": f"{product_country_info.get('lang', 'en')},en;q=0.9",
            "Referer": f"https://{product_country_info.get('domain', 'amazon.com')}/"

        })
        page = await context.new_page()
        try:
            await page.goto(url, timeout=60000, wait_until="domcontentloaded")
            content = await page.content()
            if "api-services-support@amazon.com" in content or "captcha" in content.lower():
                logging.error(f"Caught by Amazon Bot Detector in {country}!")
                return None
            await page.wait_for_selector("#productTitle", timeout=15000)

            if country == "Egypt":
                return await parse_egypt(page)
            elif country == "Saudi Arabia":
                return await parse_saudi(page)
            elif country == "Emirates":
                return await parse_uae(page)
            elif country == "United States":
                return await parse_usa(page)
            elif country == "France":
                return await parse_france(page)
            elif country == "Italy":
                return await parse_italy(page)
            elif country == "Germany":
                return await parse_germany(page)
            else:
                return await parse_general(page)
        except Exception as e:
            logging.error(f"Scrape Error for {country}: {e}")
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
    data = await scrape_product(update.message.text, country)

    if not data or not data.get("title"):
        await status.edit_text(txt["error"])
        return

    local_country_name = config["names"].get(target_lang, country)
    title = translate_text(data["title"], target_lang)
    
    caption = f"📦 <b>{title}</b>\n\n"
    if not data.get("currentPrice"):
        caption += f"⚠️ {txt['unavailable_extra'].format(country=local_country_name)}\n"
    else:
        caption += f"💰 <b>{txt['price']}:</b> {data['currentPrice']}\n"
        if data.get("oldPrice"): caption += f"<s>{txt['old_price']}: {data['oldPrice']}</s>\n"
        if data.get("discount"): caption += f"📉 <b>{txt['discount']}:</b> {data['discount']}\n"

    caption += f"\n📍 {config['flag']} {local_country_name}"

    if data.get("img"):
        try:
            await update.message.reply_photo(photo=data["img"], caption=caption, parse_mode="HTML")
            await status.delete()
        except: await status.edit_text(caption, parse_mode="HTML")
    else:
        await status.edit_text(caption, parse_mode="HTML")

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
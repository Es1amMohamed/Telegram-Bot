import logging
import asyncio
import httpx
import re
from playwright.async_api import async_playwright
from telegram import Update, InputMediaPhoto
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes, CommandHandler

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

async def expand_url(url):
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1"
        }
        async with httpx.AsyncClient(follow_redirects=True, timeout=15.0, headers=headers) as client:
            response = await client.get(url)
            final_url = str(response.url)
            logging.info(f"🔗 Expanded URL: {final_url}")
            return final_url
    except Exception as e:
        logging.error(f"⚠️ Error expanding URL: {e}")
        return url

async def fetch_amazon_dynamic(url):
    async with async_playwright() as p:
        iphone_13 = p.devices["iPhone 13 Pro Max"]
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(**iphone_13)
        page = await context.new_page()
        
        try:
            final_url = await expand_url(url)
            await page.goto(final_url, wait_until="domcontentloaded", timeout=60000)
            
            await page.evaluate("window.scrollBy(0, 600)")
            await asyncio.sleep(3)

            products = await page.evaluate("""
                () => {
                    const items = Array.from(document.querySelectorAll('.p13n-mobile-grid-item, .zg-carousel-general-faceout, .s-result-item, [data-asin]'));
                    let results = [];
                    let seenAsins = new Set();

                    for (let item of items) {
                        if (results.length >= 4) break;

                        const asin = item.getAttribute('data-asin') || item.id;
                        if (!asin || seenAsins.has(asin) || asin.length < 5) continue;

                        const nameEl = item.querySelector('.p13n-sc-truncate-desktop-type2, h2, .a-size-small, .p13n-sc-truncate-mobile-type2');
                        if (!nameEl) continue;

                        seenAsins.add(asin);

                        const priceEl = item.querySelector('._cDEzb_p13n-sc-price_3mJ9Z, .p13n-sc-price, .a-price');
                        let rawText = priceEl ? priceEl.innerText.trim() : "";
                        
                        let currency = "N/A";
                        let currentPrice = "";

                        if (rawText) {
                            rawText = rawText.replace(/\\u00a0/g, ' ').replace(/\\s/g, ' '); 
                            const currencyMatch = rawText.match(/[a-zA-Z\\u0621-\\u064A$£€]+/);
                            const priceMatch = rawText.match(/[\\d.,]+/);

                            if (currencyMatch) currency = currencyMatch[0];
                            if (priceMatch) currentPrice = priceMatch[0];
                        }

                        const oldPriceEl = item.querySelector('.a-text-strike, .a-price.a-text-price span, .basisPrice .a-offscreen');
                        let oldPrice = oldPriceEl ? oldPriceEl.innerText.replace(/[^\\d.,]/g, '').trim() : "";

                        const imgEl = item.querySelector('img');
                        let imgUrl = imgEl ? imgEl.src : "";

                        results.push({
                            name: nameEl.innerText.trim(),
                            current_price: currentPrice || "0.00",
                            old_price: oldPrice,
                            currency: currency,
                            image: imgUrl,
                            category: document.querySelector('.category-title, h1, .a-carousel-heading')?.innerText.trim() || "Global Store"
                        });
                    }
                    return results;
                }
            """)
            return products
        except Exception as e:
            logging.error(f"Error: {e}")
            return []
        finally:
            await browser.close()


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw_text = update.message.text
    url_match = re.search(r'(https?://[^\s]+)', raw_text)
    
    if not url_match: return

    url = url_match.group(0)
    custom_category = raw_text.replace(url, "").strip()

    logging.info(f"🌐 Processing URL: {url}")
    if custom_category:
        logging.info(f"🏷️ Custom Category detected: {custom_category}")

    status_msg = await update.message.reply_text("📱 Extracting products...")
    products = await fetch_amazon_dynamic(url)

    if products:
        product_names = [p['name'][:30] for p in products]
        logging.info(f"✨ Found Products: {product_names}")

        media = []
        for p in products:
            category_to_show = custom_category if custom_category else p['category']
            
            caption = f"📦 **Product:** {p['name'][:75]}...\n"
            caption += f"📂 **Category:** {category_to_show}\n\n"
            
            if p['old_price'] and p['old_price'] != p['current_price']:
                caption += f"❌ **Old Price:** {p['old_price']}\n"
                caption += f"✅ **New Price:** {p['current_price']}\n"
            else:
                caption += f"💰 **Price:** {p['current_price']}\n"
            
            caption += f"💵 **Currency:** {p['currency']}**"

            if p['image']:
                media.append(InputMediaPhoto(p['image'], caption=caption, parse_mode='Markdown'))
        
        await update.message.reply_media_group(media)
        logging.info(f"✅ Success: Sent {len(products)} products with Category: {category_to_show}")
    else:
        logging.error("❌ Failed to fetch data.")
        await update.message.reply_text("❌ Failed to fetch data.")
    
    await status_msg.delete()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚀 Welcome! Send an Amazon link and I will fetch the top 4 products.")

if __name__ == '__main__':
    TOKEN = "8500333549:AAFPuoh8434zWRFf-9g3N8jxPvCn2ZNjJFw"
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    
    print("🚀 Universal Mobile Amazon Bot is running...")
    app.run_polling(drop_pending_updates=True)
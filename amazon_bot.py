import logging
import asyncio
import re
from playwright.async_api import async_playwright
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

AMAZON_REGEX = re.compile(r"(amazon\.[a-z.]+|amzn\.to)", re.IGNORECASE)

async def fetch_amazon_data(url):
    browser = None
    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                viewport={'width': 1920, 'height': 1080}
            )
            page = await context.new_page()

            print(f"Opening Amazon URL: {url}")
            await page.goto(url, wait_until="networkidle", timeout=60000)

            data = await page.evaluate("""
                () => {
                    const getPrice = (selector) => {
                        const el = document.querySelector(selector);
                        if (!el) return null;
                        return el.innerText.replace(/[^0-9.,]/g, '').trim();
                    };

                    const titleEl = document.querySelector('#productTitle');
                    const imgEl = document.querySelector('#landingImage') || 
                                  document.querySelector('#main-image');

                    let priceAfter =
                        getPrice('.a-price .a-offscreen') ||
                        getPrice('#priceblock_ourprice') ||
                        getPrice('#priceblock_dealprice') ||
                        getPrice('.a-price-whole');

                    let priceBefore =
                        getPrice('.basisPrice .a-offscreen') ||
                        getPrice('.a-text-price .a-offscreen') ||
                        getPrice('#listPrice') ||
                        getPrice('.a-text-strike');

                    return {
                        name: titleEl ? titleEl.innerText.trim() : "N/A",
                        image: imgEl ? imgEl.src : null,
                        price_after: priceAfter || "N/A",
                        price_before: priceBefore || "N/A",
                        currency: "EGP"
                    };
                }
            """)

            if data['price_after'] == "N/A":
                content = await page.content()
                matches = re.findall(r'EGP\\s?([\\d,]+\\.\\d{2})', content)

                if matches:
                    prices = sorted(
                        list(set(float(m.replace(',', '')) for m in matches))
                    )
                    data['price_after'] = "{:,.2f}".format(prices[0])
                    if len(prices) > 1:
                        data['price_before'] = "{:,.2f}".format(prices[-1])

            return {
                "success": True,
                **data,
                "url": page.url
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

        finally:
            if browser:
                await browser.close()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome to the Amazon Price Bot\n"
        "Send an Amazon product link and I will fetch the latest price for you."
    )

async def process_amazon_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()

    waiting_msg = await update.message.reply_text(
        "⏳ Analyzing product data, please wait..."
    )

    data = await fetch_amazon_data(url)

    if data["success"]:
        symbol = data['currency']
        p_after = data['price_after'].replace('.00', '')
        p_before = data['price_before'].replace('.00', '')

        if p_before == "N/A" or p_before == p_after:
            price_msg = f"💰 **Current Price:** {p_after}\n**Currency:** {symbol}"
        else:
            price_msg = (
                f"❌ **Original Price:** {p_before}\n"
                f"✅ **Current Price:** {p_after}\n"
                f"**Currency:** {symbol}"
            )

        caption = (
            f"📦 **Product:** {data['name']}\n\n"
            f"{price_msg}\n\n"
            f"🔗 [View on Amazon]({data['url']})"
        )

        if data["image"]:
            await update.message.reply_photo(
                photo=data["image"],
                caption=caption,
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                caption,
                parse_mode='Markdown'
            )

        logging.info(f"✅ Product data fetched successfully: {data['name']}")

    else:
        await update.message.reply_text(
            f"❌ Failed to fetch product data:\n{data['error']}"
        )

    await waiting_msg.delete()


if __name__ == '__main__':
    TOKEN = "YOUR_BOT_TOKEN"

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(
        MessageHandler(filters.TEXT & (~filters.COMMAND), process_amazon_link)
    )

    print("🚀 Amazon Price Bot is running...")
    app.run_polling(drop_pending_updates=True)

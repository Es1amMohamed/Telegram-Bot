import logging
import asyncio
import re
from playwright.async_api import async_playwright
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

async def fetch_trendyol_data(url):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={'width': 1280, 'height': 800},
            locale="en-US"
        )
        page = await context.new_page()

        try:
            await context.add_cookies([
                {'name': 'countryCode', 'value': 'SA', 'domain': '.trendyol.com', 'path': '/'},
                {'name': 'language', 'value': 'en', 'domain': '.trendyol.com', 'path': '/'},
                {'name': 'storefrontId', 'value': '30', 'domain': '.trendyol.com', 'path': '/'}
            ])

            await page.goto(url, wait_until="networkidle", timeout=60000)
            
            await page.wait_for_timeout(5000)

            try:
                if await page.is_visible("#onetrust-accept-btn-handler"):
                    await page.click("#onetrust-accept-btn-handler")
            except: pass

            product_name = "N/A"
            h1_elements = await page.locator("h1").all()
            for el in h1_elements:
                text = await el.inner_text()
                if text and "Trendyol" not in text:
                    product_name = text.strip()
                    break
            
            price_after = "N/A"
            potential_prices = await page.locator("span, div, p").all()
            for el in potential_prices:
                try:
                    text = await el.inner_text()
                    if ("SAR" in text or "SR" in text or "ريال" in text) and any(c.isdigit() for c in text):
                        if len(text) < 25:
                            price_after = text.strip()
                            break
                except: continue

            image_url = None
            img_selectors = [".product-container img", ".base-product-image img", "img.product-image", ".gallery-container img"]
            for sel in img_selectors:
                img_el = await page.query_selector(sel)
                if img_el:
                    image_url = await img_el.get_attribute("src")
                    if image_url: break

            final_url = page.url
            await browser.close()

            if product_name == "N/A" or "Trendyol" in product_name:
                return {"success": False, "error": "Could not reach the product page. Please check the link."}

            return {
                "success": True,
                "name": product_name,
                "price_before": "N/A",
                "price_after": price_after,
                "image": image_url,
                "url": final_url
            }

        except Exception as e:
            await browser.close()
            return {"success": False, "error": f"Browser Error: {str(e)}"}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Welcome message when /start is pressed"""
    await update.message.reply_text(
        "👋 **Welcome to Trendyol Smart Bot!**\n\n"
        "Send me any Trendyol product link (short or long) and I will fetch its details for you.\n\n"
        "🚀 **Ready! Send your link now.**",
        parse_mode='Markdown'
    )

async def process_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processes product links sent by the user"""
    url = update.message.text
    if "trendyol.com" in url or "ty.gl" in url:
        waiting_msg = await update.message.reply_text("⏳ Simulating Saudi access & fetching product data...")
        
        data = await fetch_trendyol_data(url)
        
        if data["success"]:
            caption = (
                f"📦 **Product:** {data['name']}\n\n"
                f"💰 **Price:** {data['price_after']}\n\n"
                f"🔗 [Direct Link]({data['url']})"
            )
            if data["image"]:
                await update.message.reply_photo(photo=data["image"], caption=caption, parse_mode='Markdown')
            else:
                await update.message.reply_text(caption, parse_mode='Markdown')
        else:

            await update.message.reply_text(f"❌ {data['error']}")
        
        await waiting_msg.delete()
    else:

        await update.message.reply_text("⚠️ Please send a valid Trendyol link.")

if __name__ == '__main__':

    TOKEN = "YOUR_BOT_TOKEN_HERE"
    
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), process_link))
    
    print("🚀 Bot is running in English mode...")
    app.run_polling()
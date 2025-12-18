
import logging
import asyncio
import os
from playwright.async_api import async_playwright
from telegram import Update, InputMediaPhoto
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes, CommandHandler

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

async def fetch_trendyol_all_images(url):
    browser = None
    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(headless=True)
            device_config = p.devices["iPhone 13 Pro Max"]
            device_config["user_agent"] = "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"
            
            context = await browser.new_context(**device_config)
            await context.add_cookies([
                {'name': 'countryCode', 'value': 'SA', 'domain': '.trendyol.com', 'path': '/'},
                {'name': 'language', 'value': 'ar', 'domain': '.trendyol.com', 'path': '/'},
                {'name': 'storefrontId', 'value': '30', 'domain': '.trendyol.com', 'path': '/'}
            ])
            
            page = await context.new_page()

            print(f"Opening URL: {url}")
            await page.goto(url, wait_until="networkidle", timeout=120000)
            
            try:
                await page.wait_for_selector('.product-card', timeout=30000)
            except:
                pass

            await page.evaluate("window.scrollBy(0, 800)")
            await asyncio.sleep(5) 

            products_data = await page.evaluate("""
                () => {
                    const cards = Array.from(document.querySelectorAll('.product-card'));
                    cards.sort((a, b) => (parseInt(a.getAttribute('data-product-index')) || 0) - (parseInt(b.getAttribute('data-product-index')) || 0));

                    let results = [];
                    cards.slice(0, 4).forEach(card => {
                        const imgElements = Array.from(card.querySelectorAll('.image-slider img'));
                        let allImages = imgElements.map(img => img.src).filter(src => src && src.includes('http'));
                        allImages = [...new Set(allImages)];

                        const name = card.querySelector('.product-name')?.innerText.trim() || "Product";
                        const price = card.querySelector('.sale-price-container')?.innerText.replace(/\\n/g, ' ').trim() || "";
                        
                        results.push({
                            'images': allImages,
                            'name': name,
                            'price': price
                        });
                    });
                    return results;
                }
            """)

            return {"success": True, "products": products_data}

        except Exception as e:
            print(f"Error occurred: {e}")
            return {"success": False, "error": str(e)}
        finally:
            if browser:
                await browser.close()

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text
    if url.startswith("http"):
        status_msg = await update.message.reply_text("📸 Fetching details and images... Please wait.")
        data = await fetch_trendyol_all_images(url)
        
        if data["success"] and data["products"]:
            for i, item in enumerate(data["products"]):
                if not item['images']: continue
                media_group = [InputMediaPhoto(img, caption=f"📦 product number: {i+1}: {item['name']}\n💰 price: {item['price']}" if idx == 0 else "") 
                               for idx, img in enumerate(item['images'])]
                try:
                    await update.message.reply_media_group(media=media_group)
                    await asyncio.sleep(1)
                except Exception as e:
                    print(f"Failed to send media group: {e}")
        else:
            await update.message.reply_text("❌ Error: Could not retrieve data. The page might be taking too long to load.")
        
        await status_msg.delete()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 **Welcome to Trendyol Bot!**\nSend any link to start.", parse_mode='Markdown')

if __name__ == '__main__':
    TOKEN = "YOUR_BOT_TOKEN_HERE"
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    print("🚀 Bot is running with original logic + stability fixes...")
    app.run_polling(drop_pending_updates=True)



import logging
import asyncio
from playwright.async_api import async_playwright
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

async def fetch_trendyol_data(url):
    browser = None
    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(headless=True)
           
            iphone_13 = p.devices["iPhone 13 Pro Max"]
            context = await browser.new_context(**iphone_13, locale="en-US")
            page = await context.new_page()

            await context.add_cookies([
                {'name': 'countryCode', 'value': 'SA', 'domain': '.trendyol.com', 'path': '/'},
                {'name': 'language', 'value': 'en', 'domain': '.trendyol.com', 'path': '/'},
                {'name': 'storefrontId', 'value': '30', 'domain': '.trendyol.com', 'path': '/'}
            ])

        
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            
        
            await page.evaluate("window.scrollBy(0, 300)")
            await asyncio.sleep(2) 

            image_url = await page.evaluate("""
                () => {
               
                    const selectors = ['.sp-img', '.product-detail-image img', '.product-image-container img'];
                    for (let s of selectors) {
                        const img = document.querySelector(s);
                        if (img && img.src && img.src.startsWith('http')) return img.src;
                    }
                
                    const allImgs = Array.from(document.querySelectorAll('img'));
                    const mainImg = allImgs.find(i => i.width > 200) || allImgs[0];
                    return mainImg ? mainImg.src : null;
                }
            """)

            product_name = await page.locator("h1").first.inner_text() if await page.locator("h1").count() > 0 else "N/A"
            
      
            price_after = await page.evaluate("""
                () => {
             
                    const priceSelectors = [
                        '.product-price', 
                        '.sale-price', 
                        '.discounted-price', 
                        '.price-container',
                        '.product-detail-price'
                    ];
                    
                    for (let s of priceSelectors) {
                        const el = document.querySelector(s);
                        if (el && el.innerText && (el.innerText.includes('SAR') || el.innerText.includes('SR') || el.innerText.includes('ريال'))) {
                            return el.innerText.trim();
                        }
                    }

                    const allSpans = Array.from(document.querySelectorAll('span, div'));
                    const priceElement = allSpans.find(el => 
                        (el.innerText.includes('SAR') || el.innerText.includes('SR')) && 
                        /\\d/.test(el.innerText) && 
                        el.innerText.length < 20
                    );
                    
                    return priceElement ? priceElement.innerText.trim() : "N/A";
                }
            """)

            final_url = page.url
            return {
                "success": True,
                "name": product_name.strip(),
                "price_after": price_after,
                "image": image_url,
                "url": final_url
            }

        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            if browser: await browser.close()





async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 **Welcome to Trendyol Smart Bot**\nSend me a link.")

async def process_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text
    if "trendyol" in url or "ty.gl" in url:
        waiting_msg = await update.message.reply_text("⏳ Processing...")
        data = await fetch_trendyol_data(url)
        
        if data["success"]:
            caption = (
                f"📦 **Product:** {data['name']}\n\n"
                f"💰 **Price:** {data['price_after']}\n\n"
                f"🔗 [Direct Link]({data['url']})"
            )
       
            if data["image"] and data["image"].startswith("http"):
                await update.message.reply_photo(photo=data["image"], caption=caption, parse_mode='Markdown')
            else:
                await update.message.reply_text(f"⚠️ Image not found, but here are details:\n\n{caption}", parse_mode='Markdown')
        else:
            await update.message.reply_text(f"❌ Error: {data['error']}")
        await waiting_msg.delete()

if __name__ == '__main__':
    TOKEN = "YOUR_BOT_TOKEN_HERE"
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), process_link))
    print("🚀 Bot is running in Mobile Simulation mode...")
    app.run_polling()
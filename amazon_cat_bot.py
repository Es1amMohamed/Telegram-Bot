import logging
import asyncio
import re
import json
from playwright.async_api import async_playwright
from telegram import Update, InputMediaPhoto
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes


logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

async def fetch_amazon_universal(url, config):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 3000},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        try:
            # 1. Apply Language from Config (URL manipulation)
            target_lang = "en_AE" if config['language'] == "en" else "ar_AE"
            base_url = url.split('?')[0]
            
            rh_match = re.search(r'rh=([^&]+)', url)
            if "s?" in url and rh_match:
                final_url = f"{base_url}?rh={rh_match.group(1)}&language={target_lang}"
            else:
                final_url = f"{base_url}?language={target_lang}"

            logging.info(f"Navigating to: {final_url}")
            await page.goto(final_url, wait_until="domcontentloaded", timeout=60000)

            # 2. Check Delivery Location (Senior's requirement)
            try:
                await page.wait_for_selector("#glow-ingress-line2", timeout=5000)
                current_loc = await page.inner_text("#glow-ingress-line2")
                if config['deliver_to'].lower() not in current_loc.lower():
                    logging.info(f"Location mismatch ({current_loc}). Triggering UI...")
                    await page.click("#nav-global-location-popover-link")
                    await asyncio.sleep(1) 
            except: pass

            await page.evaluate("window.scrollBy(0, 1000)")
            await asyncio.sleep(3)

            # 3. Universal Scraping Logic (Handles Octopus, Bestsellers, and Search Results)
            result = await page.evaluate("""
                () => {
                    const products = [];
                    let category = "General";
                    
                    const catEl = document.querySelector('h1, .a-color-state, .zg-banner-landing-page-header');
                    if (catEl) category = catEl.innerText.trim().replace(/[<>]/g, "");

                    const items = document.querySelectorAll(
                        '.octopus-pc-item-block, ' +
                        '.p13n-sc-uncoverable-faceout, ' +
                        '[data-component-type="s-search-result"], ' +
                        '.s-result-item[data-asin]'
                    );

                    const seen = new Set();
                    for (const el of items) {
                        if (products.length >= 4) break;

                        let name = "", price = "0", oldPrice = "0", image = "", asin = "";

                        // A - Octopus System (JSON)
                        const quickLook = el.querySelector('[data-octopus-quick-look]');
                        if (quickLook) {
                            try {
                                const data = JSON.parse(quickLook.getAttribute('data-octopus-quick-look'));
                                name = data.title;
                                price = data.price ? data.price.replace(/[^\\d.]/g, '') : "0";
                                oldPrice = data.strikePrice ? data.strikePrice.replace(/[^\\d.]/g, '') : "0";
                                image = data.image;
                                asin = data.asin;
                            } catch(e) {}
                        }

                        // B - Regular HTML Fallback
                        if (!name || name === "") {
                            const nEl = el.querySelector('h2, .octopus-pc-asin-title, .p13n-sc-truncate-desktop-type2, .a-size-base');
                            name = nEl ? nEl.innerText.trim() : "";
                        }
                        if (price === "0") {
                            const pEl = el.querySelector('.a-price-whole, ._cDEzb_p13n-sc-price_3mJ9Z, .a-color-price');
                            price = pEl ? pEl.innerText.replace(/[^\\d.]/g, '') : "0";
                        }
                        if (image === "" || !image.startsWith('http')) {
                            const iEl = el.querySelector('img');
                            image = iEl ? iEl.src : "";
                        }

                        asin = asin || el.getAttribute('data-asin') || el.id;

                        if (name && price !== "0" && !seen.has(asin)) {
                            seen.add(asin);
                            products.push({
                                name: name.replace(/[<>]/g, "").substring(0, 100),
                                price: price,
                                old_price: oldPrice,
                                image: image,
                                category: category
                            });
                        }
                    }
                    return products;
                }
            """)
            return result
        except Exception as e:
            logging.error(f"Global Scraper Error: {e}")
            return []
        finally:
            await browser.close()

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url_text = update.message.text
    url_match = re.search(r'(https?://[^\s]+)', url_text)
    if not url_match: return

    full_url = url_match.group(0)

    amazon_config = {
        "language": "en",
        "currency": "Currency",
        "deliver_to": "Selected Country"
    }

    if ".eg" in full_url:
        amazon_config.update({"currency": "EGP", "deliver_to": "Egypt"})
    elif ".sa" in full_url:
        amazon_config.update({"currency": "SAR", "deliver_to": "Saudi Arabia"})
    elif ".ae" in full_url:
        amazon_config.update({"currency": "AED", "deliver_to": "UAE"})
    elif ".com" in full_url and "amazon.com" in full_url:
        amazon_config.update({"currency": "USD", "deliver_to": "USA"})
    else:
        amazon_config.update({"currency": "Price", "deliver_to": "International"})

    status = await update.message.reply_text(f"🌍 Checking Amazon ({amazon_config['deliver_to']})...")
    
    products = await fetch_amazon_universal(full_url, amazon_config)

    if not products:
        await status.edit_text("❌ No products found. Please ensure the link contains a product list.")
        return

    media = []
    for p in products:
        caption = (
            f"📦 <b>{p['name']}...</b>\n\n"
            f"📂 <b>Category:</b> {p['category']}\n"
            f"💰 <b>Price:</b> {p['price']} {amazon_config['currency']}\n"
        )
        if p['old_price'] != "0":
            caption += f"<s>❌ Was: {p['old_price']}</s>\n"
        
        caption += f"📍 <b>Deliver to:</b> {amazon_config['deliver_to']}"

        if p['image']:
            media.append(InputMediaPhoto(p['image'], caption=caption, parse_mode='HTML'))

    try:
        if media:
            await update.message.reply_media_group(media)
            await status.delete()
    except Exception as e:
        logging.error(f"Telegram Media Error: {e}")
        await status.edit_text(f"⚠️ Error sending images: {e}")

if __name__ == "__main__":
    TOKEN = "8500333549:AAFPuoh8434zWRFf-9g3N8jxPvCn2ZNjJFw"
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    print("🚀 Bot is running (International Mode)...")
    app.run_polling()
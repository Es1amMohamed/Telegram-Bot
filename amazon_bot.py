import logging
import asyncio
import re
from urllib.parse import urlparse, quote  # أضفنا quote للصورة
from playwright.async_api import async_playwright
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

AMAZON_SHORT_DOMAINS = {"amzn.to", "a.co", "amzn.eu", "amzn.asia"}

async def resolve_short_url(page, url):
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        return page.url
    except:
        return url

async def handle_initial_popup(page, target_location):
    try:
        await page.wait_for_selector(".a-popover-modal, #GLUXSignInWidget", timeout=10000)
        await page.fill("#GLUXZipUpdateInput, input[placeholder*='city'], input[placeholder*='zip']", target_location)
        await asyncio.sleep(2)
        await page.click('input[aria-labelledby="GLUXZipUpdate-announce"], button:has-text("Apply")')
        await asyncio.sleep(3)
        await page.click("button:has-text('Done'), #GLUXConfirmClose", timeout=8000)
    except:
        pass

async def change_delivery_location(page, target_location, is_us=False):
    try:
        await page.wait_for_selector("#glow-ingress-line2, #nav-global-location-slot", timeout=10000)
        current = await page.inner_text("#glow-ingress-line2, #nav-global-location-slot")
        if target_location.lower() in current.lower():
            return True
    except:
        pass

    logging.info(f"Changing location to {target_location}")
    try:
        await page.click("#nav-global-location-popover-link, #glow-ingress-block", force=True, timeout=10000)
        await asyncio.sleep(5)
        input_sel = "#GLUXZipUpdateInput, input[placeholder*='zip'], input[placeholder*='city']"
        await page.wait_for_selector(input_sel, timeout=15000)
        await page.fill(input_sel, "")
        await page.type(input_sel, "10001" if is_us else target_location, delay=100)
        await asyncio.sleep(2)
        await page.click('input[aria-labelledby="GLUXZipUpdate-announce"], button:has-text("Apply")', timeout=10000)
        await asyncio.sleep(4)
        try:
            await page.click("button:has-text('Done'), #GLUXConfirmClose", timeout=8000)
        except:
            pass
        await asyncio.sleep(12)
        return True
    except Exception as e:
        logging.error(f"Location change error: {e}")
        return False

async def change_currency_if_needed(page, target_currency):
    map_loc = {"USD": "10001", "AED": "Dubai", "SAR": "Riyadh", "EGP": "Cairo"}
    target = map_loc.get(target_currency, "Dubai")
    is_us = target_currency == "USD"
    return await change_delivery_location(page, target, is_us)

async def fetch_single_product(original_url, config):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 4500},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            locale="en-US",
            extra_http_headers={"Accept-Language": "en-US,en;q=0.9"}
        )
        page = await context.new_page()
        try:

            if urlparse(original_url).netloc in AMAZON_SHORT_DOMAINS:
                original_url = await resolve_short_url(page, original_url)


            asin_match = re.search(r'/dp/([A-Z0-9]{10})|/gp/product/([A-Z0-9]{10})', original_url)
            if not asin_match:
                return None
            asin = asin_match.group(1) or asin_match.group(2)


            domain = ("amazon.com" if "amazon.com" in original_url else
                      "amazon.sa" if "amazon.sa" in original_url else
                      "amazon.ae" if "amazon.ae" in original_url else
                      "amazon.eg" if "amazon.eg" in original_url else "amazon.com")

   
            base_url = f"https://www.{domain}/dp/{asin}"
            final_url = base_url if domain in ["amazon.sa", "amazon.com"] else f"{base_url}?language={'en_AE' if config['language'] == 'en' else 'ar_AE'}"

            logging.info(f"Opening product: {final_url}")
            await page.goto(final_url, wait_until="domcontentloaded", timeout=60000)

            await handle_initial_popup(page, config['deliver_to'])
            await change_currency_if_needed(page, config['currency'])
            await change_delivery_location(page, config['deliver_to'], domain == "amazon.com")

            await asyncio.sleep(12)
            try:
                await page.wait_for_selector('#twister, .twisterSlotDiv, input[role="radio"]', timeout=10000)
                selected = await page.query_selector('input[role="radio"][aria-checked="true"]')
                if not selected:
                    selected = await page.query_selector('input[role="radio"]')
                if selected:
                    await selected.click()
                    logging.info("Clicked first variant to load price/title")
                    await asyncio.sleep(8)  
            except Exception as e:
                logging.info(f"No variants detected: {e}")
          
            product = await page.evaluate("""
() => {
    const data = {
        title: "",
        price: "",
        old_price: "",
        category: "Unknown",
        image: ""
    };

    // ================= TITLE =================
    data.title = document.querySelector('#productTitle')?.innerText.trim() || "Unknown";

    // ================= PRICE (ROBUST & GLOBAL) =================
    const priceRoot =
        document.querySelector('#corePriceDisplay_desktop_feature_div .priceToPay') ||
        document.querySelector('.priceToPay') ||
        document.querySelector('.a-price:not(.a-text-price)');

    if (priceRoot) {
        const symbol =
            priceRoot.querySelector('.a-price-symbol')?.innerText.trim() || '';

        const whole =
            priceRoot.querySelector('.a-price-whole')?.innerText
                ?.replace(/[^0-9]/g, '') || '';

        const fraction =
            priceRoot.querySelector('.a-price-fraction')?.innerText
                ?.replace(/[^0-9]/g, '') || '00';

        data.price = `${symbol}${whole}.${fraction}`.trim();
    } else {
        data.price = "Check on site";
    }

    // ================= OLD PRICE =================
    const oldPriceNode =
        document.querySelector('#corePriceDisplay_desktop_feature_div .a-text-price .a-offscreen') ||
        document.querySelector('.a-text-price .a-offscreen');

    if (oldPriceNode) {
        data.old_price = oldPriceNode.innerText.trim();
    }

    // ================= CATEGORY =================
    const crumbs = Array.from(
        document.querySelectorAll('#wayfinding-breadcrumbs_feature_div a')
    )
        .map(a => a.innerText.trim())
        .filter(Boolean);

    data.category = crumbs.slice(0, 3).join(' > ') || "Unknown";

    // ================= IMAGE =================
    const img =
        document.querySelector('#landingImage') ||
        document.querySelector('#imgTagWrapperId img');

    data.image =
        img?.getAttribute('data-old-hires') ||
        img?.src ||
        '';

    return data;
}
""")

            product['currency'] = config['currency']
            product['deliver_to'] = config['deliver_to']
            return product

        except Exception as e:
            logging.error(f"Scrape error: {e}")
            try:
                await page.screenshot(path="product_error.png", full_page=True)
            except:
                pass
            return None
        finally:
            await browser.close()

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE, custom_config: dict = None):
    url_text = update.message.text
    url_match = re.search(r'(https?://[^\s]+)', url_text)
    if not url_match:
        await update.message.reply_text("📌 Please send a valid Amazon product link.")
        return
    full_url = url_match.group(0)

    amazon_config = {"language": "en", "currency": "AED", "deliver_to": "Dubai"}

    if custom_config:
        amazon_config.update(custom_config)
    else:
        if ".eg" in full_url:
            amazon_config.update({"currency": "EGP", "deliver_to": "Cairo", "language": "en"})
        elif ".sa" in full_url:
            amazon_config.update({"currency": "SAR", "deliver_to": "Riyadh", "language": "ar"})
        elif ".ae" in full_url:
            amazon_config.update({"currency": "AED", "deliver_to": "Dubai", "language": "en"})
        elif "amazon.com" in full_url:
            amazon_config.update({"currency": "USD", "deliver_to": "New York", "language": "en"})

    status = await update.message.reply_text(f"🔍 Fetching product ({amazon_config['deliver_to']})...")

    product = await fetch_single_product(full_url, amazon_config)

    if not product or not product['title']:
        await status.edit_text("❌ Failed to load product.")
        return

    caption = f"📦 <b>{product['title']}</b>\n\n📂 <b>Category:</b> {product['category']}\n"
    if product['old_price']:
        caption += f"💰 <b>Price:</b> <s>{product['old_price']}</s> → <b>{product['price']}</b>\n"
    else:
        caption += f"💰 <b>Price:</b> <b>{product['price']}</b>\n"
    caption += f"📍 <b>Deliver to:</b> {product['deliver_to']}"

    try:
        if product['image']:
            safe_image = quote(product['image'], safe=':/?=&%#')
            await update.message.reply_photo(photo=safe_image, caption=caption, parse_mode='HTML')
        else:
            await update.message.reply_text(caption, parse_mode='HTML')
        await status.delete()
    except Exception as e:
        logging.error(f"Send error: {e}")
        await status.edit_text("⚠️ Error sending (image issue).")

if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()  

    TOKEN = "your_telegram_bot_token"
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND),
                                  lambda u, c: handle_message(u, c, None)))
    print("🚀 Single Product Amazon Bot - Final Version Running!")
    app.run_polling()
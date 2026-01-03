import logging
import asyncio
import re
import os
from urllib.parse import urlparse
from playwright.async_api import async_playwright
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

SCREENSHOTS_DIR = "amazon_screenshots"
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

AMAZON_SHORT_DOMAINS = {"amzn.to", "a.co", "amzn.eu", "amzn.asia"}

async def take_screenshot(page, prefix, attempt):
    filename = f"{SCREENSHOTS_DIR}/{prefix}_attempt_{attempt}.png"
    try:
        await page.screenshot(path=filename, full_page=True)
        logging.info(f"📸 Screenshot saved: {filename}")
    except: pass

async def resolve_short_url(page, url):
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        return page.url if page.url != url else url
    except:
        return url

async def handle_popups_and_location(page, target_location):
    try:
        consent_btn = await page.query_selector("#sp-cc-accept, button:has-text('Accept'), button:has-text('قبول')", timeout=5000)
        if consent_btn and await consent_btn.is_visible():
            await consent_btn.click()
            await asyncio.sleep(2)

        location_el = await page.query_selector("#glow-ingress-line1, #glow-ingress-line2, #nav-global-location-slot", timeout=5000)
        if location_el:
            current = await location_el.inner_text()
            if target_location.lower() in current.lower():
                return

            link = await page.query_selector("#nav-global-location-popover-link, #nav-global-location-slot")
            if link and await link.is_visible():
                await link.click(force=True)
                await asyncio.sleep(3)
                zip_input = await page.query_selector("#GLUXZipUpdateInput", timeout=10000)
                if zip_input:
                    await zip_input.fill("11511" if "United States" in target_location else "10001")
                    await page.click("input[aria-labelledby='GLUXZipUpdate-announce'], button:has-text('Apply')")
                    await asyncio.sleep(5)
                    await page.click("button:has-text('Done'), #GLUXConfirmClose", timeout=8000)
    except Exception as e:
        logging.warning(f"Popup issue: {e}")

async def get_price_from_page(page):
    """دالة جديدة لاستخراج السعر بطرق متعددة"""
    price_text = await page.evaluate("""
        () => {
            // جميع selectors الممكنة للسعر
            const selectors = [
                '.a-offscreen',
                '.a-price .a-offscreen',
                '#corePrice_feature_div .a-offscreen',
                '.a-price-whole',
                '.reinventPricePriceToPayMargin .a-price-whole',
                '.a-price-symbol',
                '#priceblock_ourprice',
                '#priceblock_dealprice',
                '.a-color-price'
            ];
            let prices = [];
            selectors.forEach(sel => {
                document.querySelectorAll(sel).forEach(el => {
                    const text = el.innerText.trim();
                    if (text && /[0-9]/.test(text) && text.length < 50) {
                        prices.push(text);
                    }
                });
            });
            // أول سعر غير فاضي
            return prices.find(p => p !== '' && p !== ' ') || null;
        }
    """)
    return price_text

async def fetch_single_product(original_url, config, max_retries=3):
    async with async_playwright() as p:
        for attempt in range(1, max_retries + 1):
            browser = None
            try:
                logging.info(f"Attempt {attempt}/{max_retries}: {original_url}")

                browser = await p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
                    viewport={"width": 1920, "height": 1080},
                    locale=config.get('locale', 'en-US'),
                    extra_http_headers={"Accept-Language": "en-US,en;q=0.9,ar;q=0.8"}
                )
                await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => false});")

                page = await context.new_page()

                if urlparse(original_url).netloc in AMAZON_SHORT_DOMAINS:
                    original_url = await resolve_short_url(page, original_url)

                await page.goto(original_url, wait_until="domcontentloaded", timeout=60000)

                # Wait للعنوان والسعر بطريقة مرنة
                await page.wait_for_selector('#productTitle', timeout=30000)
                await asyncio.sleep(4)
                await page.evaluate("window.scrollBy(0, 800)")
                await asyncio.sleep(3)

                await handle_popups_and_location(page, config['deliver_to'])

                # استخراج البيانات
                product = await page.evaluate("""
                    () => {
                        const data = {title: "Unknown", price: "Check on site", category: "Unknown", image: ""};
                        const titleEl = document.querySelector('#productTitle');
                        if (titleEl) data.title = titleEl.innerText.trim();

                        const img = document.querySelector('#landingImage, #imgTagWrapperId img');
                        if (img) data.image = img.getAttribute('data-old-hires') || img.src || "";

                        const crumbs = Array.from(document.querySelectorAll('#wayfinding-breadcrumbs_feature_div a')).map(a => a.innerText.trim());
                        data.category = crumbs.slice(0, 3).join(' > ') || "Unknown";

                        return data;
                    }
                """)

                # استخراج السعر بدالة منفصلة أقوى
                price = await get_price_from_page(page)
                if price:
                    product['price'] = price

                if product['title'] != "Unknown" and product['price'] != "Check on site":
                    product['currency'] = config['currency']
                    product['deliver_to'] = config['deliver_to']
                    await take_screenshot(page, "success", attempt)
                    return product

            except Exception as e:
                await take_screenshot(page, "error", attempt) if 'page' in locals() else None
                logging.error(f"Error attempt {attempt}: {e}")

            finally:
                if browser:
                    await browser.close()

            await asyncio.sleep(10)

        return None


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url_match = re.search(r'(https?://[^\s]+)', update.message.text)
    if not url_match: return
    full_url = url_match.group(0)

    amazon_config = {"currency": "USD", "deliver_to": "United States", "locale": "en-US"}
    domain_map = {
        ".eg": {"currency": "EGP", "deliver_to": "Cairo", "locale": "ar-EG"},
        ".sa": {"currency": "SAR", "deliver_to": "Riyadh", "locale": "ar-SA"},
        ".es": {"currency": "EUR", "deliver_to": "Madrid", "locale": "es-ES"}
    }
    parsed = urlparse(full_url)
    for domain, cfg in domain_map.items():
        if parsed.netloc.endswith(domain):
            amazon_config.update(cfg)
            break

    status = await update.message.reply_text("🔍 Fetching product details... (may take up to 2 minutes)")
    product = await fetch_single_product(full_url, amazon_config)

    if not product or product['title'] == "Unknown":
        await status.edit_text("❌ Error fetching product. Amazon blocked access temporarily. Try again in a few minutes.")
        return

    caption = f"📦 <b>{product['title']}</b>\n\n📂 <b>Category:</b> {product['category']}\n💰 <b>Price:</b> {product['currency']} {product['price']}\n📍 <b>Region:</b> {product['deliver_to']}"

    try:
        if product['image']:
            await update.message.reply_photo(photo=product['image'], caption=caption, parse_mode='HTML')
        else:
            await update.message.reply_text(caption, parse_mode='HTML')
        await status.delete()
    except Exception as e:
        logging.error(f"Send error: {e}")
        await status.edit_text(caption, parse_mode='HTML')

if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()
    TOKEN = "8275673221:AAFqU7osZUD3_kCdLv8P5FmleNTgLx3sJYE"
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    app.run_polling()


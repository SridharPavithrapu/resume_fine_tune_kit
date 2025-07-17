
import asyncio
from playwright.async_api import async_playwright
from PIL import Image, ImageOps
import pytesseract
import re
import time
import os
from dotenv import load_dotenv

load_dotenv()
EMAIL = os.getenv("JOBSCAN_EMAIL")
PASSWORD = os.getenv("JOBSCAN_PASSWORD")


async def run_jobscan(resume_text, jd_text):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        try:
            await page.goto("https://app.jobscan.co/auth/login", timeout=60000)
            await page.fill("input[name='email']", EMAIL)
            await page.fill("input[name='password']", PASSWORD)
            await page.click("button:has-text('Sign In')")
            await page.wait_for_selector("span.title:has-text('New Scan')")
            await page.click("span.title:has-text('New Scan')")

            resume_field = page.locator("textarea[placeholder^='Paste resume']")
            jd_field = page.locator("#jobDescriptionInput")
            await resume_field.fill(resume_text)
            await jd_field.fill(jd_text)

            scan_button = page.locator("button[data-test='scan-button']")
            await scan_button.click()

            await page.wait_for_selector("#score", timeout=60000)

            previous_img = None
            for i in range(20):
                await page.locator("#score").screenshot(path="score_section.png")
                img_bytes = open("score_section.png", "rb").read()
                if previous_img and img_bytes == previous_img:
                    break
                previous_img = img_bytes
                time.sleep(1)

            img = Image.open("score_section.png")
            thresholds = [150]
            upscales = [2, 3]
            psms = [3, 6, 7, 8, 10, 11]
            results = []

            for t in thresholds:
                for s in upscales:
                    big = img.resize((img.width * s, img.height * s))
                    gray = ImageOps.grayscale(big)
                    bw = gray.point(lambda x: 0 if x < t else 255, '1')
                    for psm in psms:
                        for wl in [True, False]:
                            config = f"--psm {psm} "
                            if wl:
                                config += "-c tessedit_char_whitelist=0123456789%"
                            text = pytesseract.image_to_string(bw, config=config).strip()
                            results.append((f"thr{t}_scale{s}_psm{psm}_{'wl' if wl else 'no_wl'}", text))

            all_texts = [text for _, text in results]
            best = max(all_texts, key=len)
            match = re.search(r"\d+%", best)
            if match:
                return match.group(0)
            digits = re.findall(r"\b\d{1,3}\b", best)
            if digits:
                return f"{digits[0]}%"
            return "N/A"
        except Exception:
            return "N/A"
        finally:
            await browser.close()


def get_jobscan_score(resume_text, jd_text):
    return asyncio.run(run_jobscan(resume_text, jd_text))

import asyncio
from playwright.async_api import async_playwright, expect
from PIL import Image, ImageOps
import pytesseract
import re
import time
import os
from dotenv import load_dotenv
from bs4 import BeautifulSoup
import fitz  # PyMuPDF

load_dotenv()
EMAIL = os.getenv("JOBSCAN_EMAIL")
PASSWORD = os.getenv("JOBSCAN_PASSWORD")
HEADLESS = False
OCR_DEBUG = os.getenv("OCR_DEBUG", "0") == "1"

async def extract_ats_feedback(page):
    html = await page.content()
    soup = BeautifulSoup(html, "html.parser")
    missing_keywords = [li.get_text(strip=True) for li in soup.select("ul.keywords-missing li") if li.get_text(strip=True)]
    missing_sections = [sec.get_text(strip=True) for sec in soup.select("div.missing-section span.section-name") if sec.get_text(strip=True)]
    return missing_keywords, list(filter(None, missing_sections))

def extract_skills_from_pdf(pdf_path):
    doc = fitz.open(pdf_path)
    text = "\n".join([page.get_text() for page in doc])

    def extract_section_skills(section_name):
        pattern = re.compile(rf"{section_name}.*?(?=\n\n|\Z)", re.DOTALL | re.IGNORECASE)
        match = pattern.search(text)
        if not match:
            return []

        block = re.sub(
            r"(Skills Comparison|Highlighted Skills|Add Skill|Copy All|Don't see skills.*?|Page \d+ of \d+|IMPORTANT|Jobscan Report.*?)",
            "", match.group(0), flags=re.DOTALL
        )

        raw_lines = [line.strip() for line in block.splitlines()]
        exclusions = {
            "Skill", "Resume", "Job Description", "Update", "Add Skill", "Copy All",
            "Skills Comparison", "Highlighted Skills", "Education Match", "IMPORTANT",
            "Recruiter tips", "from the job description?", "HIGH SCORE IMPACT", "MEDIUM SCORE IMPACT",
            "Update required education level", "your education is noted.", "jobs.",
            "frequently in the job description.", "Hard skills", "Soft skills", "Jobscan Report",
            "Resume Tone", "Job Level Match", "Job Title Match", "Date Formatting", "Measurable Results",
            "Update scan information", "internship or a personal project.",
            "found by our algorithms.", "View Measurable Results", "and buzzwords were found. Good job!",
            "Improve your job match by including more", "Customize this section using your"
        }

        skills = [
            line for line in raw_lines
            if re.search(r"[A-Za-z]", line)
            and len(line.split()) <= 6
            and len(line) <= 50
            and line.lower() not in exclusions
            and not line.endswith(":")
        ]

        return sorted(set(skills))

    return {
        "hard_skills": extract_section_skills("Hard skills"),
        "soft_skills": extract_section_skills("Soft skills"),
    }


async def run_jobscan(resume_text, jd_text):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=HEADLESS)
        context = await browser.new_context()
        page = await context.new_page()

        try:
            await page.goto("https://app.jobscan.co/auth/login", timeout=60000)
            await page.fill("input[name='email']", EMAIL)
            await page.fill("input[name='password']", PASSWORD)
            await page.click("button:has-text('Sign In')")
            await page.wait_for_load_state('networkidle')

            if "Invalid email or password" in await page.content():
                print("❌ Login failed: check credentials.")
                await page.screenshot(path="login_failed.png")
                return "N/A", [], [], {}

            # 🛡️ Dismiss location permission popup if visible
            try:
                if await page.locator("text=app.jobscan.co wants to").is_visible():
                    await page.locator("text=Never allow").click()
                    print("✅ Dismissed location permission popup")
            except Exception as e:
                print(f"⚠️ Location popup not found or already dismissed: {e}")

            for attempt in range(3):
                try:
                    print(f"🔁 Checking dashboard (attempt {attempt + 1}/3)...")
                    await page.wait_for_selector("span.title:has-text('New Scan')", timeout=10000)
                    break
                except:
                    print(f"⏳ Retry #{attempt + 1}: Reloading dashboard...")
                    await page.screenshot(path=f"dashboard_retry_{attempt + 1}.png")
                    await page.reload()
            else:
                print("❌ Failed to load dashboard after retries.")
                await page.screenshot(path="fail_dashboard_load.png")
                return "N/A", [], [], {}

            await page.click("span.title:has-text('New Scan')")
            await page.wait_for_timeout(1000)

            resume_field = page.locator("textarea[placeholder^='Paste resume']")
            jd_field = page.locator("#jobDescriptionInput")
            await expect(resume_field).to_be_visible(timeout=10000)
            await expect(jd_field).to_be_visible(timeout=10000)

            await resume_field.fill(resume_text)
            await jd_field.fill(jd_text)

            scan_button = page.locator("button[data-test='scan-button']")

            try:
                print("⏳ Waiting for scan button to become enabled...")
                await expect(scan_button).to_be_enabled(timeout=10000)
                print("✅ Scan button is enabled. Attempting click...")
                await scan_button.click()
                await page.wait_for_timeout(500)
            except Exception as e:
                print(f"⚠️ Scan button click failed on first try: {e}")
                await page.screenshot(path="scan_click_failed.png")
                print("🔁 Retrying scan button click...")
                try:
                    await page.keyboard.press("Escape")  # Dismiss any overlay
                    await page.wait_for_timeout(1000)
                    await scan_button.click()
                    await page.wait_for_timeout(500)
                except Exception as e2:
                    print(f"❌ Scan click retry also failed: {e2}")
                    raise

            # 🔧 NEW: Dismiss Jobscan Report Modal (if visible)
            try:
                if await page.locator("text=Jobscan Report").is_visible(timeout=3000):
                    print("⚠️ Detected Jobscan Report modal. Dismissing...")
                    await page.locator("text=Dismiss").click()
                    await page.wait_for_timeout(500)
            except Exception as e:
                print(f"⚠️ Failed to dismiss Jobscan Report modal: {e}")

            # 🧹 NEW: General Modal Sweeper
            try:
                modals = page.locator("div[class*='modal'], div[class*='overlay'], .shepherd-modal-overlay-container")
                if await modals.count() > 0 and await modals.first.is_visible():
                    print("🧹 Sweeping visible modals with ESC...")
                    await page.keyboard.press("Escape")
                    await page.wait_for_timeout(1000)
            except Exception as e:
                print(f"⚠️ Modal sweep failed: {e}")

            print("⏳ Waiting for scan results...")

            for attempt in range(6):
                try:
                    await page.wait_for_selector("#score", timeout=10000)
                    break
                except:
                    print(f"⏳ Waiting for score... retry {attempt + 1}")
                    await page.wait_for_timeout(2000)
            else:
                print("❌ ATS score never appeared.")
                return "N/A", [], [], {}

            overlays = [
                page.locator("button:has-text('Dismiss')"),
                page.locator("button:has-text('Got it')"),
                page.locator(".shepherd-modal-overlay-container"),
                page.locator("button:has-text('Accept')"),
            ]
            for overlay in overlays:
                try:
                    if await overlay.count() > 0:
                        print(f"⚠️ Found overlay: {await overlay.first.inner_text()}")
                        await overlay.first.click()
                        await page.wait_for_timeout(300)
                except Exception as e:
                    print(f"⚠️ Failed to dismiss overlay: {e}")

            score = "N/A"
            previous_img = None
            for i in range(20):
                path = "score_section.png"
                await page.locator("#score").screenshot(path=path)
                img_bytes = open(path, "rb").read()
                if i > 0 and img_bytes == previous_img:
                    print(f"✅ Score gauge stabilized after {i} seconds.")
                    break
                previous_img = img_bytes
                await page.wait_for_timeout(1000)

            img = Image.open("score_section.png")
            thresholds = [150, 180, 200]
            upscales = [2, 3, 5, 8]
            psms = [3, 6, 7, 8, 10, 11, 13]

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
                            match = re.search(r"(\d{1,3})%", text)
                            if match:
                                score = match.group(0)
                                print(f"[OCR SUCCESS] Extracted ATS Score: {score}")
                                break
                        if score != "N/A": break
                    if score != "N/A": break
                if score != "N/A": break

            if score == "N/A":
                fallback_text = pytesseract.image_to_string(img).strip()
                match = re.search(r"(\d{1,3})%", fallback_text)
                if match:
                    score = match.group(0)
                    print(f"[OCR SUCCESS - Fallback] Extracted ATS Score: {score}")
                else:
                    print("❌ OCR failed — returning score=0 for ATS retry loop.")
                    score = "0%"

            await page.evaluate("""
                document.querySelectorAll("div[class*='tooltip'], div[role='dialog'], .shepherd-modal-overlay-container")
                .forEach(el => el.style.display = 'none');
            """)
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
            await page.wait_for_timeout(1500)
            print("✅ Hidden tooltip/popups before PDF render.")

            _, sections = await extract_ats_feedback(page)

            await page.wait_for_timeout(1000)
            await page.pdf(path="jobscan_full_rendered.pdf", format="A4", print_background=True)
            missed_skills = extract_skills_from_pdf("jobscan_full_rendered.pdf")
            keywords = missed_skills["hard_skills"] + missed_skills["soft_skills"]

            if OCR_DEBUG:
                print("📋 Raw PDF skill dump:")
                for k, v in missed_skills.items():
                    print(f"  - {k}: {v}")
                with open("jobscan_debug_output.log", "w") as f:
                    f.write(f"Score: {score}\n")
                    f.write(f"Missing Keywords: {keywords}\n")
                    f.write(f"Missing Sections: {sections}\n")
                    f.write(f"Extracted Skills: {missed_skills}\n")

            if isinstance(score, str) and score.endswith('%'):
                score = score.replace('%', '')
            try:
                score_int = int(score)
            except ValueError:
                score_int = 0

            return score_int, keywords, sections, missed_skills

        except Exception as e:
            print(f"[ERROR] Jobscan flow failed: {e}")
            await page.screenshot(path="fail_generic.png")
            return "N/A", [], [], {}
        finally:
            await browser.close()

def get_jobscan_score(resume_text, jd_text):
    return asyncio.run(run_jobscan(resume_text, jd_text))

def get_jobscan_score_and_feedback(resume_text, jd_text):
    score, keywords, sections, _ = asyncio.run(run_jobscan(resume_text, jd_text))
    return score, keywords, sections

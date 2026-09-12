import os
import re
import time
import google.generativeai as genai
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()

LEETCODE_USERNAME = os.getenv("LEETCODE_USERNAME")
LEETCODE_PASSWORD = os.getenv("LEETCODE_PASSWORD")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

def get_solution_from_gemini(title, description, lang="python3"):
    prompt = f"""
You are an expert competitive programmer.
Solve this LeetCode problem and return ONLY the solution code, no explanation.

Problem Title: {title}

Problem Description:
{description}

Language: {lang}

Return only the function/class code that LeetCode expects. No markdown, no backticks.
"""
    response = model.generate_content(prompt)
    return response.text.strip()

def login_leetcode(page):
    print("🔐 Navigating to LeetCode login...")
    page.goto("https://leetcode.com/accounts/login/", wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle", timeout=15000)

    print(f"📄 Current URL: {page.url}")
    print(f"📄 Page title: {page.title()}")

    # Try multiple selectors for username
    username_selectors = [
        "input#id_login",
        "input[name='login']",
        "input[autocomplete='username']",
        "input[name='username']",
        "input[placeholder*='username' i]",
        "input[placeholder*='email' i]",
        "input[type='text']",
    ]

    username_input = None
    for selector in username_selectors:
        try:
            el = page.locator(selector).first
            if el.count() > 0 and el.is_visible():
                username_input = el
                print(f"✅ Found username field: {selector}")
                break
        except:
            continue

    if username_input is None:
        # Save screenshot for debugging
        page.screenshot(path="login-debug.png", full_page=True)
        print("❌ Could not find username field. Page content:")
        print(page.content()[:2000])
        raise RuntimeError("Login form not found")

    # Fill credentials
    username_input.click()
    username_input.fill(LEETCODE_USERNAME)

    password_selectors = [
        "input#id_password",
        "input[name='password']",
        "input[type='password']",
    ]
    for selector in password_selectors:
        try:
            el = page.locator(selector).first
            if el.count() > 0 and el.is_visible():
                el.fill(LEETCODE_PASSWORD)
                print(f"✅ Found password field: {selector}")
                break
        except:
            continue

    # Submit
    submit_selectors = [
        "button[type='submit']",
        "button:has-text('Sign in')",
        "button:has-text('Log in')",
        "input[type='submit']",
    ]
    for selector in submit_selectors:
        try:
            el = page.locator(selector).first
            if el.count() > 0 and el.is_visible():
                el.click()
                print(f"✅ Clicked submit: {selector}")
                break
        except:
            continue

    # Wait for redirect after login
    time.sleep(5)
    page.wait_for_load_state("networkidle", timeout=15000)
    print(f"✅ Logged in! Current URL: {page.url}")

def run_agent():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
        ])
        context = browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )
        page = context.new_page()

        # Login
        login_leetcode(page)

        # Step 2: Fetch daily challenge via GraphQL
        print("📅 Fetching Daily Challenge...")
        page.goto("https://leetcode.com/problemset/", wait_until="domcontentloaded")
        time.sleep(3)

        daily_data = page.evaluate("""
            async () => {
                const res = await fetch('/graphql', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        query: `{
                            activeDailyCodingChallengeQuestion {
                                date
                                link
                                question {
                                    title
                                    titleSlug
                                    content
                                    difficulty
                                }
                            }
                        }`
                    })
                });
                const data = await res.json();
                return data.data.activeDailyCodingChallengeQuestion;
            }
        """)

        title = daily_data['question']['title']
        slug = daily_data['question']['titleSlug']
        content = daily_data['question']['content']
        difficulty = daily_data['question']['difficulty']
        link = "https://leetcode.com" + daily_data['link']

        print(f"📝 Today's Problem: {title} [{difficulty}]")

        # Step 3: Get solution from Gemini
        print("🤖 Getting solution from Gemini...")
        clean_content = re.sub('<[^<]+?>', '', content)
        solution = get_solution_from_gemini(title, clean_content)
        print("✅ Solution generated!")
        print("--- Solution Preview ---")
        print(solution[:300])
        print("------------------------")

        # Step 4: Open problem page
        print(f"🌐 Opening: {link}")
        page.goto(link, wait_until="domcontentloaded")
        time.sleep(5)

        # Step 5: Set language to Python3
        try:
            page.wait_for_selector("[data-cy='lang-select'], button:has-text('Python')", timeout=8000)
            lang_btn = page.locator("button:has-text('Python3')").first
            if not lang_btn.is_visible():
                lang_selector = page.locator("[data-cy='lang-select']").first
                if lang_selector.is_visible():
                    lang_selector.click()
                    time.sleep(1)
                    page.locator("text=Python3").first.click()
                    time.sleep(1)
            print("✅ Language: Python3")
        except Exception as e:
            print(f"⚠️ Language selector: {e}")

        # Step 6: Paste solution
        print("📋 Pasting solution...")
        try:
            editor = page.locator(".view-lines").first
            editor.click()
            time.sleep(1)
            page.keyboard.press("Control+a")
            time.sleep(0.5)
            page.keyboard.type(solution)
            time.sleep(2)
            print("✅ Solution pasted!")
        except Exception as e:
            print(f"⚠️ Editor: {e}")

        # Step 7: Submit
        print("🚀 Submitting...")
        try:
            submit_btn = page.locator("button:has-text('Submit')").last
            submit_btn.click()
            time.sleep(10)

            result = page.locator(".text-green-s, [data-e2e-locator='submission-result']").first
            if result.is_visible():
                print(f"🎉 Result: {result.inner_text()}")
            else:
                print("⏳ Submission sent — check LeetCode for result")
        except Exception as e:
            print(f"⚠️ Submit: {e}")

        browser.close()
        print("✅ Done! Streak maintained 🔥")

if __name__ == "__main__":
    run_agent()

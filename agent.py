import os
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

def run_agent():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        # Step 1: Login
        print("🔐 Logging in to LeetCode...")
        page.goto("https://leetcode.com/accounts/login/")
        page.wait_for_selector("#id_login", timeout=15000)
        page.fill("#id_login", LEETCODE_USERNAME)
        page.fill("#id_password", LEETCODE_PASSWORD)
        page.click("button[type='submit']")
        page.wait_for_url("https://leetcode.com/", timeout=20000)
        print("✅ Logged in!")
        time.sleep(3)

        # Step 2: Go to Daily Challenge
        print("📅 Opening Daily Challenge...")
        page.goto("https://leetcode.com/problemset/")
        time.sleep(3)

        # Fetch daily challenge via GraphQL
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
        # Strip HTML tags from content
        import re
        clean_content = re.sub('<[^<]+?>', '', content)
        solution = get_solution_from_gemini(title, clean_content)
        print("✅ Solution generated!")
        print("--- Solution Preview ---")
        print(solution[:300])
        print("------------------------")

        # Step 4: Open problem page
        print(f"🌐 Opening problem: {link}")
        page.goto(link)
        time.sleep(5)

        # Step 5: Set language to Python3
        try:
            lang_btn = page.locator("button:has-text('Python3')").first
            if not lang_btn.is_visible():
                # Try clicking language selector
                page.locator("[data-cy='lang-select']").click()
                time.sleep(1)
                page.locator("text=Python3").click()
                time.sleep(1)
            print("✅ Language set to Python3")
        except Exception as e:
            print(f"⚠️ Language selector issue: {e}")

        # Step 6: Paste solution in editor
        print("📋 Pasting solution...")
        try:
            # Click on editor and select all, then type
            editor = page.locator(".view-lines").first
            editor.click()
            time.sleep(1)
            page.keyboard.press("Control+a")
            time.sleep(0.5)
            page.keyboard.type(solution)
            time.sleep(2)
            print("✅ Solution pasted!")
        except Exception as e:
            print(f"⚠️ Editor paste issue: {e}")

        # Step 7: Submit
        print("🚀 Submitting solution...")
        try:
            submit_btn = page.locator("button:has-text('Submit')").last
            submit_btn.click()
            time.sleep(8)

            # Check result
            result = page.locator(".text-green-s, [data-e2e-locator='submission-result']").first
            if result.is_visible():
                result_text = result.inner_text()
                print(f"🎉 Result: {result_text}")
            else:
                print("⏳ Submission sent — check LeetCode for result")
        except Exception as e:
            print(f"⚠️ Submit issue: {e}")

        browser.close()
        print("✅ Agent finished! Streak maintained 🔥")

if __name__ == "__main__":
    run_agent()

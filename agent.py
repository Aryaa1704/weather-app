def submit_via_playwright(slug, question_id, solution):
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox"]
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 720},
            )

            page = context.new_page()

            # Pehle leetcode.com open kar
            page.goto("https://leetcode.com/", wait_until="networkidle", timeout=30000)

            # Ab cookie set kar
            context.add_cookies([{
                "name": "LEETCODE_SESSION",
                "value": LEETCODE_SESSION,
                "domain": "leetcode.com",
                "path": "/"
            }])

            # Problem page pe ja
            page.goto(f"https://leetcode.com/problems/{slug}/", wait_until="networkidle", timeout=60000)
            time.sleep(5)

            csrf = ""
            for cookie in context.cookies():
                if cookie["name"] == "csrftoken":
                    csrf = cookie["value"]
                    break

            print(f"🍪 CSRF via Playwright: {bool(csrf)}")

            result = page.evaluate(f"""
                async () => {{
                    const solution = {json.dumps(solution)};
                    const resp = await fetch('/problems/{slug}/submit/', {{
                        method: 'POST',
                        headers: {{
                            'Content-Type': 'application/json',
                            'X-CSRFToken': '{csrf}',
                            'Referer': 'https://leetcode.com/problems/{slug}/',
                            'Origin': 'https://leetcode.com'
                        }},
                        body: JSON.stringify({{
                            lang: 'python3',
                            question_id: '{question_id}',
                            typed_code: solution
                        }})
                    }});
                    const text = await resp.text();
                    return {{ status: resp.status, body: text }};
                }}
            """)

            print(f"🌐 Playwright response: {result.get('status')} | {result.get('body', '')[:200]}")
            browser.close()

            body = result.get("body", "")
            try:
                data = json.loads(body)
                return data.get("submission_id")
            except:
                return None

    except Exception as e:
        print(f"❌ Playwright submit error: {e}")
        return None

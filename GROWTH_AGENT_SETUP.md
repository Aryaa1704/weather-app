# LeetCode Profile Growth Agent setup

This is an additive extension. It does not replace agent.py or the existing daily/keepalive workflows.

## 1. Required repository secrets

Open Settings -> Secrets and variables -> Actions -> New repository secret.

Required:
- LEETCODE_USERNAME: your exact LeetCode username.
- LEETCODE_SESSION: your current LeetCode session cookie.

The existing AI provider secrets used by agent.py are reused for community article drafts:
- GEMINI_API_KEY
- GROQ_API_KEY
- NVIDIA_API_KEY
- CEREBRAS_API_KEY
- SAMBANOVA_API_KEY
- MISTRAL_API_KEY
- OPENROUTER_API_KEY
- CLOUDFLARE_API_TOKEN
- CLOUDFLARE_ACCOUNT_ID
- HF_TOKEN

Telegram is optional but required for Telegram alerts:
- TELEGRAM_BOT_TOKEN: create a bot with Telegram's official BotFather and copy its token.
- TELEGRAM_CHAT_ID: send the bot a message, then obtain your chat ID from the bot updates endpoint. Keep both values private.

Do not put cookies, tokens, or API keys in source files or commit them.

## 2. What runs

- Scheduled daily at 08:00 India Standard Time (02:30 UTC).
- Can also be started manually from Actions -> LeetCode Profile Growth Agent -> Run workflow.
- Writes profile statistics and a contest report to the GitHub Actions run summary.
- Sends Telegram notifications when Telegram secrets are configured.
- Checks contests starting in the next 48 hours and links to the official contest page. Registration remains manual.
- Attempts to create a Markdown article draft from a recent accepted Python submission.
- Uploads community_drafts as a workflow artifact for 14 days.

## 3. Community publishing approval

Download the leetcode-community-drafts artifact from the successful workflow run. Read and correct the explanation, dry run, complexity, and code. Publish manually from your LeetCode account only after verifying it. This workflow never publishes a post or fabricates engagement.

## 4. Contest safety

The agent is a reminder and tracking tool. Register manually and solve/submit contest problems yourself. Do not use AI-generated answers or automated submissions during a live contest.

## 5. First-run checklist

1. Merge the pull request into main after reviewing it.
2. Add/verify the repository secrets above.
3. Open Actions and enable workflows if GitHub prompts you.
4. Run LeetCode Profile Growth Agent manually once.
5. Inspect the profile report, contest reminder output, Telegram delivery, and community draft artifact.
6. For GitHub notifications, watch the repository and enable Actions/workflow notifications in GitHub notification settings. Failed workflow runs are also visible in the Actions tab.

If LeetCode changes its undocumented GraphQL fields, the profile or submission-draft step may need maintenance. Contest schedule lookup is also based on LeetCode's public contest endpoint.

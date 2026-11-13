# Dutch A1 drill (Telegram + GitHub Actions)

- **Morning:** 10 words or phrases with pronunciation and English.
- **Evening:** the same 10 as tap-to-answer quiz polls.
- **Sunday:** a mini-test of everything you missed that week, English → Dutch.

Right answers move a word to longer gaps (1, 2, 4, 8, 16 days). A wrong answer brings it back the next day.

## Setup (about 10 minutes)

1. **Create the bot.** In Telegram, open **@BotFather**, send `/newbot`, pick a name, and copy the token it gives you.
2. **Create a private GitHub repo** and upload everything in this folder, including the `.github` folder.
3. **Add the token.** In the repo: Settings → Secrets and variables → Actions → New repository secret. Name it `TELEGRAM_BOT_TOKEN` and paste the token.
4. **Say hello.** Open your new bot in Telegram and send `/start`.
5. **First run.** In the repo: Actions → Dutch drill → Run workflow → `lesson`. You should get a welcome message and your first 10 words.

After that it runs by itself.

## Good to know

- The bot belongs to the first chat that messages it. Do step 4 before step 5.
- Answers are read a few times a day, not instantly, but each quiz shows the right answer straight away.
- GitHub can start scheduled runs 10 to 30 minutes late.
- Times are set in UTC in `.github/workflows/drill.yml`, so messages arrive an hour later in summer.
- To add vocabulary, add rows to `words.csv` (`dutch|pronunciation|english|example|example in English`).
- `state.json` is your progress. Delete it to start over.

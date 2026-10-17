<div align="center">

# AI Discord Support Agent

**Free AI Discord Support bot, powered by OpenRouter free models**

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![discord.py](https://img.shields.io/badge/discord.py-2.4%2B-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discordpy.readthedocs.io/)
[![OpenRouter](https://img.shields.io/badge/OpenRouter-free%20models-6566F1?style=for-the-badge&logo=openai&logoColor=white)](https://openrouter.ai/)
[![Cost](https://img.shields.io/badge/cost-%240-brightgreen?style=for-the-badge)](#-free-models-only)
[![Multilingual](https://img.shields.io/badge/replies%20in-any%20language-orange?style=for-the-badge&logo=googletranslate&logoColor=white)](#-features)

</div>

---

## Quickstart

### 1. Create the Discord bot

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications) → **New Application** → **Bot**.
2. Enable **Message Content Intent** under *Privileged Gateway Intents*.
3. Copy the bot token.
4. Invite it with the `bot` scope and these permissions: **Send Messages**, **Read Message History**, **Add Reactions**.

### 2. Get an OpenRouter key

Create a free key at [openrouter.ai/keys](https://openrouter.ai/keys).

### 3. Install and run

```bash
pip install -r requirements.txt
```

Create a `.env` file next to `bot.py`:

```env
DISCORD_TOKEN=your-discord-bot-token
OPENROUTER_API_KEY=sk-or-v1-...
SUPPORT_CHANNEL_IDS=123456789012345678
```

```bash
python bot.py
```

### When does the bot respond?

-  Any message in a **support channel** (`SUPPORT_CHANNEL_IDS`)
-  When it's **@mentioned**
-  When someone **replies** to one of its messages
-  In **DMs**

##  Teaching the bot

Edit `knowledge.md`. It is the bot's **only source of truth**, so it won't make up links or policies that aren't there.

> [!NOTE]
> Free models have daily rate limits and can sometimes be slow or unavailable. Fallback models in `MODELS` help a lot.


import asyncio
import logging
import os
import re
from pathlib import Path

import aiohttp
import discord
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
OPENROUTER_API_KEY = os.environ["OPENROUTER_API_KEY"]
MODELS = [m.strip() for m in os.getenv("MODELS", "openrouter/free").split(",") if m.strip()]
SUPPORT_CHANNEL_IDS = {
    int(c) for c in os.getenv("SUPPORT_CHANNEL_IDS", "").split(",") if c.strip()
}
FREE_MODELS_ONLY = os.getenv("FREE_MODELS_ONLY", "true").strip().lower() not in ("0", "false", "no", "off")
HISTORY_LIMIT = int(os.getenv("HISTORY_LIMIT", "12"))
KNOWLEDGE_FILE = Path(os.getenv("KNOWLEDGE_FILE", "knowledge.md"))

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DISCORD_MAX_LEN = 2000
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "2000"))

THINK_RE = re.compile(r"<think>.*?(</think>|$)", re.S | re.I)
REACT_RE = re.compile(r"\[REACT\]\**\s*(\S+)?", re.I)
IGNORE_RE = re.compile(r"\[IGNORE\]", re.I)

log = logging.getLogger("support-bot")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def is_free_model(model: str) -> bool:
    return model == "openrouter/free" or model.endswith(":free")


if not MODELS:
    raise SystemExit("MODELS is empty.")
if FREE_MODELS_ONLY:
    bad = [m for m in MODELS if not is_free_model(m)]
    if bad:
        raise SystemExit(
            f"Only free models are allowed ('openrouter/free' or '*:free'). Rejected: {bad}. "
            "Set FREE_MODELS_ONLY=false to allow paid models."
        )

SYSTEM_PROMPT = """You are {bot_name}, the support assistant of a Discord server.

## Personality
Helpful but efficient. Short, direct, friendly. No filler, no long greetings, no repeating the question.
Use 1-3 sentences unless the user truly needs steps. Never invent facts, links or policies.

## Language
Always answer in the same language the user wrote their last message in.

## Server knowledge (your only source of truth)
{knowledge}

## Rules
- If the question belongs to another server/game/company listed in the knowledge, redirect them with the link and make clear we are not associated with them.
- If you don't know and it's in scope, say so briefly and point to human staff.
- You are reading a channel transcript. Lines are prefixed with the author's name.

## Output format (strict)
Reply with EXACTLY one of:
1. Your message text (no name prefix).
2. `[REACT] <one emoji>` - when the message only needs acknowledgement (thanks, ok, got it, solved). Prefer 👍.
3. `[IGNORE]` - when the latest message is not for you (people chatting among themselves, off-topic banter that needs no answer).
"""


def load_knowledge() -> str:
    try:
        return KNOWLEDGE_FILE.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        log.warning("Knowledge file %s not found", KNOWLEDGE_FILE)
        return "(no server info provided)"


def split_message(text: str, limit: int = DISCORD_MAX_LEN) -> list[str]:
    chunks = []
    while len(text) > limit:
        cut = text.rfind("\n", 0, limit)
        if cut <= 0:
            cut = text.rfind(" ", 0, limit)
        if cut <= 0:
            cut = limit
        chunks.append(text[:cut])
        text = text[cut:].lstrip()
    if text:
        chunks.append(text)
    return chunks


class SupportBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents, allowed_mentions=discord.AllowedMentions.none())
        self.http_session: aiohttp.ClientSession | None = None
        self.channel_locks: dict[int, asyncio.Lock] = {}

    async def setup_hook(self):
        self.http_session = aiohttp.ClientSession(
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "X-Title": "Discord Support Bot",
            },
            timeout=aiohttp.ClientTimeout(total=90),
        )

    async def close(self):
        if self.http_session:
            await self.http_session.close()
        await super().close()

    async def on_ready(self):
        log.info("Logged in as %s (models: %s, free only: %s)", self.user, ", ".join(MODELS), FREE_MODELS_ONLY)

    def should_handle(self, message: discord.Message) -> bool:
        if message.author.bot or not message.content.strip():
            return False
        if isinstance(message.channel, discord.DMChannel):
            return True
        if self.user in message.mentions:
            return True
        ref = message.reference
        if ref and isinstance(ref.resolved, discord.Message) and ref.resolved.author == self.user:
            return True
        return message.channel.id in SUPPORT_CHANNEL_IDS

    async def build_messages(self, message: discord.Message) -> list[dict]:
        system = SYSTEM_PROMPT.format(bot_name=self.user.display_name, knowledge=load_knowledge())
        msgs = [{"role": "system", "content": system}]

        history = [m async for m in message.channel.history(limit=HISTORY_LIMIT, before=message)]
        for m in reversed(history):
            if not m.content.strip():
                continue
            if m.author == self.user:
                msgs.append({"role": "assistant", "content": m.content})
            elif not m.author.bot:
                msgs.append({"role": "user", "content": f"{m.author.display_name}: {m.clean_content}"})

        msgs.append({"role": "user", "content": f"{message.author.display_name}: {message.clean_content}"})
        return msgs

    async def ask_llm(self, messages: list[dict]) -> str | None:
        payload = {"model": MODELS[0], "messages": messages, "max_tokens": MAX_TOKENS, "temperature": 0.4}
        if len(MODELS) > 1:
            payload["models"] = MODELS

        for attempt in range(3):
            try:
                async with self.http_session.post(OPENROUTER_URL, json=payload) as resp:
                    data = await resp.json(content_type=None)
                    if resp.status == 429 or resp.status >= 500:
                        log.warning("OpenRouter %s (attempt %d): %s", resp.status, attempt + 1, data)
                        await asyncio.sleep(2 ** attempt * 2)
                        continue
                    if resp.status != 200:
                        log.error("OpenRouter %s: %s", resp.status, data)
                        return None
                    choice = data["choices"][0]
                    content = THINK_RE.sub("", choice["message"].get("content") or "").strip()
                    log.info(
                     #  you can add the below line to log content
                     #  "Answered with %s (finish_reason=%s): %r",
                        "Answered with %s (finish_reason=%s)",
                        data.get("model"), choice.get("finish_reason"), content[:200],
                    )
                    if content:
                        return content
                    log.warning("Empty content (attempt %d), retrying", attempt + 1)
            except (aiohttp.ClientError, asyncio.TimeoutError, KeyError, IndexError) as e:
                log.warning("OpenRouter request failed (attempt %d): %r", attempt + 1, e)
                await asyncio.sleep(2 ** attempt * 2)
        return None

    async def on_message(self, message: discord.Message):
        if not self.should_handle(message):
            return

        lock = self.channel_locks.setdefault(message.channel.id, asyncio.Lock())
        async with lock:
            messages = await self.build_messages(message)
            async with message.channel.typing():
                reply = await self.ask_llm(messages)

            if not reply:
                await message.reply(
                    "Sorry, I couldn't process that right now. Please try again in a moment.",
                    mention_author=False,
                )
                return

            await self.dispatch_reply(message, reply)

    async def dispatch_reply(self, message: discord.Message, reply: str):
        if IGNORE_RE.search(reply) and len(reply) < 40:
            log.info("Ignoring message %s", message.id)
            return

        react = REACT_RE.search(reply)
        if react and len(reply) < 40:
            emoji = react.group(1) or "👍"
            try:
                await message.add_reaction(emoji)
            except discord.HTTPException:
                await message.add_reaction("👍")
            return

        reply = IGNORE_RE.sub("", REACT_RE.sub("", reply)).strip()
        reply = re.sub(rf"^(You|{re.escape(self.user.display_name)}):\s*", "", reply, flags=re.I)
        if not reply:
            return

        for i, chunk in enumerate(split_message(reply)):
            if i == 0:
                await message.reply(chunk, mention_author=False)
            else:
                await message.channel.send(chunk)


if __name__ == "__main__":
    SupportBot().run(DISCORD_TOKEN, log_handler=None)
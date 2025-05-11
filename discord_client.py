import discord
from dotenv import load_dotenv
import os

load_dotenv()

BOT_TOKEN = os.environ.get("DISCORD_TOKEN")
CHANNEL_ID = os.environ.get("DISCORD_CHANNEL_ID")


async def get_discord_client() -> discord.Client:
    intents = discord.Intents.default()
    client = discord.Client(intents=intents)

    await client.login(BOT_TOKEN)

    @client.event
    async def send(message: str) -> None:
        channel = await client.fetch_channel(CHANNEL_ID)
        if channel:
            await channel.send(message)

    return client

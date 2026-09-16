"""
database.py
------------
MongoDB connection (Motor - async) and helper functions to read/write
per-guild configuration, warns, and notes.

Collections:
  - guild_config   -> general bot configuration per server (bot-setup)
  - welcome_config -> welcome system configuration per server
  - warns          -> auto-mod / staff warnings
  - notes          -> internal moderator notes about users
"""

import os
import motor.motor_asyncio

MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "discord_bot")

_client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
db = _client[MONGO_DB_NAME]

guild_config_col = db["guild_config"]
welcome_config_col = db["welcome_config"]
warns_col = db["warns"]
notes_col = db["notes"]


# ---------------------------------------------------------------------------
# General bot configuration (bot-setup)
# ---------------------------------------------------------------------------

DEFAULT_GUILD_CONFIG = {
    "staff_roles": [],
    "admin_roles": [],
    "automod_log_channel": None,
    "automod_enabled": True,
}


async def get_guild_config(guild_id: int) -> dict:
    data = await guild_config_col.find_one({"_id": guild_id})
    if not data:
        data = {"_id": guild_id, **DEFAULT_GUILD_CONFIG}
        await guild_config_col.insert_one(data)
    else:
        # Aseguramos que si agregamos nuevos campos en el futuro, existan
        changed = False
        for k, v in DEFAULT_GUILD_CONFIG.items():
            if k not in data:
                data[k] = v
                changed = True
        if changed:
            await guild_config_col.update_one({"_id": guild_id}, {"$set": data})
    return data


async def update_guild_config(guild_id: int, fields: dict):
    await guild_config_col.update_one(
        {"_id": guild_id}, {"$set": fields}, upsert=True
    )


# ---------------------------------------------------------------------------
# Welcome system configuration
# ---------------------------------------------------------------------------

DEFAULT_WELCOME_CONFIG = {
    "enabled": False,
    "channel_id": None,
    "embed_color": 0x2B2D31,
    "ping_user": True,
    "image_url": None,
    "footer_text": None,
    "use_embed": True,
    "title": "¡Bienvenido/a {user}!",
    "description": "Nos alegra tenerte en **{server}**.\nYa somos **{member_count}** miembros.",
    "links": [],  # lista de {"label": str, "url": str}
}


async def get_welcome_config(guild_id: int) -> dict:
    data = await welcome_config_col.find_one({"_id": guild_id})
    if not data:
        data = {"_id": guild_id, **DEFAULT_WELCOME_CONFIG}
        await welcome_config_col.insert_one(data)
    else:
        changed = False
        for k, v in DEFAULT_WELCOME_CONFIG.items():
            if k not in data:
                data[k] = v
                changed = True
        if changed:
            await welcome_config_col.update_one({"_id": guild_id}, {"$set": data})
    return data


async def update_welcome_config(guild_id: int, fields: dict):
    await welcome_config_col.update_one(
        {"_id": guild_id}, {"$set": fields}, upsert=True
    )


# ---------------------------------------------------------------------------
# Warns
# ---------------------------------------------------------------------------

async def add_warn(guild_id: int, user_id: int, moderator_id: int, reason: str) -> int:
    """Adds a warn and returns the total number of active warns for the user."""
    doc = {
        "guild_id": guild_id,
        "user_id": user_id,
        "moderator_id": moderator_id,
        "reason": reason,
    }
    result = await warns_col.insert_one(doc)
    doc["_id"] = result.inserted_id
    count = await warns_col.count_documents({"guild_id": guild_id, "user_id": user_id})
    return count


async def get_warns(guild_id: int, user_id: int) -> list:
    cursor = warns_col.find({"guild_id": guild_id, "user_id": user_id}).sort("_id", 1)
    return await cursor.to_list(length=None)


async def remove_warn_by_index(guild_id: int, user_id: int, index: int) -> bool:
    """Removes warn N (1-based, following the order shown by ?warnings)."""
    warns = await get_warns(guild_id, user_id)
    if index < 1 or index > len(warns):
        return False
    target = warns[index - 1]
    await warns_col.delete_one({"_id": target["_id"]})
    return True


async def clear_warns(guild_id: int, user_id: int):
    await warns_col.delete_many({"guild_id": guild_id, "user_id": user_id})


# ---------------------------------------------------------------------------
# Notes
# ---------------------------------------------------------------------------

async def add_note(guild_id: int, user_id: int, moderator_id: int, content: str):
    await notes_col.insert_one(
        {
            "guild_id": guild_id,
            "user_id": user_id,
            "moderator_id": moderator_id,
            "content": content,
        }
    )


async def get_notes(guild_id: int, user_id: int) -> list:
    cursor = notes_col.find({"guild_id": guild_id, "user_id": user_id}).sort("_id", 1)
    return await cursor.to_list(length=None)


async def remove_note_by_index(guild_id: int, user_id: int, index: int) -> bool:
    notes = await get_notes(guild_id, user_id)
    if index < 1 or index > len(notes):
        return False
    target = notes[index - 1]
    await notes_col.delete_one({"_id": target["_id"]})
    return True

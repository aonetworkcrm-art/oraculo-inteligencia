"""
╔══════════════════════════════════════════════════════════════╗
║  TELEGRAM SCRAPER — Telethon-powered Channel Intelligence   ║
║  Scrape real credential combos from Telegram channels/groups ║
║  Usa Telethon (MTProto) — sin Google, sin proxies externos  ║
╚══════════════════════════════════════════════════════════════╝
"""
import os
import re
import json
import time
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from telethon import TelegramClient, events, errors
from telethon.tl.functions.messages import SearchRequest
from telethon.tl.types import InputMessagesFilterEmpty

from combo_leecher_engine import ComboParser, ComboEntry

logger = logging.getLogger("TelegramScraper")

# ─── Config from env ───
API_ID = os.environ.get("TG_API_ID", "")
API_HASH = os.environ.get("TG_API_HASH", "")
SESSION_NAME = os.environ.get("TG_SESSION", "oraculo_tg_session")

# ─── Known credential leak channels (can be extended) ───
KNOWN_LEAK_CHANNELS = [
    # Combos / leaks (some may be dead — the scraper handles errors gracefully)
    "combolist_official",
    "leakbase",
    "leakzone_official",
    "credentialleaks",
    "databreaches",
    "leakdatabase",
    "combosource",
    "leaksource",
    "comboxx_official",
    "hackforums_leaks",
    "darkweb_leaks",
    "email_pass_leaks",
    "combo_zone",
]

# ─── Common keywords to search in Telegram ───
SEARCH_KEYWORDS = [
    "email:pass", "user:pass", "combo", "leak", "dump",
    "password", "credentials", "login", "breach",
    "combolist", "email:password",
]


class TelethonScraper:
    """
    Telegram scraper using Telethon (MTProto API).
    
    Requires:
    - TG_API_ID and TG_API_HASH env vars (from my.telegram.org)
    - Optional TG_SESSION for session persistence
    
    Features:
    - Search messages in known leak channels
    - Auto-discover channels via keyword search
    - Real-time message monitoring via event handlers
    - Graceful error handling (channels may be dead/private)
    - Rate limiting to avoid bans
    - Parses email:pass combos from messages
    """

    def __init__(self):
        self.api_id = API_ID
        self.api_hash = API_HASH
        self.session_name = SESSION_NAME
        self.client: Optional[TelegramClient] = None
        self.parser = ComboParser()
        self._connected = False
        self._channel_cache: Dict[str, str] = {}  # username -> id
        self.stats = {
            "messages_scanned": 0,
            "combos_found": 0,
            "channels_accessible": 0,
            "channels_dead": 0,
        }

    @property
    def enabled(self) -> bool:
        """Check if Telethon credentials are configured."""
        return bool(self.api_id and self.api_hash)

    async def connect(self) -> bool:
        """Connect to Telegram MTProto."""
        if not self.enabled:
            logger.warning("❌ Telegram: TG_API_ID and TG_API_HASH not set")
            return False

        if self._connected:
            return True

        try:
            self.client = TelegramClient(self.session_name, int(self.api_id), self.api_hash)
            await self.client.connect()

            if not await self.client.is_user_authorized():
                logger.warning("⚠️ Telegram: Not authorized. Need phone number or session file")
                logger.info("   Run 'python telegram_scraper.py --login' to authenticate")
                return False

            me = await self.client.get_me()
            logger.info(f"✅ Telegram connected as @{me.username or me.id}")
            self._connected = True
            return True

        except Exception as e:
            logger.error(f"❌ Telegram connection error: {e}")
            return False

    async def disconnect(self):
        """Disconnect from Telegram."""
        if self.client and self._connected:
            await self.client.disconnect()
            self._connected = False
            logger.info("🔌 Telegram disconnected")

    async def search_channel_messages(
        self,
        channel: str,
        keyword: str,
        limit: int = 50,
        max_age_days: int = 30,
    ) -> List[Dict[str, Any]]:
        """
        Search messages in a specific channel for a keyword.
        
        Args:
            channel: Channel username (without @)
            keyword: Search term
            limit: Max messages to retrieve
            max_age_days: Only messages from last N days
        
        Returns:
            List of message dicts with text, date, sender
        """
        if not self._connected:
            logger.warning("⚠️ Telegram not connected")
            return []

        results = []
        try:
            entity = await self.client.get_entity(channel)
            self.stats["channels_accessible"] += 1

            # Calculate date offset
            offset_date = datetime.now() - timedelta(days=max_age_days)

            # Search messages
            async for msg in self.client.iter_messages(
                entity,
                limit=limit,
                search=keyword,
                offset_date=offset_date,
            ):
                if msg.text:
                    results.append({
                        "id": msg.id,
                        "text": msg.text[:5000],  # Limit size
                        "date": msg.date.isoformat() if msg.date else "",
                        "sender_id": msg.sender_id,
                        "channel": channel,
                    })
                    self.stats["messages_scanned"] += 1

            logger.debug(f"📨 {channel}: {len(results)} messages for '{keyword}'")

        except errors.ChannelPrivateError:
            logger.debug(f"🔒 {channel}: channel is private")
            self.stats["channels_dead"] += 1
        except errors.UsernameNotOccupiedError:
            logger.debug(f"❌ {channel}: username not found")
            self.stats["channels_dead"] += 1
        except errors.FloodWaitError as e:
            logger.warning(f"⏳ Flood wait: {e.seconds}s — sleeping...")
            await asyncio.sleep(e.seconds + 5)
            # Retry once
            try:
                entity = await self.client.get_entity(channel)
                async for msg in self.client.iter_messages(
                    entity, limit=limit, search=keyword,
                    offset_date=datetime.now() - timedelta(days=max_age_days),
                ):
                    if msg.text:
                        results.append({
                            "id": msg.id,
                            "text": msg.text[:5000],
                            "date": msg.date.isoformat() if msg.date else "",
                            "sender_id": msg.sender_id,
                            "channel": channel,
                        })
                        self.stats["messages_scanned"] += 1
            except Exception:
                pass
        except Exception as e:
            logger.debug(f"⚠️ {channel}: {e}")

        return results

    async def scrape_keyword(
        self,
        keyword: str,
        channels: Optional[List[str]] = None,
        max_per_channel: int = 30,
        max_age_days: int = 30,
    ) -> List[ComboEntry]:
        """
        Main scraping method — search Telegram for credential combos.
        
        Args:
            keyword: Search term (e.g., "comcast", "netflix")
            channels: Specific channels to search (None = all known)
            max_per_channel: Max messages per channel
            max_age_days: Recency filter
        
        Returns:
            List of ComboEntry objects
        """
        if not await self.connect():
            return []

        if channels is None:
            channels = KNOWN_LEAK_CHANNELS

        all_combos = []
        seen_sources = set()

        # Search in known channels
        for channel in channels:
            messages = await self.search_channel_messages(
                channel, keyword,
                limit=max_per_channel, max_age_days=max_age_days,
            )

            for msg in messages:
                text = msg.get("text", "")
                if not text:
                    continue

                combos = self.parser.parse_text(
                    text,
                    source_url=f"https://t.me/{channel}/{msg.get('id', '')}",
                    source_type="telegram_telethon",
                    keyword=keyword,
                )

                for combo in combos:
                    source_key = f"{combo.email}:{combo.password}"
                    if source_key not in seen_sources:
                        seen_sources.add(source_key)
                        all_combos.append(combo)

            # Rate limiting between channels
            await asyncio.sleep(1)

        self.stats["combos_found"] += len(all_combos)
        logger.info(f"💬 Telegram (Telethon): {len(all_combos)} combos for '{keyword}'")
        return all_combos

    async def discover_channels(self, keyword: str, max_channels: int = 5) -> List[str]:
        """
        Auto-discover Telegram channels related to a keyword.
        Uses Telegram's global search to find relevant channels.
        
        Args:
            keyword: Search term
            max_channels: Max channels to return
        
        Returns:
            List of channel usernames
        """
        if not await self.connect():
            return KNOWN_LEAK_CHANNELS[:max_channels]

        discovered = []
        try:
            # Search globally
            result = await self.client(
                SearchRequest(
                    peer="username",  # Global search
                    q=keyword,
                    filter=InputMessagesFilterEmpty(),
                    min_date=None,
                    max_date=None,
                    offset_id=0,
                    add_offset=0,
                    limit=10,
                    max_id=0,
                    min_id=0,
                    hash=0,
                )
            )

            # Extract channel info from results
            chats = getattr(result, "chats", [])
            for chat in chats[:max_channels]:
                username = getattr(chat, "username", None)
                if username and username not in discovered:
                    title = getattr(chat, "title", username)
                    participants = getattr(chat, "participants_count", 0)
                    logger.debug(f"📢 Discovered channel: @{username} ({title}) — {participants} members")
                    discovered.append(username)

        except errors.FloodWaitError as e:
            logger.warning(f"⏳ Flood wait on channel discovery: {e.seconds}s")
        except Exception as e:
            logger.debug(f"Channel discovery error: {e}")

        # Fallback to known channels
        if not discovered:
            discovered = KNOWN_LEAK_CHANNELS[:max_channels]

        return discovered

    def get_stats(self) -> Dict[str, Any]:
        """Get scraping statistics."""
        return {
            **self.stats,
            "enabled": self.enabled,
            "connected": self._connected,
            "api_id_configured": bool(self.api_id),
            "known_channels": len(KNOWN_LEAK_CHANNELS),
        }


# ═══════════════════════════════════════════════════════════════
#  SYNC WRAPPER — for use with Flask/api.py
# ═══════════════════════════════════════════════════════════════

class TelegramIntelScraper:
    """
    Synchronous wrapper around TelethonScraper.
    Uses asyncio.run() for sync callers (Flask endpoints).
    """

    def __init__(self):
        self._scraper = TelethonScraper()
        self._cache: Dict[str, tuple] = {}  # keyword -> (timestamp, combos)
        self._cache_ttl = 300  # 5 min cache

    @property
    def enabled(self) -> bool:
        return self._scraper.enabled

    def scrape(self, keyword: str, channels: Optional[List[str]] = None,
               max_per_channel: int = 20) -> List[ComboEntry]:
        """Sync wrapper for scrape_keyword."""
        # Check cache
        cached = self._cache.get(keyword)
        if cached and (time.time() - cached[0]) < self._cache_ttl:
            logger.info(f"📦 Telegram cache HIT for '{keyword}'")
            return cached[1]

        try:
            combos = asyncio.run(
                self._scraper.scrape_keyword(
                    keyword, channels=channels, max_per_channel=max_per_channel
                )
            )
            # Update cache
            self._cache[keyword] = (time.time(), combos)
            return combos
        except Exception as e:
            logger.error(f"❌ Telegram scrape error: {e}")
            return []

    def get_stats(self) -> Dict[str, Any]:
        """Get scraper stats."""
        return self._scraper.get_stats()


# ═══════════════════════════════════════════════════════════════
#  CLI TOOL
# ═══════════════════════════════════════════════════════════════

def cli_login():
    """Run interactive login to create session file."""
    import asyncio

    async def _login():
        client = TelegramClient(SESSION_NAME, int(API_ID), API_HASH)
        await client.start()
        me = await client.get_me()
        print(f"\n✅ Logged in as @{me.username or me.id}")
        print(f"📁 Session saved to: {SESSION_NAME}.session")
        await client.disconnect()

    if not API_ID or not API_HASH:
        print("❌ Set TG_API_ID and TG_API_HASH environment variables first!")
        print("   Get them from https://my.telegram.org/apps")
        return

    asyncio.run(_login())


def cli_search():
    """Search for combos from command line."""
    import sys
    import argparse
    
    parser = argparse.ArgumentParser(description="Telegram Leak Scraper")
    parser.add_argument("keyword", help="Keyword to search (e.g., comcast)")
    parser.add_argument("--channels", "-c", nargs="*", help="Specific channels")
    parser.add_argument("--limit", "-l", type=int, default=20, help="Messages per channel")
    parser.add_argument("--login", action="store_true", help="Login to Telegram")
    parser.add_argument("--discover", action="store_true", help="Discover channels for keyword")
    args = parser.parse_args()

    if args.login:
        cli_login()
        return

    scraper = TelegramIntelScraper()

    if args.discover:
        print(f"\n🔍 Discovering channels for '{args.keyword}'...")
        channels = asyncio.run(TelethonScraper().discover_channels(args.keyword))
        print(f"\n📢 Found {len(channels)} channels:")
        for ch in channels:
            print(f"   @{ch}")
        return

    if not scraper.enabled:
        print("❌ Telegram not configured. Set TG_API_ID and TG_API_HASH.")
        print("   Get them from https://my.telegram.org/apps")
        print("   Then run: python telegram_scraper.py --login")
        return

    print(f"\n💬 Searching Telegram for '{args.keyword}'...")
    print(f"   Channels: {args.channels or KNOWN_LEAK_CHANNELS[:5]}")
    print(f"   Max per channel: {args.limit}")
    print("=" * 50)

    combos = scraper.scrape(args.keyword, channels=args.channels, max_per_channel=args.limit)

    print(f"\n✅ Found {len(combos)} combos:")
    for combo in combos[:20]:
        pw_hidden = combo.password[:10] + "***" if len(combo.password) > 10 else combo.password
        print(f"   📧 {combo.email:<40} : {pw_hidden:<15} [{combo.domain}]")

    if len(combos) > 20:
        print(f"\n   ... and {len(combos) - 20} more")

    # Save to file
    if combos:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = f"data/telegram_combos_{args.keyword}_{ts}.txt"
        os.makedirs("data", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            for c in combos:
                f.write(f"{c.email}:{c.password}  #{c.domain} | {c.source_type}\n")
        print(f"\n💾 Saved to: {path}")

    print(f"\n📊 Stats: {scraper.get_stats()}")


if __name__ == "__main__":
    cli_search()

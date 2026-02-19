#!/usr/bin/env python3
"""Discord Admin CLI — Claude Codeが叩くDiscord管理コマンド集

使い方:
  cd /home/ebi/discord-bot
  uv run python scripts/discord_admin.py list-threads
  uv run python scripts/discord_admin.py delete-threads --dry-run
  uv run python scripts/discord_admin.py delete-threads --older-than 7
  uv run python scripts/discord_admin.py delete-threads --all
  uv run python scripts/discord_admin.py delete-thread THREAD_ID
  uv run python scripts/discord_admin.py channel-info CHANNEL_ID
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import aiohttp
from dotenv import load_dotenv

# .envを読む（discord-botルートディレクトリ基準）
load_dotenv(Path(__file__).parent.parent / ".env")

DISCORD_API = "https://discord.com/api/v10"
TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
CHANNEL_ID = os.getenv("CLAUDE_CHANNEL_ID") or os.getenv("DISCORD_CHANNEL_ID", "")


def make_headers() -> dict[str, str]:
    if not TOKEN:
        print("ERROR: DISCORD_BOT_TOKEN が設定されていません", file=sys.stderr)
        sys.exit(1)
    return {
        "Authorization": f"Bot {TOKEN}",
        "Content-Type": "application/json",
    }


# ─────────────────────────────────────────────────
# Discord ID → 作成日時の変換
# Discord Snowflake: 上位42bitがエポック（2015-01-01）からのms
# ─────────────────────────────────────────────────
DISCORD_EPOCH = 1420070400000  # 2015-01-01T00:00:00Z ms


def snowflake_to_datetime(snowflake_id: int | str) -> datetime:
    ts_ms = (int(snowflake_id) >> 22) + DISCORD_EPOCH
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)


async def handle_rate_limit(response: aiohttp.ClientResponse) -> None:
    """レートリミット（429）のとき指定秒数待つ"""
    if response.status == 429:
        data = await response.json()
        retry_after = float(data.get("retry_after", 1.0))
        print(f"  ⏳ Rate limit — {retry_after:.1f}秒待機...")
        await asyncio.sleep(retry_after)


# ─────────────────────────────────────────────────
# API呼び出しヘルパー
# ─────────────────────────────────────────────────

async def get_channel(session: aiohttp.ClientSession, channel_id: str) -> dict:
    async with session.get(f"{DISCORD_API}/channels/{channel_id}") as r:
        r.raise_for_status()
        return await r.json()


async def get_active_threads(session: aiohttp.ClientSession, guild_id: str) -> list[dict]:
    """ギルド内のアクティブなスレッドをすべて取得"""
    async with session.get(f"{DISCORD_API}/guilds/{guild_id}/threads/active") as r:
        r.raise_for_status()
        data = await r.json()
        return data.get("threads", [])


async def get_archived_threads(
    session: aiohttp.ClientSession,
    channel_id: str,
    private: bool = False,
) -> list[dict]:
    """アーカイブ済みスレッドをページネーションで全件取得"""
    path = "private" if private else "public"
    threads: list[dict] = []
    before: str | None = None

    while True:
        params = {"limit": 100}
        if before:
            params["before"] = before

        async with session.get(
            f"{DISCORD_API}/channels/{channel_id}/threads/archived/{path}",
            params=params,
        ) as r:
            if r.status == 403:
                # プライベートスレッドにアクセスできない場合はスキップ
                break
            r.raise_for_status()
            data = await r.json()

        batch = data.get("threads", [])
        threads.extend(batch)

        if not data.get("has_more", False):
            break

        # 最後のスレッドのIDを次のbeforeに使う
        if batch:
            before = batch[-1]["id"]
        else:
            break

    return threads


async def delete_channel(
    session: aiohttp.ClientSession,
    channel_id: str,
    name: str = "",
    dry_run: bool = False,
) -> bool:
    """スレッド（チャンネル）を削除。dry_runのときはスキップ"""
    label = name or channel_id
    if dry_run:
        print(f"  [DRY-RUN] 削除をスキップ: {label}")
        return True

    # リトライループ（レートリミット対応）
    for attempt in range(5):
        async with session.delete(f"{DISCORD_API}/channels/{channel_id}") as r:
            if r.status == 429:
                await handle_rate_limit(r)
                continue
            if r.status in (200, 204):
                print(f"  ✅ 削除: {label}")
                return True
            if r.status == 404:
                print(f"  ⚠️  既に存在しない: {label}")
                return True
            if r.status == 403:
                print(f"  ❌ 権限なし: {label}")
                return False
            print(f"  ❌ エラー {r.status}: {label}")
            return False
        break

    return False


# ─────────────────────────────────────────────────
# コマンド実装
# ─────────────────────────────────────────────────

async def cmd_channel_info(channel_id: str) -> None:
    """チャンネル情報を表示（guild_idの確認などに使う）"""
    async with aiohttp.ClientSession(headers=make_headers()) as session:
        info = await get_channel(session, channel_id)

    print(f"チャンネル情報:")
    print(f"  ID       : {info['id']}")
    print(f"  Name     : {info.get('name', '(thread)')}")
    print(f"  Type     : {info.get('type')}")
    print(f"  Guild ID : {info.get('guild_id', '不明')}")
    print(f"  Parent   : {info.get('parent_id', 'なし')}")


async def cmd_list_threads(channel_id: str) -> None:
    """指定チャンネル配下のスレッドを一覧表示"""
    async with aiohttp.ClientSession(headers=make_headers()) as session:
        # guild_idをチャンネル情報から取得
        ch_info = await get_channel(session, channel_id)
        guild_id = ch_info.get("guild_id")
        if not guild_id:
            print("ERROR: guild_id が取得できません", file=sys.stderr)
            return

        # アクティブスレッド
        active = await get_active_threads(session, guild_id)
        # このチャンネルの子スレッドだけ絞り込む
        active = [t for t in active if t.get("parent_id") == channel_id]

        # アーカイブ済みスレッド（public + private）
        archived_pub = await get_archived_threads(session, channel_id, private=False)
        archived_priv = await get_archived_threads(session, channel_id, private=True)

    all_threads = active + archived_pub + archived_priv

    print(f"\n📌 チャンネル: {ch_info.get('name', channel_id)}")
    print(f"   アクティブ: {len(active)} / アーカイブ(public): {len(archived_pub)} / アーカイブ(private): {len(archived_priv)}")
    print(f"   合計: {len(all_threads)} スレッド\n")

    for t in sorted(all_threads, key=lambda x: int(x["id"]), reverse=True):
        created = snowflake_to_datetime(t["id"])
        age_days = (datetime.now(tz=timezone.utc) - created).days
        archived = "🗂" if t.get("thread_metadata", {}).get("archived") else "💬"
        print(f"  {archived} [{age_days:3d}日前] {t.get('name', '(無題)')[:60]}  (id: {t['id']})")


async def cmd_delete_threads(
    channel_id: str,
    older_than_days: int | None,
    delete_all: bool,
    keep_newest: int | None,
    dry_run: bool,
) -> None:
    """スレッドを条件付きで一括削除"""
    if not delete_all and older_than_days is None and keep_newest is None:
        print("ERROR: --all / --older-than N / --keep-newest N のいずれかを指定してください", file=sys.stderr)
        sys.exit(1)

    async with aiohttp.ClientSession(headers=make_headers()) as session:
        ch_info = await get_channel(session, channel_id)
        guild_id = ch_info.get("guild_id")
        if not guild_id:
            print("ERROR: guild_id が取得できません", file=sys.stderr)
            return

        print(f"📡 スレッド取得中...")
        active = await get_active_threads(session, guild_id)
        active = [t for t in active if t.get("parent_id") == channel_id]
        archived_pub = await get_archived_threads(session, channel_id, private=False)
        archived_priv = await get_archived_threads(session, channel_id, private=True)

        all_threads = active + archived_pub + archived_priv
        print(f"   合計 {len(all_threads)} スレッド発見")

        # フィルタリング
        now = datetime.now(tz=timezone.utc)

        # --keep-newest: IDの大きい順にN件を保持リストに入れ、残りを削除対象にする
        if keep_newest is not None:
            sorted_by_newest = sorted(all_threads, key=lambda t: int(t["id"]), reverse=True)
            keep_ids = {t["id"] for t in sorted_by_newest[:keep_newest]}
            targets = [t for t in all_threads if t["id"] not in keep_ids]
            print(f"   保持（最新{keep_newest}件）:")
            for t in sorted_by_newest[:keep_newest]:
                print(f"     ✅ {t.get('name', '(無題)')[:60]}")
        else:
            keep_ids = set()
            targets = []
            for t in all_threads:
                if delete_all:
                    targets.append(t)
                elif older_than_days is not None:
                    created = snowflake_to_datetime(t["id"])
                    age_days = (now - created).days
                    if age_days >= older_than_days:
                        targets.append(t)

        print(f"   削除対象: {len(targets)} スレッド")
        if dry_run:
            print("   ⚠️  DRY-RUN モード — 実際には削除しません\n")
        else:
            print()

        # 削除実行
        success = 0
        fail = 0
        for t in targets:
            name = t.get("name", "(無題)")
            created = snowflake_to_datetime(t["id"])
            age_days = (now - created).days
            print(f"  [{age_days:3d}日前] {name[:50]}")
            ok = await delete_channel(session, t["id"], name=name, dry_run=dry_run)
            if ok:
                success += 1
            else:
                fail += 1
            # レートリミットを避けるため少し待つ
            if not dry_run:
                await asyncio.sleep(0.5)

    print(f"\n{'[DRY-RUN] ' if dry_run else ''}完了: {success} 削除, {fail} 失敗")


async def cmd_delete_thread(thread_id: str) -> None:
    """指定スレッドを1件削除"""
    async with aiohttp.ClientSession(headers=make_headers()) as session:
        ok = await delete_channel(session, thread_id, name=thread_id)
    if not ok:
        sys.exit(1)


# ─────────────────────────────────────────────────
# エントリーポイント
# ─────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Discord Admin CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    # channel-info
    p_info = sub.add_parser("channel-info", help="チャンネル情報表示")
    p_info.add_argument("channel_id", nargs="?", default=CHANNEL_ID)

    # list-threads
    p_list = sub.add_parser("list-threads", help="スレッド一覧表示")
    p_list.add_argument("--channel", default=CHANNEL_ID, dest="channel_id")

    # delete-threads
    p_del = sub.add_parser("delete-threads", help="スレッド一括削除")
    p_del.add_argument("--channel", default=CHANNEL_ID, dest="channel_id")
    p_del.add_argument("--older-than", type=int, metavar="DAYS",
                       help="N日以上前のスレッドを削除")
    p_del.add_argument("--all", action="store_true", dest="delete_all",
                       help="全スレッドを削除")
    p_del.add_argument("--keep-newest", type=int, metavar="N",
                       help="最新N件を残して残りを削除")
    p_del.add_argument("--dry-run", action="store_true",
                       help="実際には削除しない（確認用）")

    # delete-thread
    p_one = sub.add_parser("delete-thread", help="スレッドを1件削除")
    p_one.add_argument("thread_id")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.cmd == "channel-info":
        asyncio.run(cmd_channel_info(args.channel_id or CHANNEL_ID))
    elif args.cmd == "list-threads":
        asyncio.run(cmd_list_threads(args.channel_id))
    elif args.cmd == "delete-threads":
        asyncio.run(cmd_delete_threads(
            channel_id=args.channel_id,
            older_than_days=args.older_than,
            keep_newest=args.keep_newest,
            delete_all=args.delete_all,
            dry_run=args.dry_run,
        ))
    elif args.cmd == "delete-thread":
        asyncio.run(cmd_delete_thread(args.thread_id))


if __name__ == "__main__":
    main()

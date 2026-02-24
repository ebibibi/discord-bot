#!/usr/bin/env python3
"""Obsidian 02_Projects ↔ Discord スレッド同期スクリプト

1プロジェクト1スレッドの状態を作り、ノートのfrontmatterに discord_thread_id を記録する。

使い方:
  cd /home/ebi/discord-bot
  uv run python scripts/sync_projects.py --dry-run   # 確認のみ
  uv run python scripts/sync_projects.py             # 実行
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from pathlib import Path

import aiohttp
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

DISCORD_API = "https://discord.com/api/v10"
TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
CHANNEL_ID = os.getenv("CLAUDE_CHANNEL_ID") or os.getenv("DISCORD_CHANNEL_ID", "")
GUILD_ID = os.getenv("DISCORD_GUILD_ID", "")
OWNER_ID = os.getenv("DISCORD_OWNER_ID", "")

PROJECTS_DIR = Path("/home/ebi/scheduler/obsidian/02_Projects")

# 同期対象外のファイル名
SKIP_FILES = {"_about.md"}


def make_headers() -> dict[str, str]:
    if not TOKEN:
        print("ERROR: DISCORD_BOT_TOKEN が設定されていません", file=sys.stderr)
        sys.exit(1)
    return {"Authorization": f"Bot {TOKEN}", "Content-Type": "application/json"}


def collect_projects() -> list[dict]:
    """02_Projects フォルダからプロジェクト情報を収集する。

    フォルダ型: フォルダ名と同名の .md がインデックスノート
    ファイル型: .md ファイル直接
    """
    projects = []
    for item in sorted(PROJECTS_DIR.iterdir()):
        if item.name.startswith("."):
            continue
        if item.is_dir():
            # フォルダ型: フォルダ名と同名の .md を探す
            index_md = item / f"{item.name}.md"
            if index_md.exists():
                projects.append({
                    "name": item.name,
                    "note_path": index_md,
                })
            else:
                # インデックスがないフォルダはスキップ
                print(f"  ⚠ フォルダ {item.name} にインデックスノートなし → スキップ")
        elif item.is_file() and item.suffix == ".md":
            if item.name in SKIP_FILES:
                continue
            projects.append({
                "name": item.stem,
                "note_path": item,
            })
    return projects


def read_frontmatter(note_path: Path) -> tuple[dict, str]:
    """ノートのfrontmatter(dict)と本文(str)を返す。"""
    content = note_path.read_text(encoding="utf-8")
    if not content.startswith("---"):
        return {}, content

    end = content.find("---", 3)
    if end == -1:
        return {}, content

    fm_str = content[3:end]
    body = content[end + 3:]

    # シンプルなYAMLパース（pyyamlなしで対応）
    fm: dict = {}
    for line in fm_str.splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            fm[key.strip()] = val.strip()

    return fm, body


def write_frontmatter(note_path: Path, fm: dict, body: str) -> None:
    """frontmatterをノートに書き戻す。"""
    lines = []
    for key, val in fm.items():
        if val:
            lines.append(f"{key}: {val}")
        else:
            lines.append(f"{key}:")

    fm_str = "\n".join(lines)
    new_content = f"---\n{fm_str}\n---{body}"
    note_path.write_text(new_content, encoding="utf-8")


def add_discord_thread_id_to_note(note_path: Path, thread_id: str) -> None:
    """ノートのfrontmatterに discord_thread_id を追加 or 更新する。"""
    fm, body = read_frontmatter(note_path)

    if not fm:
        # frontmatterなし → 新規作成
        content = note_path.read_text(encoding="utf-8")
        new_content = f"---\ndiscord_thread_id: {thread_id}\n---\n{content}"
        note_path.write_text(new_content, encoding="utf-8")
    else:
        fm["discord_thread_id"] = thread_id
        write_frontmatter(note_path, fm, body)


async def get_guild_id(session: aiohttp.ClientSession) -> str:
    """チャンネル情報からGuild IDを取得する。"""
    async with session.get(
        f"{DISCORD_API}/channels/{CHANNEL_ID}",
        headers=make_headers(),
    ) as r:
        if r.status != 200:
            print(f"  ERROR: チャンネル情報取得失敗 {r.status}")
            return ""
        data = await r.json()
        return data.get("guild_id", "")


async def get_active_threads(session: aiohttp.ClientSession, guild_id: str) -> list[dict]:
    """Guild内のアクティブスレッドを全取得。"""
    async with session.get(
        f"{DISCORD_API}/guilds/{guild_id}/threads/active",
        headers=make_headers(),
    ) as r:
        if r.status != 200:
            text = await r.text()
            print(f"  ERROR: スレッド取得失敗 {r.status}: {text[:200]}")
            return []
        data = await r.json()
        return data.get("threads", [])


async def create_thread(session: aiohttp.ClientSession, name: str) -> dict | None:
    """Discord にスレッドを作成する（スターターメッセージなし）。"""
    payload = {
        "name": name[:100],  # Discord: 最大100文字
        "type": 11,  # GUILD_PUBLIC_THREAD
        "auto_archive_duration": 10080,  # 7日
    }
    async with session.post(
        f"{DISCORD_API}/channels/{CHANNEL_ID}/threads",
        headers=make_headers(),
        json=payload,
    ) as r:
        if r.status in (200, 201):
            return await r.json()
        text = await r.text()
        print(f"  ERROR: スレッド作成失敗 '{name}': {r.status} - {text[:200]}")
        return None


async def post_init_message(session: aiohttp.ClientSession, thread_id: str, project_name: str) -> bool:
    """スレッドにコンテキスト初期化メッセージを投稿する。

    /clear で前のセッション履歴を消去し、recall-context で最新状態に復元する。
    """
    message = f"/clear\n{project_name}に関して思い出して"
    async with session.post(
        f"{DISCORD_API}/channels/{thread_id}/messages",
        headers=make_headers(),
        json={"content": message},
    ) as r:
        if r.status in (200, 201):
            return True
        text = await r.text()
        print(f"  ERROR: メッセージ投稿失敗 (thread {thread_id}): {r.status} - {text[:200]}")
        return False


# 自動生成スレッドのプレフィックス（マッチング対象外）
AUTO_THREAD_PREFIXES = ("[scheduled]", "🔄 ", "[scheduled] ")


def is_auto_thread(thread: dict) -> bool:
    """自動生成スレッド（Scheduled/docs-sync等）を除外する。"""
    name_lower = thread["name"].lower()
    return any(name_lower.startswith(p.lower()) for p in AUTO_THREAD_PREFIXES)


def match_thread(project_name: str, threads: list[dict]) -> dict | None:
    """プロジェクト名と既存スレッドを名前で照合する。

    自動生成スレッドは除外し、意味のある照合のみを行う。
    """
    # 自動スレッドを除外した候補リスト
    candidates = [t for t in threads if not is_auto_thread(t)]

    name_lower = project_name.lower()

    # 完全一致優先
    for t in candidates:
        if t["name"].lower() == name_lower:
            return t

    # 部分一致: プロジェクト名の先頭12文字以上がスレッド名に含まれる
    prefix_len = min(12, len(name_lower))
    prefix = name_lower[:prefix_len]
    if prefix_len >= 8:
        for t in candidates:
            thread_lower = t["name"].lower()
            # スレッド名が長すぎる（100文字超）場合は除外（誤マッチ防止）
            if len(t["name"]) > 60:
                continue
            if prefix in thread_lower:
                return t

    # スレッド名（12文字以上）がプロジェクト名に含まれる
    for t in candidates:
        thread_lower = t["name"].lower()
        if len(t["name"]) > 60:
            continue
        if len(thread_lower) >= 8 and thread_lower in name_lower:
            return t

    return None


async def sync(dry_run: bool, reinit: bool = False) -> None:
    """プロジェクトとDiscordスレッドを同期する。

    reinit=True のとき、既存スレッドにもコンテキスト初期化メッセージを投稿する。
    """
    projects = collect_projects()
    print(f"\n📁 プロジェクト数: {len(projects)}")
    if reinit:
        print("🔄 --reinit モード: 既存スレッドにもコンテキスト初期化メッセージを投稿します")

    async with aiohttp.ClientSession() as session:
        guild_id = await get_guild_id(session)
        if not guild_id:
            print("ERROR: Guild IDが取得できませんでした")
            return
        threads = await get_active_threads(session, guild_id)
        # claudecodeチャンネルのスレッドのみに絞る
        channel_threads = [t for t in threads if t.get("parent_id") == CHANNEL_ID]
        print(f"💬 既存スレッド数（claudecodeチャンネル）: {len(channel_threads)}")

        results = []

        for proj in projects:
            name = proj["name"]
            note_path = proj["note_path"]

            # 既にfrontmatterにthread_idがあれば確認
            fm, _ = read_frontmatter(note_path)
            existing_id = fm.get("discord_thread_id", "")

            if existing_id:
                # 既存IDが有効なスレッドか確認
                matched = next((t for t in channel_threads if t["id"] == existing_id), None)
                if matched:
                    if reinit and not dry_run:
                        print(f"  🔄 [{name}] → 既存スレッド '{matched['name']}' にコンテキスト初期化メッセージを投稿")
                        await post_init_message(session, existing_id, name)
                        await asyncio.sleep(0.5)
                        results.append({"project": name, "action": "reinited", "thread_id": existing_id})
                    elif reinit and dry_run:
                        print(f"  🔄 [{name}] → [dry-run] 既存スレッド '{matched['name']}' へ投稿予定")
                        results.append({"project": name, "action": "would_reinit", "thread_id": existing_id})
                    else:
                        print(f"  ✅ [{name}] → 既存スレッド '{matched['name']}' (ID: {existing_id})")
                        results.append({"project": name, "action": "existing", "thread_id": existing_id})
                    continue
                else:
                    print(f"  ⚠ [{name}] → frontmatterにID {existing_id} あるがスレッドが見つからない → 再マッチング")

            # 名前でマッチング
            matched_thread = match_thread(name, channel_threads)
            if matched_thread:
                thread_id = matched_thread["id"]
                thread_name = matched_thread["name"]
                print(f"  🔗 [{name}] → 既存スレッド '{thread_name}' (ID: {thread_id}) にマッチ")
                if not dry_run:
                    add_discord_thread_id_to_note(note_path, thread_id)
                results.append({"project": name, "action": "matched", "thread_id": thread_id, "thread_name": thread_name})
            else:
                # 新規スレッド作成
                print(f"  ➕ [{name}] → 新規スレッド作成")
                if not dry_run:
                    thread = await create_thread(session, name)
                    if thread:
                        thread_id = thread["id"]
                        add_discord_thread_id_to_note(note_path, thread_id)
                        print(f"      → 作成完了 ID: {thread_id}")
                        await asyncio.sleep(0.5)
                        ok = await post_init_message(session, thread_id, name)
                        if ok:
                            print(f"      → コンテキスト初期化メッセージを投稿しました")
                        results.append({"project": name, "action": "created", "thread_id": thread_id})
                    else:
                        results.append({"project": name, "action": "failed"})
                else:
                    results.append({"project": name, "action": "would_create"})

            # Rate limit対策
            if not dry_run:
                await asyncio.sleep(0.5)

        # サマリー
        print("\n📊 サマリー:")
        existing = sum(1 for r in results if r["action"] == "existing")
        matched = sum(1 for r in results if r["action"] == "matched")
        created = sum(1 for r in results if r["action"] == "created")
        would_create = sum(1 for r in results if r["action"] == "would_create")
        reinited = sum(1 for r in results if r["action"] == "reinited")
        would_reinit = sum(1 for r in results if r["action"] == "would_reinit")
        failed = sum(1 for r in results if r["action"] == "failed")

        print(f"  既存（変更なし）: {existing}")
        print(f"  マッチ（既存スレッド）: {matched}")
        if dry_run:
            print(f"  作成予定: {would_create}")
            if reinit:
                print(f"  初期化メッセージ投稿予定: {would_reinit}")
        else:
            print(f"  新規作成（＋初期化メッセージ投稿）: {created}")
            if reinit:
                print(f"  コンテキスト再初期化: {reinited}")
            print(f"  失敗: {failed}")

        if dry_run:
            print("\n⚠️  dry-run モード。--dry-run を外すと実行されます。")


def get_project_thread_ids() -> set[str]:
    """ObsidianノートのfrontmatterからプロジェクトスレッドIDを全収集する。"""
    thread_ids: set[str] = set()
    for root, _dirs, files in os.walk(PROJECTS_DIR):
        for fname in files:
            if not fname.endswith(".md") or fname == "_about.md":
                continue
            fpath = Path(root) / fname
            content = fpath.read_text(encoding="utf-8")
            m = re.search(r"discord_thread_id:\s*(\S+)", content)
            if m:
                thread_ids.add(m.group(1))
    return thread_ids


async def join_project_threads(dry_run: bool) -> None:
    """プロジェクトスレッド全件にオーナーをメンバー追加する（サイドバーに表示させる）。"""
    if not OWNER_ID:
        print("ERROR: DISCORD_OWNER_ID が設定されていません")
        return

    thread_ids = get_project_thread_ids()
    print(f"\n👤 オーナー追加対象: {len(thread_ids)} スレッド (OWNER_ID: {OWNER_ID})")

    async with aiohttp.ClientSession() as session:
        ok = 0
        for tid in sorted(thread_ids):
            if dry_run:
                print(f"  [dry-run] PUT thread-members/{OWNER_ID} → {tid}")
                ok += 1
                continue
            for attempt in range(4):
                async with session.put(
                    f"{DISCORD_API}/channels/{tid}/thread-members/{OWNER_ID}",
                    headers=make_headers(),
                ) as r:
                    if r.status == 204:
                        print(f"  ✅ {tid}")
                        ok += 1
                        break
                    elif r.status == 429:
                        data = await r.json()
                        wait = data.get("retry_after", 2.0) + 0.2
                        print(f"  ⏳ rate limit, {wait:.1f}s 待機 (attempt {attempt+1})")
                        await asyncio.sleep(wait)
                    else:
                        text = await r.text()
                        print(f"  ❌ {tid}: {r.status} {text[:100]}")
                        break
            await asyncio.sleep(0.5)

    print(f"\n完了: {ok}/{len(thread_ids)}")
    if dry_run:
        print("⚠️  dry-run モード。--dry-run を外すと実行されます。")


async def cleanup_threads(dry_run: bool) -> None:
    """プロジェクトスレッド以外を全削除する。"""
    project_ids = get_project_thread_ids()
    print(f"\n🧹 保護スレッド数: {len(project_ids)}")

    async with aiohttp.ClientSession() as session:
        guild_id = await get_guild_id(session)
        if not guild_id:
            print("ERROR: Guild IDが取得できませんでした")
            return

        all_threads = await get_active_threads(session, guild_id)
        channel_threads = [t for t in all_threads if t.get("parent_id") == CHANNEL_ID]
        targets = [t for t in channel_threads if t["id"] not in project_ids]

        print(f"💬 チャンネル内スレッド: {len(channel_threads)} / 削除対象: {len(targets)}")

        if not targets:
            print("削除対象なし。")
            return

        print("\n削除対象一覧:")
        for t in sorted(targets, key=lambda x: x["id"]):
            print(f"  🗑  [{t['id']}] {t['name'][:60]}")

        if dry_run:
            print(f"\n⚠️  dry-run モード。実際には削除しません。")
            return

        deleted = 0
        for t in targets:
            async with session.delete(
                f"{DISCORD_API}/channels/{t['id']}",
                headers=make_headers(),
            ) as r:
                if r.status in (200, 204):
                    print(f"  ✅ 削除: {t['name'][:50]}")
                    deleted += 1
                elif r.status == 429:
                    data = await r.json()
                    wait = data.get("retry_after", 1.0)
                    print(f"  ⏳ rate limit {wait}s 待機中...")
                    await asyncio.sleep(wait + 0.2)
                    # リトライ
                    async with session.delete(
                        f"{DISCORD_API}/channels/{t['id']}",
                        headers=make_headers(),
                    ) as r2:
                        if r2.status in (200, 204):
                            print(f"  ✅ 削除(retry): {t['name'][:50]}")
                            deleted += 1
                        else:
                            text = await r2.text()
                            print(f"  ❌ 失敗: {t['name'][:50]} ({r2.status})")
                else:
                    text = await r.text()
                    print(f"  ❌ 失敗: {t['name'][:50]} ({r.status})")
            await asyncio.sleep(0.4)

        print(f"\n完了: {deleted}/{len(targets)} 削除")


def main() -> None:
    parser = argparse.ArgumentParser(description="Obsidian Projects ↔ Discord スレッド同期")
    sub = parser.add_subparsers(dest="cmd")

    # sync サブコマンド（デフォルト）
    p_sync = sub.add_parser("sync", help="プロジェクトスレッドを作成・frontmatterを更新")
    p_sync.add_argument("--dry-run", action="store_true")
    p_sync.add_argument(
        "--reinit",
        action="store_true",
        help="既存スレッドにもコンテキスト初期化メッセージ（/clear + 思い出して）を投稿する",
    )

    # join サブコマンド
    p_join = sub.add_parser("join", help="プロジェクトスレッドにオーナーをメンバー追加（サイドバー表示）")
    p_join.add_argument("--dry-run", action="store_true")

    # cleanup サブコマンド
    p_clean = sub.add_parser("cleanup", help="プロジェクト以外のスレッドを全削除")
    p_clean.add_argument("--dry-run", action="store_true")

    # 後方互換: 引数なし or --dry-run のみ → sync 扱い
    parser.add_argument("--dry-run", action="store_true", help="実際には変更しない（syncのデフォルト動作用）")
    parser.add_argument("--reinit", action="store_true", help="既存スレッドにもコンテキスト初期化メッセージを投稿（syncのデフォルト動作用）")

    args = parser.parse_args()

    if args.cmd == "join":
        asyncio.run(join_project_threads(args.dry_run))
    elif args.cmd == "cleanup":
        asyncio.run(cleanup_threads(args.dry_run))
    else:
        dry_run = getattr(args, "dry_run", False)
        reinit = getattr(args, "reinit", False)
        asyncio.run(sync(dry_run, reinit))


if __name__ == "__main__":
    main()

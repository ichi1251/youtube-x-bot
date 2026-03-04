"""
YouTube急上昇動画ピックアップ → Slack確認 → X 自動ポストスクリプト

使い方:
  python main.py --mode draft   # YouTube検索 → Slackに投稿案を送信
  python main.py --mode post    # Slack返信を確認 → Xにポスト
  python main.py --mode direct  # Slack確認なしで直接Xにポスト（旧動作）
  python main.py --dry-run      # どのモードでも実際のAPI呼び出しを行わない
"""
import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Windowsコンソールの文字コード(cp932)が絵文字に対応していないため utf-8 に強制
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv

from youtube_client import YouTubeClient
from x_client import XClient, build_tweet
from slack_client import SlackClient

# ロギング設定
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("run.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

# 返信待ちの投稿案を保存するファイル
PENDING_FILE = Path(__file__).parent / "pending_posts.json"


def load_config(args: argparse.Namespace) -> dict:
    load_dotenv()

    def require(key: str) -> str:
        val = os.getenv(key)
        if not val:
            logger.error(".env に %s が設定されていません", key)
            sys.exit(1)
        return val

    dry_run = args.dry_run or os.getenv("DRY_RUN", "false").lower() == "true"

    # config.json から設定を読み込む
    config_path = Path(__file__).parent / "config.json"
    if not config_path.exists():
        logger.error("config.json が見つかりません")
        sys.exit(1)
    cfg = json.loads(config_path.read_text(encoding="utf-8"))

    WEEKDAY_KEYS = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
    CATEGORY_NAMES = {
        "20": "ゲーム", "22": "人物・ブログ", "23": "コメディ",
        "24": "エンターテイメント", "25": "ニュース・政治",
        "26": "ハウツー・スタイル", "27": "教育",
        "28": "科学・テクノロジー", "29": "社会活動",
    }

    schedule = cfg.get("category_schedule", {})
    today_key = WEEKDAY_KEYS[datetime.now().weekday()]
    if cfg.get("use_category", True) and not args.category:
        category_id = schedule.get(today_key, "28")
    else:
        category_id = args.category or None
    category_name = CATEGORY_NAMES.get(category_id, f"カテゴリ{category_id}") if category_id else "カテゴリなし"

    keywords_raw = args.keywords or ""
    keywords = [k.strip() for k in keywords_raw.split(",") if k.strip()]

    return {
        "youtube_api_key": require("YOUTUBE_API_KEY"),
        "x_api_key": require("X_API_KEY"),
        "x_api_secret": require("X_API_SECRET"),
        "x_access_token": require("X_ACCESS_TOKEN"),
        "x_access_token_secret": require("X_ACCESS_TOKEN_SECRET"),
        "slack_token": os.getenv("SLACK_BOT_TOKEN", ""),
        "slack_channel": os.getenv("SLACK_CHANNEL_ID", ""),
        "keywords": keywords,
        "category_id": category_id,
        "category_name": category_name,
        "today_key": today_key,
        "schedule": schedule,
        "days": cfg.get("search_days", 7),
        "max_results": cfg.get("max_results", 50),
        "top_n": cfg.get("top_n", 3),
        "max_subscriber_count": cfg.get("max_subscriber_count", None),
        "min_duration_seconds": cfg.get("min_duration_seconds", 60),
        "post_interval": cfg.get("post_interval_seconds", 60),
        "post_times": cfg.get("post_times", ["09:00", "12:00", "18:00"]),
        "dry_run": dry_run,
        "mode": args.mode,
    }


# ──────────────────────────────────────────
# draft モード: YouTube検索 → Slackに投稿案を送信
# ──────────────────────────────────────────
def run_draft(config: dict):
    logger.info("=== draft モード開始 ===")

    if not config["slack_token"] or not config["slack_channel"]:
        logger.error(".env に SLACK_BOT_TOKEN / SLACK_CHANNEL_ID が設定されていません")
        sys.exit(1)

    logger.info("本日（%s）のカテゴリ: %s (ID=%s)",
                config["today_key"], config["category_name"], config["category_id"])

    yt = YouTubeClient(config["youtube_api_key"])
    videos = yt.search_videos(
        days=config["days"],
        max_results=config["max_results"],
        keywords=config["keywords"] or None,
        category_id=config["category_id"] if not config["keywords"] else None,
        max_subscriber_count=config["max_subscriber_count"],
        min_duration_seconds=config["min_duration_seconds"],
    )

    if not videos:
        logger.warning("条件に合う動画が見つかりませんでした。終了します。")
        return

    top_videos = videos[:config["top_n"]]
    logger.info("投稿案: %d 件", len(top_videos))

    sc = SlackClient(config["slack_token"], config["slack_channel"])
    post_times = config["post_times"]
    pending = []

    for i, video in enumerate(top_videos, 1):
        draft_text = build_tweet(video)
        slot = i - 1
        post_time = post_times[slot] if slot < len(post_times) else ""

        if config["dry_run"]:
            logger.info("[DRY RUN] Slack送信スキップ。下書き（ポスト予定: %s）:\n%s", post_time, draft_text)
            pending.append({"ts": f"dry_run_{i}", "draft": draft_text,
                            "title": video.title, "time_slot": slot, "post_time": post_time})
            continue

        ts = sc.post_draft(draft_text, index=i, total=len(top_videos), post_time=post_time)
        if ts:
            pending.append({"ts": ts, "draft": draft_text,
                            "title": video.title, "time_slot": slot, "post_time": post_time})

    PENDING_FILE.write_text(json.dumps(pending, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("=== draft 完了: %d 件をSlackに送信 ===", len(pending))
    for p in pending:
        logger.info("  案%d: %s → ポスト予定 %s", p["time_slot"] + 1, p["title"][:30], p["post_time"])
    logger.info("Slackで返信後、各時刻に自動ポストされます")


# ──────────────────────────────────────────
# post モード: 現在時刻に対応するスロットをSlack返信確認 → Xにポスト
# ──────────────────────────────────────────
def run_post(config: dict):
    logger.info("=== post モード開始 ===")

    if not PENDING_FILE.exists():
        logger.error("pending_posts.json が見つかりません。先に --mode draft を実行してください")
        sys.exit(1)

    pending = json.loads(PENDING_FILE.read_text(encoding="utf-8"))
    if not pending:
        logger.info("pending_posts.json が空です。終了します。")
        return

    if not config["slack_token"] or not config["slack_channel"]:
        logger.error(".env に SLACK_BOT_TOKEN / SLACK_CHANNEL_ID が設定されていません")
        sys.exit(1)

    if config["dry_run"]:
        logger.info("[DRY RUN] 返信確認・ポストをスキップ")
        return

    sc = SlackClient(config["slack_token"], config["slack_channel"])
    xc = XClient(
        api_key=config["x_api_key"],
        api_secret=config["x_api_secret"],
        access_token=config["x_access_token"],
        access_token_secret=config["x_access_token_secret"],
    )

    remaining = []
    for item in pending:
        ts = item["ts"]
        draft_text = item["draft"]
        title = item.get("title", "")[:30]

        action, post_text = sc.get_reply_decision(ts, draft_text)

        if action == "skip":
            logger.info("「%s」→ 返信なし、次回に持ち越し", title)
            remaining.append(item)
            continue

        logger.info("「%s」→ 返信あり、Xにポスト", title)
        logger.info("送信テキスト（%d文字）:\n%s", len(post_text), post_text)
        try:
            response = xc.client.create_tweet(text=post_text)
            tweet_id = response.data["id"]
            tweet_url = f"https://x.com/i/web/status/{tweet_id}"
            logger.info("→ ポスト成功: %s", tweet_url)
            sc.post_result_notification(ts, tweet_url=tweet_url, skipped=False)
        except Exception as e:
            logger.error("→ Xポストエラー: %s", e)
            if hasattr(e, 'response') and e.response is not None:
                logger.error("→ エラー詳細: %s", e.response.text)
            sc.post_result_notification(ts, tweet_url=None, skipped=False)
            remaining.append(item)

    PENDING_FILE.write_text(json.dumps(remaining, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("=== post 完了（残り %d 件） ===", len(remaining))


# ──────────────────────────────────────────
# direct モード: Slack確認なしで直接Xにポスト（旧動作）
# ──────────────────────────────────────────
def run_direct(config: dict):
    logger.info("=== direct モード開始 ===")

    logger.info("本日（%s）のカテゴリ: %s (ID=%s)",
                config["today_key"], config["category_name"], config["category_id"])

    yt = YouTubeClient(config["youtube_api_key"])
    videos = yt.search_videos(
        days=config["days"],
        max_results=config["max_results"],
        keywords=config["keywords"] or None,
        category_id=config["category_id"] if not config["keywords"] else None,
    )

    if not videos:
        logger.warning("条件に合う動画が見つかりませんでした。終了します。")
        return

    top_videos = videos[:config["top_n"]]
    xc = XClient(
        api_key=config["x_api_key"],
        api_secret=config["x_api_secret"],
        access_token=config["x_access_token"],
        access_token_secret=config["x_access_token_secret"],
    )

    success_count = 0
    for i, video in enumerate(top_videos):
        ok = xc.post(video, dry_run=config["dry_run"])
        if ok:
            success_count += 1
        if i < len(top_videos) - 1 and not config["dry_run"]:
            logger.info("%d 秒待機...", config["post_interval"])
            time.sleep(config["post_interval"])

    logger.info("=== 完了: %d / %d 件ポスト成功 ===", success_count, len(top_videos))


def main():
    parser = argparse.ArgumentParser(description="YouTube急上昇動画をXにポスト")
    parser.add_argument(
        "--mode",
        choices=["draft", "post", "direct"],
        default="direct",
        help="draft: Slackに案送信 / post: Slack返信確認してXポスト / direct: 直接Xポスト",
    )
    parser.add_argument("--dry-run", action="store_true", help="実際のAPI呼び出しを行わない")
    parser.add_argument("--keywords", type=str, help="カンマ区切りキーワード（カテゴリより優先）")
    parser.add_argument("--category", type=str, help="カテゴリID直接指定（曜日スケジュール上書き）")
    args = parser.parse_args()

    config = load_config(args)
    logger.info("キーワード: %s / 期間: 過去%d日 / モード: %s%s",
                config["keywords"], config["days"], config["mode"],
                " [DRY RUN]" if config["dry_run"] else "")

    if config["mode"] == "draft":
        run_draft(config)
    elif config["mode"] == "post":
        run_post(config)
    else:
        run_direct(config)


if __name__ == "__main__":
    main()

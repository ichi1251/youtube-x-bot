"""
Slack API を使って投稿案の送信・返信取得を行うモジュール。

【動作フロー】
  draft モード: YouTube動画の投稿案をSlackに送信し ts（メッセージID）を返す
  post  モード: スレッド返信を読み取り、承認/修正/スキップを判定して返す

【返信ルール】
  「OK」「ok」「承認」 → 元の下書きをそのままポスト
  その他テキスト       → 返信テキストを先頭に追加して動画情報と合わせてポスト
  返信なし             → スキップ
  「スキップ」「skip」  → スキップ
"""
import re
import logging
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

logger = logging.getLogger(__name__)

APPROVE_WORDS = {"ok", "承認", "よし", "ヨシ", "投稿", "ポスト"}
SKIP_WORDS = {"スキップ", "skip", "ng", "NG", "やめ", "削除"}

_URL_RE = re.compile(r'https?://\S+')
X_MAX_CHARS = 280
X_URL_LENGTH = 23  # XはURLを常に23文字として換算


def x_len(text: str) -> int:
    """X(Twitter)の文字数カウント方式で文字数を返す。
    - URL → 23文字固定
    - BMP外の文字（多くの絵文字）→ 2文字
    - それ以外 → 1文字
    """
    # URLを仮のプレースホルダーに置換してカウント
    url_count = len(_URL_RE.findall(text))
    text_no_url = _URL_RE.sub('', text)
    count = url_count * X_URL_LENGTH
    for ch in text_no_url:
        count += 2 if ord(ch) > 0xFFFF else 1
    return count


class SlackClient:
    def __init__(self, bot_token: str, channel_id: str):
        self.client = WebClient(token=bot_token)
        self.channel_id = channel_id

    def post_draft(self, draft_text: str, index: int, total: int, post_time: str = "") -> str | None:
        """
        Slackに投稿案を送信する。
        post_time: ポスト予定時刻（例: "09:00"）。空文字の場合は非表示。
        Returns: メッセージのタイムスタンプ（ts）。失敗時はNone。
        """
        time_str = f"⏰ ポスト予定: *{post_time}*\n" if post_time else ""
        header = (
            f":pencil: *投稿案 {index}/{total}*　{time_str}"
            f"返信してください\n"
            f"　✅ そのまま投稿　　　→ `OK` と返信\n"
            f"　✏️ 一言追加して投稿　→ 追加テキストを返信（動画情報はそのまま先頭に付加）\n"
            f"　⏭️ スキップ　　　　 → `スキップ` と返信\n"
            f"　（返信なしの場合もスキップになります）\n"
            f"{'─' * 40}"
        )
        full_message = f"{header}\n\n```\n{draft_text}\n```"

        try:
            response = self.client.chat_postMessage(
                channel=self.channel_id,
                text=full_message,
                mrkdwn=True,
            )
            ts = response["ts"]
            logger.info("Slack 投稿案送信完了 (ts=%s): 案 %d/%d", ts, index, total)
            return ts
        except SlackApiError as e:
            logger.error("Slack 送信エラー: %s", e.response["error"])
            return None

    def get_reply_decision(self, ts: str, draft_text: str) -> tuple[str, str]:
        """
        スレッドの最初の返信を読み取り、ポストするテキストとアクションを返す。

        Returns:
            (action, post_text)
            action: "post" | "skip"
            post_text: Xにポストするテキスト（action=="skip"のときは空文字）
        """
        try:
            response = self.client.conversations_replies(
                channel=self.channel_id,
                ts=ts,
            )
            messages = response.get("messages", [])
        except SlackApiError as e:
            logger.error("Slack 返信取得エラー: %s", e.response["error"])
            return "skip", ""

        # messages[0] が元投稿、messages[1] 以降が返信
        replies = [m for m in messages[1:] if not m.get("bot_id")]

        if not replies:
            logger.info("返信なし → スキップ (ts=%s)", ts)
            return "skip", ""

        reply_text = replies[0]["text"].strip()
        lower = reply_text.lower().strip()

        if lower in SKIP_WORDS or any(w in reply_text for w in SKIP_WORDS):
            logger.info("スキップ指示 → スキップ (ts=%s)", ts)
            return "skip", ""

        if lower in APPROVE_WORDS or any(w.lower() == lower for w in APPROVE_WORDS):
            logger.info("承認 → 元の下書きをポスト (ts=%s)", ts)
            return "post", draft_text

        # それ以外は返信テキストを先頭に追加して動画情報と結合
        logger.info("追加テキスト受信 → 先頭に付加してポスト (ts=%s)", ts)
        combined = f"{reply_text}\n\n{draft_text}"
        # X換算で280文字超過の場合は返信テキストを切り詰める
        if x_len(combined) > X_MAX_CHARS:
            draft_x_len = x_len(draft_text) + 2  # "\n\n" 分
            budget = X_MAX_CHARS - draft_x_len - 1  # "…" 分
            trimmed = ""
            count = 0
            for ch in reply_text:
                ch_len = 2 if ord(ch) > 0xFFFF else 1
                if count + ch_len > budget:
                    break
                trimmed += ch
                count += ch_len
            reply_text = (trimmed or reply_text[:10]) + "…"
            combined = f"{reply_text}\n\n{draft_text}"
        logger.info("投稿文字数（X換算）: %d", x_len(combined))
        return "post", combined

    def post_result_notification(self, ts: str, tweet_url: str | None, skipped: bool):
        """ポスト結果をSlackのスレッドに通知する"""
        if skipped:
            text = "⏭️ スキップしました"
        elif tweet_url:
            text = f"✅ Xにポストしました: {tweet_url}"
        else:
            text = "❌ Xへのポストに失敗しました"

        try:
            self.client.chat_postMessage(
                channel=self.channel_id,
                thread_ts=ts,
                text=text,
            )
        except SlackApiError as e:
            logger.error("Slack 結果通知エラー: %s", e.response["error"])

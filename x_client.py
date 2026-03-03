"""
X (Twitter) API v2 を使って動画情報をポストするモジュール。
tweepy + OAuth 1.0a (User Context) で認証。
"""
import logging
import tweepy

from youtube_client import VideoInfo

logger = logging.getLogger(__name__)

# ツイートの最大文字数（URLは23文字固定換算）
MAX_TWEET_LENGTH = 280


def build_tweet(video: VideoInfo) -> str:
    """
    動画情報からツイート本文を生成する。
    280文字に収まるようタイトルを必要に応じて省略する。
    """
    view_str = video.format_number(video.view_count)
    sub_str = video.format_number(video.subscriber_count)
    ratio_str = f"{video.ratio:.1f}"

    # 公開日（YYYY-MM-DD部分だけ取得）
    pub_date = video.published_at[:10]

    body_template = (
        "急上昇動画ピックアップ\n\n"
        "{title}\n\n"
        "ch: {channel}\n"
        "再生数: {views}回\n"
        "登録者数: {subs}人\n"
        "比率: {ratio}倍\n"
        "公開日: {date}\n\n"
        "{url}"
    )

    full_text = body_template.format(
        title=video.title,
        channel=video.channel_name,
        views=view_str,
        subs=sub_str,
        ratio=ratio_str,
        date=pub_date,
        url=video.url,
    )

    # 280文字超過の場合はタイトルを省略
    if len(full_text) > MAX_TWEET_LENGTH:
        max_title_len = len(video.title) - (len(full_text) - MAX_TWEET_LENGTH) - 3
        if max_title_len > 10:
            truncated_title = video.title[:max_title_len] + "…"
        else:
            truncated_title = video.title[:10] + "…"
        full_text = body_template.format(
            title=truncated_title,
            channel=video.channel_name,
            views=view_str,
            subs=sub_str,
            ratio=ratio_str,
            date=pub_date,
            url=video.url,
        )

    return full_text


class XClient:
    def __init__(
        self,
        api_key: str,
        api_secret: str,
        access_token: str,
        access_token_secret: str,
    ):
        self.client = tweepy.Client(
            consumer_key=api_key,
            consumer_secret=api_secret,
            access_token=access_token,
            access_token_secret=access_token_secret,
        )

    def post(self, video: VideoInfo, dry_run: bool = False) -> bool:
        """
        動画情報をXにポストする。
        dry_run=True の場合はポストせずログに出力するだけ。
        Returns: ポスト成功かどうか
        """
        tweet_text = build_tweet(video)

        if dry_run:
            logger.info("[DRY RUN] ポスト予定:\n%s", tweet_text)
            return True

        try:
            response = self.client.create_tweet(text=tweet_text)
            tweet_id = response.data["id"]
            logger.info("ポスト成功 (tweet_id=%s): %s", tweet_id, video.title)
            return True
        except tweepy.errors.TweepyException as e:
            logger.error("X ポストエラー: %s", e)
            return False

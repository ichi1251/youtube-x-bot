"""
YouTube Data API v3 を使って動画を検索・フィルタするモジュール。
条件:
  - 再生数 > チャンネル登録者数
  - ショート動画を除外（60秒以下 または タイトルに #shorts/#short）
  - 日本語タイトルの動画のみ（ひらがな・カタカナ・漢字を含む）
"""
import re
import logging
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# 日本語文字（ひらがな・カタカナ・CJK統合漢字）にマッチ
_JP_RE = re.compile(r'[\u3040-\u30ff\u4e00-\u9fff]')

# ISO 8601 duration パーサ（例: PT1M30S → 90秒）
_DURATION_RE = re.compile(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?')

logger = logging.getLogger(__name__)


@dataclass
class VideoInfo:
    video_id: str
    title: str
    channel_name: str
    channel_id: str
    view_count: int
    subscriber_count: int
    published_at: str
    url: str

    @property
    def ratio(self) -> float:
        """再生数 / 登録者数"""
        return self.view_count / self.subscriber_count if self.subscriber_count > 0 else 0

    def format_number(self, n: int) -> str:
        if n >= 100_000_000:
            return f"{n / 100_000_000:.1f}億"
        elif n >= 10_000:
            return f"{n / 10_000:.1f}万"
        else:
            return f"{n:,}"


def _parse_duration(duration: str) -> int:
    """ISO 8601 duration を秒数に変換。例: PT1M30S → 90"""
    m = _DURATION_RE.match(duration)
    if not m:
        return 0
    hours, minutes, seconds = (int(x or 0) for x in m.groups())
    return hours * 3600 + minutes * 60 + seconds


class YouTubeClient:
    def __init__(self, api_key: str):
        self.service = build("youtube", "v3", developerKey=api_key)

    def search_videos(
        self,
        days: int,
        max_results: int = 50,
        keywords: list[str] | None = None,
        category_id: str | None = None,
        max_subscriber_count: int | None = None,
        min_duration_seconds: int = 60,
    ) -> list[VideoInfo]:
        """
        キーワードまたはカテゴリで動画を検索し、再生数 > 登録者数の動画を返す。
        keywords と category_id はどちらか一方を指定する。
        """
        published_after = (
            datetime.now(timezone.utc) - timedelta(days=days)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")

        all_video_ids: list[str] = []

        if category_id:
            ids = self._search_by_category(category_id, published_after, max_results)
            all_video_ids.extend(ids)
            logger.info("カテゴリID「%s」: %d件取得", category_id, len(ids))
            # 0件の場合はカテゴリなしの急上昇にフォールバック
            if not ids:
                logger.warning("カテゴリID=%s で0件。カテゴリなし急上昇にフォールバック", category_id)
                ids = self._search_most_popular_no_category(published_after, max_results)
                all_video_ids.extend(ids)
                logger.info("カテゴリなし急上昇: %d件取得", len(ids))
        elif not keywords:
            ids = self._search_all_by_view_count(published_after, max_results)
            all_video_ids.extend(ids)
            logger.info("再生数順検索: %d件取得", len(ids))
        elif keywords:
            for keyword in keywords:
                ids = self._search_by_keyword(keyword, published_after, max_results)
                all_video_ids.extend(ids)
                logger.info("キーワード「%s」: %d件取得", keyword, len(ids))

        unique_ids = list(dict.fromkeys(all_video_ids))
        logger.info("重複除去後: %d件", len(unique_ids))

        if not unique_ids:
            return []

        videos = self._fetch_video_details(unique_ids)
        filtered = self._filter_and_enrich(videos, max_subscriber_count, min_duration_seconds)
        filtered.sort(key=lambda v: v.ratio, reverse=True)
        return filtered

    def _search_by_category(
        self,
        category_id: str,
        published_after: str,
        max_results: int,
    ) -> list[str]:
        """
        videos.list(chart=mostPopular) でカテゴリ別の人気動画を取得し、
        published_after 以降に公開されたものだけに絞る。
        404エラー（JPで未対応カテゴリ）の場合は search.list にフォールバック。
        """
        try:
            response = self.service.videos().list(
                part="id,snippet",
                chart="mostPopular",
                regionCode="JP",
                videoCategoryId=category_id,
                maxResults=min(max_results, 50),
            ).execute()
            items = response.get("items", [])
            # published_after 以降の動画だけ返す
            return [
                item["id"] for item in items
                if item["snippet"]["publishedAt"] >= published_after
            ]
        except HttpError as e:
            if e.resp.status == 404:
                logger.warning(
                    "カテゴリID=%s は JP の mostPopular 非対応。search.list にフォールバック",
                    category_id,
                )
                return self._search_by_category_fallback(category_id, published_after, max_results)
            logger.error("YouTube mostPopular 取得エラー (category=%s): %s", category_id, e)
            return []

    def _search_by_category_fallback(
        self,
        category_id: str,
        published_after: str,
        max_results: int,
    ) -> list[str]:
        """search.list + videoCategoryId でカテゴリ検索（フォールバック用）"""
        try:
            response = self.service.search().list(
                part="id",
                type="video",
                videoCategoryId=category_id,
                publishedAfter=published_after,
                maxResults=min(max_results, 50),
                order="viewCount",
                regionCode="JP",
                relevanceLanguage="ja",
            ).execute()
            return [item["id"]["videoId"] for item in response.get("items", [])]
        except HttpError as e:
            logger.error("YouTube search.list フォールバックエラー (category=%s): %s", category_id, e)
            return []

    def _search_most_popular_no_category(
        self,
        published_after: str,
        max_results: int,
    ) -> list[str]:
        """カテゴリ指定なしで日本の急上昇動画を取得"""
        try:
            response = self.service.videos().list(
                part="id,snippet",
                chart="mostPopular",
                regionCode="JP",
                maxResults=min(max_results, 50),
            ).execute()
            items = response.get("items", [])
            return [
                item["id"] for item in items
                if item["snippet"]["publishedAt"] >= published_after
            ]
        except HttpError as e:
            logger.error("YouTube mostPopular（カテゴリなし）取得エラー: %s", e)
            return []

    def _search_all_by_view_count(
        self,
        published_after: str,
        max_results: int,
    ) -> list[str]:
        """直近に公開された動画を新着順で取得（日本語フィルタは後処理）"""
        try:
            logger.info("検索パラメータ: publishedAfter=%s, maxResults=%d", published_after, max_results)
            response = self.service.search().list(
                part="id",
                type="video",
                publishedAfter=published_after,
                maxResults=min(max_results, 50),
                order="date",
            ).execute()
            items = response.get("items", [])
            logger.info("APIレスポンス: %d件, nextPageToken=%s", len(items), response.get("nextPageToken", "なし"))
            return [item["id"]["videoId"] for item in items]
        except HttpError as e:
            logger.error("YouTube 新着検索エラー: %s", e)
            return []

    def _search_by_keyword(
        self,
        keyword: str,
        published_after: str,
        max_results: int,
    ) -> list[str]:
        try:
            response = self.service.search().list(
                q=keyword,
                type="video",
                part="id",
                publishedAfter=published_after,
                maxResults=min(max_results, 50),
                order="viewCount",
                regionCode="JP",
                relevanceLanguage="ja",
            ).execute()
            return [item["id"]["videoId"] for item in response.get("items", [])]
        except HttpError as e:
            logger.error("YouTube 検索エラー (keyword=%s): %s", keyword, e)
            return []

    def _fetch_video_details(self, video_ids: list[str]) -> list[dict]:
        """50件ずつ分割してビデオ詳細を取得（contentDetails で尺も取得）"""
        results = []
        for i in range(0, len(video_ids), 50):
            chunk = video_ids[i:i + 50]
            try:
                response = self.service.videos().list(
                    id=",".join(chunk),
                    part="snippet,statistics,contentDetails",
                ).execute()
                results.extend(response.get("items", []))
            except HttpError as e:
                logger.error("YouTube videos.list エラー: %s", e)
        return results

    def _filter_and_enrich(
        self,
        videos: list[dict],
        max_subscriber_count: int | None = None,
        min_duration_seconds: int = 60,
    ) -> list[VideoInfo]:
        """
        以下の条件で絞り込んで VideoInfo リストを返す:
          1. 短い動画を除外（min_duration_seconds未満 または タイトルに #shorts/#short）
          2. 日本語タイトルのみ（ひらがな・カタカナ・漢字を含む）
          3. 再生数 > チャンネル登録者数
          4. 登録者数が max_subscriber_count 以下（指定時）
        """
        # ショート・日本語フィルタを先に適用してAPIコール数を削減
        pre_filtered = []
        for v in videos:
            title = v["snippet"]["title"]

            # --- 短い動画を除外 ---
            duration_sec = _parse_duration(
                v.get("contentDetails", {}).get("duration", "PT0S")
            )
            if duration_sec < min_duration_seconds:
                logger.debug("短い動画除外（%d秒）: %s", duration_sec, title)
                continue
            if re.search(r'#shorts?\b', title, re.IGNORECASE):
                logger.debug("ショート除外（タイトル）: %s", title)
                continue

            # --- 日本語タイトルのみ ---
            if not _JP_RE.search(title):
                logger.debug("日本語なし除外: %s", title)
                continue

            pre_filtered.append(v)

        logger.info("ショート・言語フィルタ後: %d件", len(pre_filtered))

        # チャンネル登録者数を取得
        channel_ids = list({v["snippet"]["channelId"] for v in pre_filtered})
        subscriber_map = self._fetch_subscriber_counts(channel_ids)

        result = []
        for v in pre_filtered:
            stats = v.get("statistics", {})
            view_count = int(stats.get("viewCount", 0))
            channel_id = v["snippet"]["channelId"]
            subscriber_count = subscriber_map.get(channel_id, 0)

            # 登録者数が非公開のチャンネルはスキップ
            if subscriber_count == 0:
                continue

            if max_subscriber_count and subscriber_count > max_subscriber_count:
                logger.debug("登録者数超過除外（%d人）: %s", subscriber_count, v["snippet"]["title"])
                continue

            if view_count > subscriber_count:
                result.append(VideoInfo(
                    video_id=v["id"],
                    title=v["snippet"]["title"],
                    channel_name=v["snippet"]["channelTitle"],
                    channel_id=channel_id,
                    view_count=view_count,
                    subscriber_count=subscriber_count,
                    published_at=v["snippet"]["publishedAt"],
                    url=f"https://www.youtube.com/watch?v={v['id']}",
                ))

        logger.info("フィルタ後（再生数>登録者数）: %d件", len(result))
        return result

    def _fetch_subscriber_counts(self, channel_ids: list[str]) -> dict[str, int]:
        """チャンネルIDに対する登録者数マップを返す"""
        result = {}
        for i in range(0, len(channel_ids), 50):
            chunk = channel_ids[i:i + 50]
            try:
                response = self.service.channels().list(
                    id=",".join(chunk),
                    part="statistics",
                ).execute()
                for item in response.get("items", []):
                    cid = item["id"]
                    stats = item.get("statistics", {})
                    # hiddenSubscriberCount が True の場合は 0
                    if stats.get("hiddenSubscriberCount", False):
                        result[cid] = 0
                    else:
                        result[cid] = int(stats.get("subscriberCount", 0))
            except HttpError as e:
                logger.error("YouTube channels.list エラー: %s", e)
        return result

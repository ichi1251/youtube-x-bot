import tweepy
from dotenv import load_dotenv
import os

load_dotenv()

api_key = os.getenv("X_API_KEY")
api_secret = os.getenv("X_API_SECRET")
access_token = os.getenv("X_ACCESS_TOKEN")
access_token_secret = os.getenv("X_ACCESS_TOKEN_SECRET")

print(f"X_API_KEY      : {api_key[:6]}... (length={len(api_key) if api_key else 0})")
print(f"X_API_SECRET   : {api_secret[:6]}... (length={len(api_secret) if api_secret else 0})")
print(f"X_ACCESS_TOKEN : {access_token[:6]}... (length={len(access_token) if access_token else 0})")
print(f"X_ACCESS_TOKEN_SECRET: {access_token_secret[:6]}... (length={len(access_token_secret) if access_token_secret else 0})")

client = tweepy.Client(
    consumer_key=api_key,
    consumer_secret=api_secret,
    access_token=access_token,
    access_token_secret=access_token_secret,
)

# 読み取りテスト
try:
    me = client.get_me()
    print("読み取り認証成功:", me)
except tweepy.TweepyException as e:
    print("読み取り失敗:", e)

# 書き込みテスト
try:
    response = client.create_tweet(text="テスト投稿（自動化テスト）")
    print("書き込み成功:", response)
except tweepy.TweepyException as e:
    print("書き込み失敗:", e)
    if hasattr(e, 'response') and e.response is not None:
        print("レスポンス詳細:", e.response.text)

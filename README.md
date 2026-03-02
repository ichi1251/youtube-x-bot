# YouTube急上昇動画 → X 自動ポストBot

キーワード・期間を指定してYouTubeを検索し、
**「再生数 > チャンネル登録者数」** の動画（=既存ファン以外に広まった動画）を
自動でXにポストするPythonスクリプトです。

---

## セットアップ

### 1. 依存パッケージのインストール

```bash
cd youtube-x-bot
pip install -r requirements.txt
```

---

### 2. YouTube Data API キーの取得

1. [Google Cloud Console](https://console.cloud.google.com/) にアクセス
2. 新しいプロジェクトを作成（または既存プロジェクトを選択）
3. 左メニュー → **「APIとサービス」→「ライブラリ」**
4. 「YouTube Data API v3」を検索 → 有効化
5. **「APIとサービス」→「認証情報」→「認証情報を作成」→「APIキー」**
6. 生成されたAPIキーをコピー

> 無料枠: 1日10,000ユニット（検索1回=100unit、動画詳細50件=1unit）

---

### 3. X (Twitter) API キーの取得

1. [X Developer Portal](https://developer.twitter.com/en/portal/dashboard) にアクセス
2. 「Create Project」→ アプリを作成
3. **User authentication settings** を設定:
   - App permissions: **Read and Write**
   - Type of App: Web App / Automated App or Bot
   - Callback URL: `https://localhost` （仮でOK）
4. 「Keys and tokens」タブから以下をコピー:
   - API Key (Consumer Key)
   - API Key Secret (Consumer Secret)
   - Access Token
   - Access Token Secret

> ⚠️ X APIの無料プランはWrite（ポスト）のみ対応。月500件まで投稿可能。

---

### 4. .env ファイルの作成

`.env.example` をコピーして `.env` を作成し、APIキーを設定:

```bash
cp .env.example .env
```

`.env` を編集:

```env
YOUTUBE_API_KEY=AIza...
X_API_KEY=xxx...
X_API_SECRET=xxx...
X_ACCESS_TOKEN=xxx...
X_ACCESS_TOKEN_SECRET=xxx...

SEARCH_KEYWORDS=プログラミング,AI,ChatGPT
SEARCH_DAYS=7
MAX_RESULTS_PER_KEYWORD=20
TOP_N=3
POST_INTERVAL_SECONDS=60
DRY_RUN=false
```

---

## 実行方法

### テスト実行（ポストせず確認のみ）

```bash
python main.py --dry-run
```

### 通常実行

```bash
python main.py
```

### キーワードをコマンドラインから指定

```bash
python main.py --keywords "生成AI,LLM,機械学習"
```

---

## Windows タスクスケジューラへの登録（毎日自動実行）

**管理者としてコマンドプロンプトを開き**、以下を実行:

```bat
setup_task.bat
```

毎朝 8:00 に自動実行されます。

### 登録確認・削除

```bat
REM 確認
SCHTASKS /QUERY /TN YouTubeXBot

REM 削除
SCHTASKS /DELETE /TN YouTubeXBot /F
```

---

## ポスト例

```
🔥 急上昇動画ピックアップ

📺 【衝撃】ChatGPTが完全に変わった...新機能がヤバすぎる

👤 テクノロジー解説チャンネル
👁 再生数: 85.2万回
👥 登録者数: 12.5万人
📊 比率: 6.8倍
📅 公開日: 2026-02-25

▶️ https://www.youtube.com/watch?v=xxxxxxxx
```

---

## ログ

実行ログは `run.log` に自動保存されます。

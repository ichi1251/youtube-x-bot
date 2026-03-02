"""
Windows タスクスケジューラに以下のジョブを登録するスクリプト。
  - YouTubeXBot_Draft : 毎朝 07:00 → Slackに投稿案を送信
  - YouTubeXBot_Post_1〜N : POST_TIMES で指定した時刻ごとに 1件ずつポスト

管理者権限のコマンドプロンプトで実行してください:
  python setup_schedule.py
"""
import os
import subprocess
import sys
from pathlib import Path
from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

load_dotenv(dotenv_path=Path(__file__).parent / ".env")

SCRIPT_DIR = Path(__file__).parent.resolve()
PYTHON = sys.executable
MAIN = str(SCRIPT_DIR / "main.py")

POST_TIMES = [t.strip() for t in os.getenv("POST_TIMES", "09:00,12:00,18:00").split(",")]
DRAFT_TIME = os.getenv("DRAFT_TIME", "07:00")


def register(task_name: str, command: str, time_str: str):
    cmd = [
        "SCHTASKS", "/CREATE",
        "/TN", task_name,
        "/TR", f'"{PYTHON}" "{MAIN}" {command}',
        "/SC", "DAILY",
        "/ST", time_str,
        "/RL", "HIGHEST",
        "/F",
    ]
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode == 0:
        print(f"  [OK] {task_name} ({time_str})")
    else:
        print(f"  [ERROR] {task_name}: {result.stderr.strip()}")


def delete(task_name: str):
    subprocess.run(
        ["SCHTASKS", "/DELETE", "/TN", task_name, "/F"],
        shell=True, capture_output=True
    )


print("=" * 50)
print("YouTube X Bot - タスクスケジューラ登録")
print("=" * 50)

# 既存のジョブを削除（再登録のため）
print("\n既存ジョブを削除中...")
delete("YouTubeXBot_Draft")
for i in range(1, 10):
    delete(f"YouTubeXBot_Post_{i}")

# draft ジョブ（毎朝固定時刻）
print(f"\n▶ draft ジョブ登録（毎日 {DRAFT_TIME}）")
register("YouTubeXBot_Draft", "--mode draft", DRAFT_TIME)

# post ジョブ（POST_TIMES の時刻ごと）
print(f"\n▶ post ジョブ登録（{len(POST_TIMES)} 件）")
for i, t in enumerate(POST_TIMES, 1):
    register(f"YouTubeXBot_Post_{i}", "--mode post", t)

print("\n" + "=" * 50)
print("登録済みジョブ一覧:")
subprocess.run(
    'SCHTASKS /QUERY /FO TABLE | findstr "YouTubeXBot"',
    shell=True
)
print("\n削除する場合:")
print("  SCHTASKS /DELETE /TN YouTubeXBot_Draft /F")
for i in range(1, len(POST_TIMES) + 1):
    print(f"  SCHTASKS /DELETE /TN YouTubeXBot_Post_{i} /F")

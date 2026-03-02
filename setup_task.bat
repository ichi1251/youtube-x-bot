@echo off
REM ============================================================
REM  Windows タスクスケジューラに2つのジョブを登録する
REM    1. YouTubeXBot_Draft : 毎朝07:00 → Slackに投稿案を送信
REM    2. YouTubeXBot_Post  : 毎朝09:00 → Slack返信を確認しXにポスト
REM  管理者権限で実行してください
REM ============================================================

SET SCRIPT_DIR=%~dp0
SET PYTHON_PATH=python

REM python.exe の場所を自動検出
WHERE python >nul 2>&1
IF %ERRORLEVEL% EQU 0 (
    FOR /F "delims=" %%i IN ('WHERE python') DO (
        SET PYTHON_PATH=%%i
        GOTO :FOUND
    )
)
:FOUND

ECHO -----------------------------------------------
ECHO Python    : %PYTHON_PATH%
ECHO スクリプト: %SCRIPT_DIR%main.py
ECHO ジョブ1   : YouTubeXBot_Draft  毎日 07:00
ECHO ジョブ2   : YouTubeXBot_Post   毎日 09:00
ECHO -----------------------------------------------

REM ── ジョブ1: draft ──
SCHTASKS /CREATE ^
  /TN "YouTubeXBot_Draft" ^
  /TR "\"%PYTHON_PATH%\" \"%SCRIPT_DIR%main.py\" --mode draft" ^
  /SC DAILY /ST 07:00 /RL HIGHEST /F

IF %ERRORLEVEL% EQU 0 (
    ECHO [OK] YouTubeXBot_Draft を登録しました。
) ELSE (
    ECHO [ERROR] YouTubeXBot_Draft の登録に失敗しました。
)

REM ── ジョブ2: post ──
SCHTASKS /CREATE ^
  /TN "YouTubeXBot_Post" ^
  /TR "\"%PYTHON_PATH%\" \"%SCRIPT_DIR%main.py\" --mode post" ^
  /SC DAILY /ST 09:00 /RL HIGHEST /F

IF %ERRORLEVEL% EQU 0 (
    ECHO [OK] YouTubeXBot_Post を登録しました。
) ELSE (
    ECHO [ERROR] YouTubeXBot_Post の登録に失敗しました。
)

ECHO.
ECHO 確認: SCHTASKS /QUERY /TN YouTubeXBot_Draft
ECHO 確認: SCHTASKS /QUERY /TN YouTubeXBot_Post
ECHO 削除: SCHTASKS /DELETE /TN YouTubeXBot_Draft /F
ECHO 削除: SCHTASKS /DELETE /TN YouTubeXBot_Post /F

PAUSE

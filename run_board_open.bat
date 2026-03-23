@echo off
pushd "%~dp0"

REM 먼저 브라우저 열기
start "" http://127.0.0.1:5000/attendance

REM 서버를 현재 창에서 실행(이 창은 서버 전용이 됨)
venv\Scripts\python.exe app.py

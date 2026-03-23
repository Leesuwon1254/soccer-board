Set oShell = CreateObject("Wscript.Shell")

' Flask 서버 실행 (숨김 모드)
oShell.Run "cmd /c cd /d ""C:\Users\USER\Desktop\soccer-board v1.1"" && call venv\Scripts\activate && python -u app.py", 0, False

' 잠시 대기 (서버 뜨는 시간)
WScript.Sleep 3000

' 기본 브라우저 열기
oShell.Run "http://127.0.0.1:5000"

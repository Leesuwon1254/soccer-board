Dim oFSO, oShell, scriptDir, pythonPath, serverCmd

Set oFSO   = CreateObject("Scripting.FileSystemObject")
Set oShell = CreateObject("WScript.Shell")

' 스크립트 위치 기준으로 폴더 자동 감지 (경로 하드코딩 불필요)
scriptDir  = oFSO.GetParentFolderName(WScript.ScriptFullName)
pythonPath = scriptDir & "\venv\Scripts\python.exe"

' python.exe 존재 여부 확인
If Not oFSO.FileExists(pythonPath) Then
    MsgBox "venv 가상환경을 찾을 수 없습니다." & vbCrLf & _
           pythonPath & vbCrLf & vbCrLf & _
           "requirements.txt 로 venv 를 먼저 설치해주세요.", _
           vbCritical, "보드판 실행 오류"
    WScript.Quit
End If

' Flask 서버 백그라운드 실행 (콘솔 창 숨김)
serverCmd = "cmd /c cd /d """ & scriptDir & """ && """ & pythonPath & """ -u app.py"
oShell.Run serverCmd, 0, False

' 서버 준비 대기 (2초)
WScript.Sleep 2000

' 기본 브라우저로 출석 페이지 열기
oShell.Run "http://127.0.0.1:5000"

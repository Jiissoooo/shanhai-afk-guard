' ============================================================
'  启动.vbs —— 山海寻灵防AFK控制器 无黑框启动器
'
'  为什么用 vbs 而不是 exe / bat：
'    .bat 会开一个控制台窗口（黑框），关掉它程序就跟着死了。
'    vbs 由 wscript.exe 执行，本身没有控制台；再用 pythonw.exe
'    （无控制台版 Python）拉起界面，全程不出现黑框。
'
'    不用 exe 的原因：本机开启了「智能应用控制(Smart App Control)」，
'    它阻止所有没有信誉签名的新编译 exe（实测连 hello-world 都被拦）。
'    vbs + pythonw 用的是系统已有组件，不受该策略影响。
' ============================================================
Option Explicit

Dim sh, fso, root, py, mainPy, bases, vers, b, v, alt

Set sh  = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

root   = fso.GetParentFolderName(WScript.ScriptFullName)
mainPy = root & "\main.py"

If Not fso.FileExists(mainPy) Then
    MsgBox "找不到 main.py" & vbCrLf & vbCrLf & _
           "请把本文件放在程序目录下（与 main.py 同一层）。" & vbCrLf & _
           "当前目录：" & root, 16, "山海寻灵 · 防AFK控制器"
    WScript.Quit 1
End If

py = ""

' ---------- 1) 环境变量显式指定 ----------
If sh.Environment("PROCESS")("HELMD_PYTHON") <> "" Then
    py = sh.Environment("PROCESS")("HELMD_PYTHON")
End If

' ---------- 2) 常见安装位置 + 项目自带 ----------
If py = "" Then
    bases = Array( _
        sh.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\Python\Python", _
        sh.ExpandEnvironmentStrings("%ProgramFiles%") & "\Python", _
        sh.ExpandEnvironmentStrings("%ProgramFiles%") & "\Python3", _
        "C:\Python", _
        root & "\runtime\python", _
        root & "\runtime")
    vers = Array("313", "312", "311", "310", "")
    For Each b In bases
        For Each v In vers
            If py = "" Then
                If fso.FileExists(b & v & "\pythonw.exe") Then py = b & v & "\pythonw.exe"
            End If
        Next
    Next
End If

' ---------- 3) 从 PATH 里找（排除 WindowsApps 占位程序） ----------
If py = "" Then
    Dim pathVar, parts, p, cand
    pathVar = sh.Environment("PROCESS")("PATH")
    parts = Split(pathVar, ";")
    For Each p In parts
        If py = "" Then
            p = Trim(p)
            If Len(p) > 0 Then
                If InStr(LCase(p), "windowsapps") = 0 Then
                    cand = p & "\pythonw.exe"
                    If fso.FileExists(cand) Then py = cand
                End If
            End If
        End If
    Next
End If

' ---------- 4) 若有 python.exe 但没有 pythonw.exe，退回 python.exe ----------
If py = "" Then
    Dim pathVar2, parts2, p2, cand2
    pathVar2 = sh.Environment("PROCESS")("PATH")
    parts2 = Split(pathVar2, ";")
    For Each p2 In parts2
        If py = "" Then
            p2 = Trim(p2)
            If Len(p2) > 0 Then
                If InStr(LCase(p2), "windowsapps") = 0 Then
                    cand2 = p2 & "\python.exe"
                    If fso.FileExists(cand2) Then py = cand2
                End If
            End If
        End If
    Next
End If

' ---------- 没找到 ----------
If py = "" Then
    MsgBox "没有找到可用的 Python。" & vbCrLf & vbCrLf & _
           "请安装 Python 3.10 或更高版本，安装时务必勾选：" & vbCrLf & _
           "  [x] Add python.exe to PATH" & vbCrLf & vbCrLf & _
           "下载地址：" & vbCrLf & _
           "https://www.python.org/downloads/windows/" & vbCrLf & vbCrLf & _
           "注意：微软商店那个 0 字节的 python.exe 占位程序不能用。", _
           48, "山海寻灵 · 防AFK控制器"
    WScript.Quit 1
End If

' ---------- 用 pythonw.exe 无控制台启动 ----------
If InStr(LCase(py), "python.exe") > 0 Then
    alt = Replace(py, "python.exe", "pythonw.exe")
    If fso.FileExists(alt) Then py = alt
End If

sh.CurrentDirectory = root
sh.Environment("PROCESS")("PYTHONIOENCODING") = "utf-8"

' 0 = 窗口隐藏, False = 不等待
sh.Run """" & py & """ """ & mainPy & """", 0, False

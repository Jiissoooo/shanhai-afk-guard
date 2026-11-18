' diag.vbs - 诊断解释器查找
Option Explicit
Dim sh, fso, root, py, i, bases, vers, b, v, logf, ts
Set sh  = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(WScript.ScriptFullName)

Set ts = fso.OpenTextFile(root & "\artifacts\vbs_diag.txt", 2, True)
ts.WriteLine "root=" & root
ts.WriteLine "HELMD_PYTHON=[" & sh.Environment("PROCESS")("HELMD_PYTHON") & "]"
ts.WriteLine "LOCALAPPDATA=" & sh.ExpandEnvironmentStrings("%LOCALAPPDATA%")
ts.WriteLine "ProgramFiles=" & sh.ExpandEnvironmentStrings("%ProgramFiles%")

bases = Array( _
    sh.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\Python\Python", _
    sh.ExpandEnvironmentStrings("%ProgramFiles%") & "\Python", _
    "C:\Python", _
    root & "\runtime")
vers = Array("313", "312", "311", "310", "")

py = ""
For Each b In bases
    For Each v In vers
        ts.WriteLine "try: " & b & v & "\pythonw.exe -> " & CStr(fso.FileExists(b & v & "\pythonw.exe"))
        If py = "" Then
            If fso.FileExists(b & v & "\pythonw.exe") Then py = b & v & "\pythonw.exe"
        End If
    Next
Next

ts.WriteLine "FOUND=" & py
ts.Close

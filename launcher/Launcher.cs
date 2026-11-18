// Launcher.cs - 山海寻灵防AFK控制器 原生启动器
//
// 解决三个问题：
//   1. 双击 .bat 会留一个黑色控制台窗口，关掉它就杀掉程序
//      -> 编译成 /target:winexe 的 GUI 子系统 exe，本身没有控制台
//   2. .bat 需要安装 Python 并配好 PATH
//      -> 自动定位解释器并改用 pythonw.exe（无控制台 Python）
//   3. 权限不足时游戏进程打不进去，但用户看不出来
//      -> manifest 声明 requireAdministrator，双击即弹 UAC
//
// 编译（Windows 自带 csc，无需联网）：
//   csc /target:winexe /win32manifest:launcher.manifest /out:山海寻灵防AFK.exe Launcher.cs
using System;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Windows.Forms;

namespace ShanhaiAFK
{
    static class Launcher
    {
        private const string AppTitle = "山海寻灵 · 防AFK控制器";
        private const string EnvMarker = "HELMD_LAUNCHED";

        [STAThread]
        static void Main()
        {
            try
            {
                string root = AppDomain.CurrentDomain.BaseDirectory.TrimEnd('\\');
                string mainPy = Path.Combine(root, "main.py");
                if (!File.Exists(mainPy))
                {
                    Fail("找不到 main.py\n\n" +
                         "请把本 exe 放在程序目录下（与 main.py 同一层）。\n" +
                         "当前目录：" + root);
                    return;
                }

                // 防止重复启动：同一个程序只跑一份
                if (Process.GetProcessesByName("pythonw").Length > 0 &&
                    Environment.GetEnvironmentVariable(EnvMarker) == null)
                {
                    var r = MessageBox.Show(
                        "检测到已有 pythonw 进程在运行，可能已经启动过了。\n\n" +
                        "仍要继续再启动一个实例吗？",
                        AppTitle, MessageBoxButtons.YesNo,
                        MessageBoxIcon.Question, MessageBoxDefaultButton.Button2);
                    if (r != DialogResult.Yes) return;
                }

                string py = FindPython(root);
                if (py == null)
                {
                    Fail("没有找到可用的 Python 解释器。\n\n" +
                         "请安装 Python 3.10 或更高版本（安装时勾选\n" +
                         "\"Add python.exe to PATH\"），然后重新运行本程序：\n" +
                         "https://www.python.org/downloads/windows/\n\n" +
                         "注意：微软商店里那个 0 字节的 python.exe 占位程序\n" +
                         "不能使用，它只会弹出\"去商店安装\"。");
                    return;
                }

                var psi = new ProcessStartInfo();
                psi.FileName = py;
                psi.Arguments = Quote(mainPy);
                psi.WorkingDirectory = root;
                psi.UseShellExecute = false;
                psi.CreateNoWindow = true;   // 关键：不创建控制台
                psi.WindowStyle = ProcessWindowStyle.Hidden;
                psi.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8";
                psi.EnvironmentVariables[EnvMarker] = "1";

                Process p = Process.Start(psi);
                if (p == null)
                {
                    Fail("启动 Python 失败，未返回进程句柄。");
                }
                // 启动器本身立即退出，GUI 继续独立运行
            }
            catch (Exception ex)
            {
                Fail("启动失败：\n\n" + ex.GetType().Name + ": " + ex.Message);
            }
        }

        // ---------------------------------------------------------------
        // 解释器查找：优先 pythonw.exe（无控制台），排除 WindowsApps 占位符
        // ---------------------------------------------------------------
        static string FindPython(string root)
        {
            // 1) 环境变量显式指定
            string explicitPy = Environment.GetEnvironmentVariable("HELMD_PYTHON");
            if (!string.IsNullOrEmpty(explicitPy))
            {
                if (File.Exists(explicitPy)) return explicitPy;
                string w = Path.Combine(Path.GetDirectoryName(explicitPy) ?? "",
                                        "pythonw.exe");
                if (File.Exists(w)) return w;
            }

            // 2) 项目内自带运行时
            string[] bundled =
            {
                Path.Combine(root, "runtime", "pythonw.exe"),
                Path.Combine(root, "runtime", "python.exe"),
                Path.Combine(root, "python", "pythonw.exe"),
            };
            foreach (string b in bundled) if (File.Exists(b)) return b;

            // 3) 常见安装位置
            string local = Environment.GetFolderPath(
                Environment.SpecialFolder.LocalApplicationData);
            string pf = Environment.GetFolderPath(
                Environment.SpecialFolder.ProgramFiles);
            string[] versions = { "313", "312", "311", "310" };
            foreach (string v in versions)
            {
                string[] cands =
                {
                    Path.Combine(local, @"Programs\Python\Python" + v + @"\pythonw.exe"),
                    Path.Combine(pf, @"Python" + v + @"\pythonw.exe"),
                    @"C:\Python" + v + @"\pythonw.exe",
                };
                foreach (string c in cands) if (File.Exists(c)) return c;
            }

            // 4) PATH 兜底：排除 WindowsApps 占位目录
            string pathVar = Environment.GetEnvironmentVariable("PATH") ?? "";
            foreach (string raw in pathVar.Split(';'))
            {
                string dir = raw.Trim();
                if (dir.Length == 0) continue;
                if (dir.IndexOf("WindowsApps",
                        StringComparison.OrdinalIgnoreCase) >= 0) continue;
                try
                {
                    string w = Path.Combine(dir, "pythonw.exe");
                    if (File.Exists(w)) return w;
                }
                catch { /* 非法路径字符，跳过 */ }
            }
            return null;
        }

        static string Quote(string s)
        {
            return "\"" + s + "\"";
        }

        static void Fail(string msg)
        {
            MessageBox.Show(msg, AppTitle, MessageBoxButtons.OK,
                            MessageBoxIcon.Warning);
        }
    }
}

"""Launch the entire guide app elevated; one UAC approval per app start."""
import ctypes
from pathlib import Path
import shutil
import subprocess
import sys


def main():
    # 呼び出し元のPythonを優先する。これにより、uvで構築した環境や
    # bundled runtimeから起動しても、依存関係の異なるPythonへ切り替わらない。
    root = Path(__file__).resolve().parent
    # bundled runtimeにはStreamlitが入っていないため、通常はuv環境を使う。
    uv = shutil.which('uv')
    venv_python = root.parents[1] / '.venv' / 'Scripts' / 'python.exe'
    if sys.platform != 'win32':
        raise RuntimeError('Windows専用の起動プログラムです')
    if uv is None and not venv_python.is_file():
        raise RuntimeError('uv sync済みの環境が見つかりません')
    if not ctypes.windll.shell32.IsUserAnAdmin():
        shell = ctypes.windll.shell32.ShellExecuteW
        shell.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_wchar_p,
                          ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_int]
        shell.restype = ctypes.c_void_p
        # uv run が選んだPythonで、このランチャーを管理者として再実行する。
        result = shell(None, 'runas', sys.executable,
                       subprocess.list2cmdline([str(Path(__file__).resolve())]), str(root), 0)
        if not result or result <= 32:
            raise RuntimeError('管理者起動が拒否または失敗しました')
        return
    if uv is not None:
        command = [uv, 'run', '--project', str(root.parents[1]), 'streamlit', 'run',
                   str(root / 'app_auto_guide.py'), '--server.address', '127.0.0.1']
    else:
        command = [str(venv_python), '-m', 'streamlit', 'run', str(root / 'app_auto_guide.py'),
                   '--server.address', '127.0.0.1']
    subprocess.run(command, cwd=root, check=True)


if __name__ == '__main__':
    main()

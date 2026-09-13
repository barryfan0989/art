import os
import sys
import subprocess
from pathlib import Path

def run_all_py_files():

    base_dir = Path(__file__).parent

    current_file = Path(__file__).name

    # 1. 執行資料庫清理腳本
    print("開始清洗舊資料庫資料...")
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        subprocess.run([sys.executable, str(base_dir / "clean_db.py")], check=True, env=env)
    except subprocess.CalledProcessError as e:
        print(f"資料庫清洗失敗，停止執行後續爬蟲: {e}", file=sys.stderr)
        sys.exit(1)

    # 2. 篩選出其他爬蟲腳本並排除工具腳本 (start.py, clean_db.py, export_db.py, import_db.py)
    excluded_files = {current_file, "clean_db.py", "export_db.py", "import_db.py"}
    py_files = [
        f for f in base_dir.glob("*.py")
        if f.name not in excluded_files
    ]

    processes = []

    print(f"發現 {len(py_files)} 個爬蟲腳本: {', '.join(f.name for f in py_files)}")

    for file in py_files:

        print(f"啟動: {file.name}")

        p = subprocess.Popen(
            [sys.executable, str(file)],
            cwd=str(base_dir),
            env=env
        )

        processes.append(p)

    # 等待全部結束
    for p in processes:
        p.wait()

    print("全部爬蟲腳本執行完成！")

    # 3. 爬蟲完成後自動匯出備份 JSON
    print("正在將最新爬取資料匯出至 database_export.json ...")
    try:
        subprocess.run([sys.executable, str(base_dir / "export_db.py")], check=True, env=env)
        print("資料匯出完成！")
    except Exception as e:
        print(f"資料匯出時發生警告: {e}", file=sys.stderr)


if __name__ == "__main__":
    run_all_py_files()
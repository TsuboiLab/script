各班でフォルダ分けしておいたので、そこに格納してください。
他の人も使ったら便利だよーーってスクリプトに関してはgeneralに入れてください。
wiki, projectの更新もお忘れなく。

--- 2026/03/26 kawai add
分析環境共通化のために、uv使ってpythonのバージョンを3.12に統一できるようにしました。
以下に、`uv`と`git`使った解析環境構築の方法をまとめます（Mac, Linux, Windows対応）

# 1. 開発環境のセットアップ
### Gitのインストールと設定
1. 公式サイトなどからgitを用意
   - windowsの場合：[Git for Windows](https://gitforwindows.org/) をインストールします。
2. ターミナルで以下のコマンドを実行し、ユーザー設定を実施（git利用時の個人識別用なので、研究で使うアドレス書けばok）

```
git config --global user.name "Your Name"
git config --global user.email "your-email@example.com"
```

# 2. uvのインストールと実行許可
Python管理ツール uv をインストール

**Windowsの場合**

```powershell
# uvのインストール
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
# PowerShellでのスクリプト実行（仮想環境の起動）を許可
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

**Mac, Linuxの場合**

```bash
# uvのインストール
curl -LsSf https://astral.sh/uv/install.sh | sh
```

# 3. プロジェクトの初期化とパッケージ導入
分析環境(work)内に移動してuvによりpythonの仮想環境を構築します

```
# 既存のuv環境(python3.12)を再現
uv sync
```

# 4. 仮想環境の有効化
Windows の場合:
```powershell
# 仮想環境の有効化
.venv\Scripts\activate
```

Mac / Linux の場合:
```bash
source .venv/bin/activate
```

# 5. GitHubへの初回連携と保存
PCローカルとgithubのリモートとを連携

```
# Gitの初期化とリモート追加
git init
git clone https://github.com/TsuboiLab/script.git
# git remote add origin https://github.com/TsuboiLab/script.git  # 必要に応じて実施. 不要の場合有り
```

---

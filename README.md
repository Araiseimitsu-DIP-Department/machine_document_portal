# Machine Document Portal

Googleスプレッドシートで運用している「稼働中工程内検査シート」を置き換え、号機ごとに現在品番、SharePoint上の工程内検査シート、NAS上の加工図をまとめて表示する社内向けWebアプリです。

Googleスプレッドシート「生産中」から最新情報を取得し、プロセス内メモリで表示します。現在の運用ではPostgreSQLは不要です。サンプルデータモードも画面確認用として利用できます。

## 主な機能

- 「生産中」シートのD列に存在する号機だけを表示し、追加・削除を次回更新で反映
- A列の生産状態、H列の品番、I列の品名を表示
- 稼働中／停止中／生産終了／セット中をGoogleスプレッドシートに合わせて色分け
- SharePointのファイル名とH列の品番を文字列そのままで完全一致照合し、工程内検査シートを別タブで表示
- NASにある品番と同名のPDFから1ページ目を画像化し、専用タブで表示
- 加工図画像を50〜300%で拡大・縮小
- 手動・起動時の完全同期と、`AUTO_REFRESH_SECONDS` による変更号機だけの定期同期・画面再読込
- `DOCUMENT_REFRESH_TIMES` で指定した日本時間にSharePoint・NASだけを全号機分更新
- 「最新情報に更新」ボタンの近くに、工程内検査シート・加工図面を更新する操作であることを表示
- 翌営業日シートの `B40:K40` を13:00に確認し、不足資料をARAICHATへ通知
- 同じ翌営業日シートを15:00に再取得し、NASの加工図をWindowsプリンターへ1部ずつ送信
- 対象シート単位の通知重複防止と、品番単位の二重印刷防止
- 工程内検査シート、出荷検査表、測定機器点検表への共通外部リンク
- 未検出、複数候補、認証・権限・外部APIエラーの状態表示
- タブレット／Windows業務PC向けレスポンシブUI
- プロセス内メモリストア、最新画面スナップショット、加工図プレビューキャッシュ
- UTF-8ローテーションログ

## 動作環境

- Windows 10/11
- Python 3.11以上
- Chrome または Microsoft Edge の現行版
- NASおよび利用する外部サービスへ接続できる社内ネットワーク

PostgreSQLとSQLiteは現在のメモリ運用では使用しません。

## セットアップ

PowerShellでプロジェクトフォルダへ移動し、仮想環境を作成します。

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

コマンドプロンプトの場合、仮想環境の有効化は次のとおりです。

```bat
.venv\Scripts\activate.bat
```

## サンプルデータモードで起動

`.env` がなくても既定値 `USE_SAMPLE_DATA=true`、`PERSISTENCE_MODE=memory` で起動します。明示する場合は `.env.example` を `.env` へコピーしてください。

```powershell
Copy-Item .env.example .env
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

ブラウザで <http://localhost:8000> を開きます。Windowsでは `run_app.bat` をダブルクリックしても起動できます。

サンプルデータは `sample_data/machines.json` にあります。

## 本番のメモリ運用

```dotenv
PERSISTENCE_MODE=memory
USE_SAMPLE_DATA=false
```

次の情報はアプリのプロセス内で使用し、最新状態1件だけをJSONスナップショットにも保存します。

- 号機ごとの現在品番、品名、生産状態
- 工程内検査シートと加工図の取得結果
- 最終更新日時と外部サービスのエラー状態

最新画面は `DASHBOARD_SNAPSHOT_PATH` へ保存します。アプリ起動時は前回画面を読み込んだうえで、Google Sheets、SharePoint、NASを完全同期します。外部エラー時に前回の正常リンクは再利用せず、資料ボタンをエラー状態にします。複数のUvicornワーカー間でメモリと定時処理ロックは共有されないため、1ワーカーで起動してください。

## ダッシュボードの更新方法

- アプリ起動時: Google Sheets、SharePoint、NASを完全同期
- 「最新情報に更新」ボタン: 利用者の操作でGoogle Sheets、SharePoint、NASを完全同期
- `AUTO_REFRESH_SECONDS`: Google Sheetsを取得し、H列の品番が新規・変更された号機だけSharePointとNASを再検索
- `DOCUMENT_REFRESH_TIMES`: 指定した日本時間に、Google Sheetsを取得せずSharePointとNASだけを全号機分更新

画面では「最新情報に更新」ボタンの近くに「工程内検査シート・加工図面を更新するときに押してください。」と表示します。`DOCUMENT_REFRESH_TIMES` は `10:30,14:30` のように複数指定でき、空欄の場合は実行しません。

Google Sheetsのサービスアカウント、共有設定、列構成、NAS設定は [Google Sheets本番設定](docs/GOOGLE_SHEETS_PRODUCTION.md) を参照してください。

## SharePoint工程内検査シート

Microsoft Graph（マイクロソフト グラフ）のアプリケーション認証を使用し、設定したSharePointフォルダとその配下の全サブフォルダを読み取り専用で再帰検索します。GoogleスプレッドシートH列の品番と、拡張子を除いたSharePointファイル名が文字列そのままで完全一致する場合に、号機の「検査シート」ボタンを有効にします。大文字・小文字、全角・半角、空白、ダッシュ表記が異なる場合は一致として扱いません。

連携コードは実装済みです。利用開始には、Entraアプリの `Sites.Selected` への管理者同意、対象SharePointサイトへの `Read` 権限、`SHAREPOINT_DRIVE_ID`、`SHAREPOINT_FOLDER_ID` の設定が必要です。詳細は [SharePoint工程内検査シート連携](docs/SHAREPOINT_INSPECTION_SHEETS.md) を参照してください。

アプリはSharePoint上のファイルを作成・更新・削除しません。ボタンから開いたファイルで利用者が可能な操作は、その利用者自身のSharePoint権限に従います。

## NAS加工図

`NAS_DRAWING_DIRECTORY` 配下から、GoogleスプレッドシートH列の品番と同名のPDFを検索します。加工図ボタンを押すと、PDF自体ではなく1ページ目のJPEGプレビューを専用タブで開きます。

- タブ名と見出しは「号機_品番_加工図面」
- 表示領域の大きさを変えず、内部画像だけを50〜300%で拡大・縮小
- 同一PDFの同時変換を抑制
- 最大64件かつ128MiBのプレビューをプロセス内にキャッシュ
- NASパスとPDFファイルをブラウザへ直接公開しない

アプリを起動するWindowsアカウントには、NASフォルダの読み取り権限が必要です。

## サイドバーの外部リンク

号機一覧の下に区切り線と「外部リンク」見出しを表示し、次の共通リンクを別タブで開きます。リンクはホバー時の背景色と外部リンク記号で識別でき、サイドバーを折りたたんだ場合も外部リンク記号が残ります。

- `SHAREPOINT_PROCESS_INSPECTION_URL`: 工程内検査シート
- `SHAREPOINT_SHIPPING_INSPECTION_URL`: 出荷検査表
- `NOTION_MEASUREMENT_EQUIPMENT_INSPECTION_URL`: 測定機器点検表

## 翌営業日セット内容の定時処理

`SCHEDULED_OPERATIONS_ENABLED=true` の場合、アプリは日本時間の13:00と15:00に次の処理を行います。誤通知・誤印刷を防ぐため、Google、SharePoint、ARAICHAT、NAS、プリンターの設定確認が終わるまでは `false` にしてください。

- 今日より後の日付シートを順に検索し、最初に存在する `〇〇S` を翌営業日シートとする
- 13:00に `B40:K40` の空白以外の品番をSharePointとNASで完全一致検索し、ARAICHATへ通知する
- 15:00に同じシートを再取得し、一致したPDFを `DRAWING_PRINTER_NAME` へ1品番1部送信する
- 金曜日に月曜日分を処理済みの場合、土日は同じ通知と印刷を繰り返さない
- 印刷途中で失敗した場合、次回は未印刷品番だけを再処理する

送信・印刷状態は `SCHEDULED_JOB_STATE_PATH` に保存します。ARAICHATの送信結果が通信切断などで不明な場合は、二重投稿防止のため自動再送しません。

## 主な設定

全項目は `.env.example` を参照してください。

- `PERSISTENCE_MODE`: 現在は `memory`
- `USE_SAMPLE_DATA`: `true`なら外部サービスへ接続せずサンプルを表示
- `GOOGLE_SPREADSHEET_*`: Google Sheets取得設定（A=状態、D=号機、H=品番、I=品名）
- `NAS_DRAWING_DIRECTORY`: 加工図PDFを置くNASフォルダ
- `MICROSOFT_TENANT_ID` / `MICROSOFT_CLIENT_ID` / `MICROSOFT_CLIENT_SECRET`: Microsoft Graph認証
- `SHAREPOINT_DRIVE_ID` / `SHAREPOINT_FOLDER_ID`: 品番別工程内検査シートの検索先
- `SHAREPOINT_PROCESS_INSPECTION_URL` / `SHAREPOINT_SHIPPING_INSPECTION_URL`: サイドバーのSharePoint共通リンク
- `NOTION_MEASUREMENT_EQUIPMENT_INSPECTION_URL`: サイドバーのNotion共通リンク
- `AUTO_REFRESH_SECONDS`: Google Sheetsを定期取得し、品番が新規・変更された号機だけSharePoint・NASを再検索する間隔。`0`で無効
- `DOCUMENT_REFRESH_TIMES`: SharePoint・NASだけを全号機分更新する日本時間。`HH:MM`をカンマ区切りで指定し、空欄で無効
- `SCHEDULED_OPERATIONS_ENABLED`: 13:00の通知と15:00の印刷を有効化
- `ARAICHAT_BASE_URL` / `ARAICHAT_API_KEY` / `ARAICHAT_ROOM_ID`: ARAICHAT送信設定
- `DRAWING_PRINTER_NAME`: 加工図の送信先Windowsプリンター
- `DASHBOARD_SNAPSHOT_PATH` / `SCHEDULED_JOB_STATE_PATH`: 再起動時の復元・重複防止ファイル
- `LOG_*`: UTF-8ログのレベル、保存先、ローテーション

`.env`、サービスアカウントJSON、クライアントシークレット、OAuthトークン、秘密鍵はGitへ登録しないでください。

## 起動とテスト

```powershell
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
python -m pytest -q
```

Windowsでは `run_app.bat` と `run_tests.bat` も使用できます。テストはPostgreSQLや外部サービスへ実接続しません。

NSSMで常時起動する場合は、Applicationを仮想環境のPython、Argumentsを `-m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1`、AppDirectoryをプロジェクトルートに設定します。NSSMサービスの実行アカウントには、Google認証JSON、NASフォルダ、`data`、`logs`、および `DRAWING_PRINTER_NAME` のプリンターを利用できる権限が必要です。

## 将来PostgreSQLを有効にする場合

SQLAlchemyモデル、Repository、Alembicマイグレーションは、将来履歴の永続化が必要になった場合の選択肢として残しています。現在は設定も実行も不要です。

`PERSISTENCE_MODE=postgresql` を選択する場合だけ、PostgreSQLの作成、`DATABASE_URL` の設定、`alembic upgrade head` が必要です。

## 今後の検討事項

- 加工図と工程内検査シートの画面分割
- 加工図の複数ページ表示
- 枝番・改訂番号を含む検査シート検索規則
- 複数候補の選択画面
- 最新状態以外の履歴が必要になった場合の永続化

確定事項と未確定事項は [要件整理](docs/REQUIREMENTS.md)、内部構成は [アーキテクチャ](docs/ARCHITECTURE.md)、変更履歴は [CHANGELOG](docs/CHANGELOG.md) を参照してください。

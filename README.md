# Machine Document Portal

Googleスプレッドシートで運用している「稼働中工程内検査シート」を置き換え、号機ごとに現在品番、SharePoint上の工程内検査シート、NAS上の加工図をまとめて表示する社内向けWebアプリです。

Googleスプレッドシート「生産中」から最新情報を取得し、プロセス内メモリで表示します。現在の運用ではPostgreSQLは不要です。サンプルデータモードも画面確認用として利用できます。

## 主な機能

- 「生産中」シートのD列に存在する号機だけを表示し、追加・削除を次回更新で反映
- A列の生産状態、H列の品番、I列の品名を表示
- 稼働中／停止中／生産終了／セット中をGoogleスプレッドシートに合わせて色分け
- SharePointのファイル名とH列の品番を文字列そのままで照合し、完全一致または末尾が`-正の整数`の関連ファイルを別タブで表示
- 工程内検査シートが複数ある場合は件数を表示し、別タブの選択画面から全ファイルを開ける
- NASにある品番と同名のPDFの1ページ目を、ローカル配置したPDF.jsで専用タブへ高精細表示
- 加工図をボタン、マウスホイール、タッチ端末の2本指操作で50〜300%に拡大・縮小し、マウスドラッグで上下左右へ移動
- 手動・起動時の完全同期と、`AUTO_REFRESH_SECONDS` による変更号機だけの定期同期・画面再読込
- `DOCUMENT_REFRESH_TIMES` で指定した日本時間にGoogle Sheets「生産中」を取得し、SharePoint・NASも全号機分更新
- 「最新情報に更新」ボタンの右側に最終更新日時、下側に1行の操作説明を表示
- 翌営業日シートの `B36:K36` の日付と `B40:K40` の品番を13:00に確認し、対象日より前の日付が入った列を除外して不足資料をARAICHATへ通知。14:30に同じシートを再確認し、残っている不足だけを再通知
- 同じ翌営業日シートを15:00に再取得し、NASの加工図をWindowsプリンターへ1部ずつ送信
- 対象シート単位の通知重複防止と、品番単位の二重印刷防止
- 印刷できなかった加工図を自動で再実行し、解決しない場合は利用者がアプリから未印刷分だけを印刷
- 工程内検査シート、出荷検査表、測定機器点検表への共通外部リンク
- 未検出、複数候補、認証・権限・外部APIエラーの状態表示
- 解像度の異なるWindows業務PC、iPad、iPhone、Androidタブレット／スマートフォン向けレスポンシブUI
- 画面幅に応じた5列／3列／2列／1列表示、モバイルメニュー、折りたたみ可能な号機グループ
- 号機一覧のブラウザタブ、ブックマーク、iOS／Androidのホーム画面追加、Windows／Android向けWeb App Manifest（`display: standalone`）の表示名を「稼働中工程内検査シート」に統一し、加工図タブは「号機_品番_加工図面」で識別
- プロセス内メモリストア、最新画面スナップショット、加工図PDFのブラウザーキャッシュと障害時プレビューキャッシュ
- UTF-8ローテーションログ

## 動作環境

- Windows 10/11
- Python 3.11以上
- Chrome または Microsoft Edge の現行版
- NASおよび利用する外部サービスへ接続できる社内ネットワーク

PostgreSQLとSQLiteは現在のメモリ運用では使用しません。

## ファイル構成

主要なファイルとディレクトリの役割は次のとおりです。アプリ起動、定時実行、画面、業務処理を分け、変更箇所を追いやすくしています。

```text
app/
├─ main.py                 FastAPIの生成と起動・終了処理
├─ pwa.py                  PWA表示名・テーマ色・静的ファイルのキャッシュ版数
├─ scheduling.py           定期同期と13:00・14:30・15:00の実行制御
├─ routers/                画面とAPIの入口
├─ services/               同期、検索、通知、印刷などの業務処理
├─ schemas/                画面・メモリで共通利用するデータ型
├─ templates/              Jinja2画面テンプレート
├─ static/                 CSS、JavaScript、画像、PWA用manifestとアイコン
├─ models/                 将来のPostgreSQL運用向けモデル
├─ repositories/           将来のPostgreSQL運用向けデータアクセス
└─ utils/                  品番、号機並び順、ログなどの共通処理
tests/                     自動テスト
docs/                      仕様、設計、変更履歴、運用資料
sample_data/               画面確認用サンプルデータ
migrations/                将来のPostgreSQL運用向けマイグレーション
```

実行時に生成される `data/`、`logs/`、`output/` はソースコードと分離し、Gitへ登録しません。認証情報は `.env` だけで管理し、ソースコードやドキュメントへ記載しないでください。

## セットアップ

PowerShellでプロジェクトフォルダへ移動し、仮想環境を作成します。

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

コマンドプロンプトの場合、仮想環境の有効化は次のとおりです。

```bat
.venv\Scripts\activate.bat
```

## サンプルデータモードで起動

`.env` がなくても既定値 `USE_SAMPLE_DATA=true`、`PERSISTENCE_MODE=memory` で起動します。明示する場合は `.env.example` を `.env` へコピーしてください。

```powershell
Copy-Item .env.example .env
python -m app
```

ブラウザで `.env` の `APP_PORT` を開きます（`.env.example` の既定はサーバー用の `8013`。ローカルだけ `8000` にしても構いません）。Windowsでは `run_app.bat` をダブルクリックしても起動できます。`run_app.bat` と `python -m app` は `.env` のポートを読み取ります。

号機一覧のブラウザタブ、ブックマーク、「アプリのインストール」「ホーム画面に追加」の表示名は「稼働中工程内検査シート」に統一しています。加工図の専用タブだけは、開いている図面を識別できるよう「号機_品番_加工図面」と表示します。アイコンは `app/static/manifest.json` と `app/static/icons/` の画像を参照し、サイドバー上部の社名ロゴは `docs/DESIGN` の ARAI ロゴを使用します。アイコン画像を差し替えた場合は、各サイズを再生成し、`app/pwa.py` の `STATIC_ICONS_VERSION` を更新してください。CSS、JavaScript、Web App Manifestは内容から生成した `STATIC_ASSETS_VERSION` をURLへ付け、変更時にブラウザキャッシュを自動更新します。Service Workerは使用していないため、データ更新と画面の自動再読込は通常のブラウザ表示と同じです。Chrome／Edgeの「アプリとしてインストール」はHTTPS環境で利用しやすくなります。

既に保存済みのブックマークやホーム画面アイコンは、端末によって表示名が自動更新されない場合があります。その場合は既存項目を削除し、ページを再読込してから追加し直してください。

### デバイス別レイアウト

レイアウトは端末名ではなくCSSピクセル単位の表示幅で切り替わるため、Windowsの表示倍率やブラウザズームも反映されます。

| 表示幅 | 号機一覧 | ナビゲーション |
| --- | --- | --- |
| 1700px以上 | 5列 | 通常サイドバー |
| 1051〜1699px | 3列 | 通常サイドバー |
| 681〜1050px | 2列 | 900px以下ではアイコンサイドバー |
| 680px以下 | 1列 | 上部のメニューボタンから開くドロワー |

680px以下では号機グループを折りたため、初期表示は最初のグループだけを開きます。省略されやすい品番・品名は折り返して表示し、資料ボタンやメニューボタンは44px以上のタッチ領域を確保します。iPhone／iPadのセーフエリアと動的なブラウザ高さにも対応しています。

サンプルデータは `sample_data/machines.json` にあります。

本番サーバーへ実行用パッケージだけを導入する場合は、固定済みの `requirements.txt` を使用します。開発PCではテストとRuffを含む `requirements-dev.txt` を使用してください。

## 品質チェック

次のコマンドで、Ruffの静的解析、Python構文確認、全テストを順番に実行します。

```powershell
.\run_tests.bat
```

依存パッケージは実際に検証したバージョンへ固定しています。更新する場合は、一括更新せず、変更対象を明確にして全品質チェックを実行してください。

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
- `DASHBOARD_REVISION_POLL_SECONDS`: 各端末が同期完了を確認する間隔（既定300秒、`0`で自動確認を停止）
- `DOCUMENT_REFRESH_TIMES`: 指定した日本時間にGoogle Sheets「生産中」を再取得・反映し、その時点の全号機についてSharePointとNASも更新
- `AUTO_REFRESH_SECONDS` または `DOCUMENT_REFRESH_TIMES` の同期が正常完了すると、各端末で開いているアプリが更新完了を検知して自動的に再読込する

画面では「最新情報に更新」ボタンを必要以上に広げず、右側に最終更新日時、下側に「工程内検査シート・加工図面を更新するときに押してください。」という説明を1行で表示します。サイドバーには、利用者の操作判断に不要な内部保存方式や内部状態点を表示しません。外部連携エラーなど利用者が把握すべき状態は、画面上部の通知と資料ボタンで表示します。`DOCUMENT_REFRESH_TIMES=13:10` の場合は毎日13:10に完全同期し、`10:30,14:30` のような複数時刻も指定できます。空欄の場合は実行しません。

Google Sheetsのサービスアカウント、共有設定、列構成、NAS設定は [Google Sheets本番設定](docs/GOOGLE_SHEETS_PRODUCTION.md) を参照してください。

## SharePoint工程内検査シート

Microsoft Graph（マイクロソフト グラフ）のアプリケーション認証を使用し、設定したSharePointフォルダとその配下の全サブフォルダを読み取り専用で再帰検索します。GoogleスプレッドシートH列の品番と、拡張子を除いたSharePointファイル名が文字列そのままで完全一致するファイルに加え、`品番-1`、`品番-2`のように末尾へ正の整数を付けたファイルを関連付けます。大文字・小文字、全角・半角、空白、ダッシュ表記が異なる場合は一致として扱いません。

完全一致を最優先し、品番自体が`-1`などで終わる場合も省略しません。1件の場合は検査シートを直接開き、複数の場合は号機カードに件数を表示して、別タブの選択画面へファイル名と保存場所をすべて表示します。

連携コードは実装済みです。利用開始には、Entraアプリの `Sites.Selected` への管理者同意、対象SharePointサイトへの `Read` 権限、`SHAREPOINT_DRIVE_ID`、`SHAREPOINT_FOLDER_ID` の設定が必要です。詳細は [SharePoint工程内検査シート連携](docs/SHAREPOINT_INSPECTION_SHEETS.md) を参照してください。

アプリはSharePoint上のファイルを作成・更新・削除しません。ボタンから開いたファイルで利用者が可能な操作は、その利用者自身のSharePoint権限に従います。

## NAS加工図

`NAS_DRAWING_DIRECTORY` 配下から、GoogleスプレッドシートH列の品番と同名のPDFを検索します。加工図ボタンを押すと、NASパスを公開しない専用APIからPDFを取得し、ローカル配置したPDF.js 5.7.284で1ページ目を専用タブへ表示します。通常表示ではサーバー側のJPEG変換を行いません。PDF.jsの読み込みまたは描画に失敗した場合だけ、既存のJPEGプレビューへ切り替えます。

- ブラウザのタブ名と画面内見出しを「号機_品番_加工図面」形式で表示
- ヘッダー中央に同じ配色の縮小・倍率リセット・拡大ボタンを配置し、50〜300%の範囲外へ進むボタンは無効化
- 表示領域の大きさを変えず、ボタン、マウスホイール、またはタッチ端末の2本指操作で内部図面だけを50〜300%に拡大・縮小
- 表示領域からはみ出した画像を、マウスの左ドラッグで上下左右へ移動
- 表示倍率を図面タブ内に一時保存し、画面の自動再読込後も直前の倍率を復元
- 拡大操作中はCSSで即時反映し、操作停止から250ms後に高精細なCanvasを再描画
- PC、タブレット、スマートフォンごとにCanvasの辺長、総画素数、端末ピクセル比を制限し、使用済みCanvasを解放
- Chrome／EdgeではModern版、SafariとAppleモバイル端末ではLegacy版のPDF.jsを同一バージョンで使用
- PDF APIは `application/pdf`、インライン表示、Range、ETag、Last-Modified、`private, max-age=3600` に対応
- フォールバックJPEGだけを最大64件かつ128MiBまでプロセス内にキャッシュ
- NASの共有パスをブラウザへ公開せず、PDF.js本体、Worker、CMap、標準フォント、WASMもCDNを使わずアプリから配信

アプリを起動するWindowsアカウントには、NASフォルダの読み取り権限が必要です。

初回表示時間はPDF内部の画像構成と端末性能に左右されます。代表PDFではPCの実測で約1.8〜3.7秒でした。`DEBUG=true` のときはブラウザーの開発者コンソールとビューアー要素の `data-*` 属性へ、PDF取得、初期化、初回描画、再描画の時間を記録します。iPhone／iPadはSafari 16.4以降、Androidは現行Chromeを推奨し、本番導入前に実際の端末と社内無線LANで確認してください。PDF.jsを利用できない端末でも、JPEGフォールバックで閲覧を継続します。

## サイドバーの外部リンク

号機一覧の下に区切り線と「外部リンク」見出しを表示し、次の共通リンクを別タブで開きます。リンクはホバー時の背景色と外部リンク記号で識別でき、サイドバーを折りたたんだ場合も外部リンク記号が残ります。

- `SHAREPOINT_PROCESS_INSPECTION_URL`: 工程内検査シート
- `SHAREPOINT_SHIPPING_INSPECTION_URL`: 出荷検査表
- `NOTION_MEASUREMENT_EQUIPMENT_INSPECTION_URL`: 測定機器点検表

## 翌営業日セット内容の定時処理

`SCHEDULED_OPERATIONS_ENABLED=true` の場合、アプリは日本時間の13:00、14:30、15:00に次の処理を行います。誤通知・誤印刷を防ぐため、Google、SharePoint、ARAICHAT、NAS、プリンターの設定確認が終わるまでは `false` にしてください。

- 今日より後の日付シートを順に検索し、最初に存在する `〇〇S` を翌営業日シートとする
- 13:00に `B36:K36` の日付と `B40:K40` の空白以外の品番を列ごとに取得し、B36:K36の日付が対象日より前の列は処理対象から除外する。対象日と同じ日付または対象日より後の日付の列は処理を続行する
- 対象となった品番をSharePointとNASで検索し、確認できない品番がある場合だけARAICHATへ通知する
- 13:00通知の見出しは「【翌営業日セット予定分の検査シート・加工図面確認通知】」とし、品番ごとの対応、工程内検査シートのSharePoint保存場所、加工図面のNAS保存場所を表示する。資料確認用の案内はアプリのサイドバーへ表示しない
- 14:30に13:00と同じシートの `B36:K36` と `B40:K40` を再取得し、同じ日付条件でSharePointとNASを再確認する。その時点でも確認できない品番がある場合だけARAICHATへ再通知する
- 14:30再確認通知の見出しは「【翌営業日セット予定分の再確認（14:30）】」とする
- 15:00に同じシートの `B36:K36` と `B40:K40` を再取得し、同じ日付条件で対象となった品番に一致するPDFを `DRAWING_PRINTER_NAME` へ1品番1部送信する
- 金曜日に月曜日分を処理済みの場合、土日は同じ通知と印刷を繰り返さない
- 15:00時点で確認できない加工図は自動再検索・自動印刷せず、アップロード後に手動で発行する
- 15:00時点で存在したPDFをプリンターへ送信できなかった場合は、未印刷品番だけを `PRINT_RETRY_DELAYS_SECONDS` の間隔で自動再実行する。現在の設定は3分後、5分後、10分後（`180,300,600`）
- 自動再実行後も未完了、または送信結果を判断できない場合だけ、左サイドバーに「印刷の確認」と件数を表示する
- 利用者が「未印刷分を印刷する」を選ぶと、操作中の端末ではなくアプリを起動しているWindows PCから指定プリンターへ送信する
- 送信された可能性がある品番は自動再印刷せず、利用者が用紙を確認して「印刷されている」「印刷されていない」を選ぶ
- 通常時は印刷案内を表示せず、処理履歴と技術的なエラー詳細は開発者向けログだけに記録する

13:00通知、14:30再確認通知、印刷状態は `SCHEDULED_JOB_STATE_PATH` に分けて保存します。ARAICHATの送信結果が通信切断などで不明な場合は、同じ時刻の通知を自動再送しません。状態ファイルが壊れている、形式が不正、読み書きできない場合は、空の状態で再開せず定時通知と印刷を安全停止します。通常のダッシュボード表示は継続し、技術的な詳細は開発者向けログへ記録します。

本番へ切り替える際は、従来の印刷スクリプトやタスクスケジューラを先に停止し、Google Sheets、SharePoint、ARAICHAT、NAS、プリンターを確認したうえで、13:00より前に `SCHEDULED_OPERATIONS_ENABLED=true` へ変更してNSSMサービスを再起動します。13:00以降に有効化すると13:00通知を、14:30以降では再確認通知も、15:00以降では印刷処理も、その日の未処理分として順に開始する可能性があります。従来処理と同時に動かすと二重通知・二重印刷になるため、並行稼働は行いません。

実運用の送信先は、アプリを起動するサーバー用PCに登録済みの第1工場プリンターです。別PCの第2工場プリンターを使用した画面からの再印刷テストでは、ブラウザを操作した端末ではなくアプリ側のWindows環境から印刷ジョブが送信され、用紙が正常に出力されることを確認済みです。

ARAICHATは、実際の翌営業日シート `23S` と日付条件適用後の5品番を使い、ルームID 24へ13:00通知と14:30再確認通知を別々にテスト送信して正常完了を確認済みです。テスト送信では本番の処理済み記録と重複防止キーを使用していません。

## 主な設定

全項目は `.env.example` を参照してください。

- `PERSISTENCE_MODE`: 現在は `memory`
- `APP_PORT`: 待ち受けポート。サーバー用PCは `8013`、ローカル確認で別ポートにしたい場合のみ変更
- `USE_SAMPLE_DATA`: `true`なら外部サービスへ接続せずサンプルを表示
- `GOOGLE_SPREADSHEET_*`: Google Sheets取得設定（A=状態、D=号機、H=品番、I=品名）
- `NAS_DRAWING_DIRECTORY`: 加工図PDFを置くNASフォルダ
- `MICROSOFT_TENANT_ID` / `MICROSOFT_CLIENT_ID` / `MICROSOFT_CLIENT_SECRET`: Microsoft Graph認証
- `SHAREPOINT_DRIVE_ID` / `SHAREPOINT_FOLDER_ID`: 品番別工程内検査シートの検索先
- `SHAREPOINT_PROCESS_INSPECTION_URL` / `SHAREPOINT_SHIPPING_INSPECTION_URL`: サイドバーのSharePoint共通リンク
- `NOTION_MEASUREMENT_EQUIPMENT_INSPECTION_URL`: サイドバーのNotion共通リンク
- `AUTO_REFRESH_SECONDS`: Google Sheetsを定期取得し、品番が新規・変更された号機だけSharePoint・NASを再検索する間隔。`0`で無効
- `DASHBOARD_REVISION_POLL_SECONDS`: ブラウザーが同期完了を確認して号機一覧を再読込する間隔。既定値は300秒、`0`で自動確認を停止
- `DOCUMENT_REFRESH_TIMES`: Google Sheets「生産中」を再取得し、SharePoint・NASも全号機分更新する日本時間。`HH:MM`をカンマ区切りで指定し、空欄で無効
- `SCHEDULED_OPERATIONS_ENABLED`: 13:00の通知、14:30の再確認通知、15:00の印刷を有効化
- `ARAICHAT_BASE_URL` / `ARAICHAT_API_KEY` / `ARAICHAT_ROOM_ID`: ARAICHAT送信設定
- `DRAWING_PRINTER_NAME`: 加工図の送信先Windowsプリンター
- `DRAWING_PRINTER_DISPLAY_NAME`: 利用者画面に表示する分かりやすいプリンター名
- `PRINT_RETRY_DELAYS_SECONDS`: 印刷できなかった場合の自動再実行間隔。秒数をカンマ区切りで指定（既定値 `180,300,600`）
- `DASHBOARD_SNAPSHOT_PATH` / `SCHEDULED_JOB_STATE_PATH`: 再起動時の復元・重複防止ファイル
- `LOG_*`: UTF-8ログのレベル、保存先、ローテーション

`.env`、サービスアカウントJSON、クライアントシークレット、OAuthトークン、秘密鍵はGitへ登録しないでください。

## 起動とテスト

```powershell
python -m app
python -m pytest -q
```

Windowsでは `run_app.bat` と `run_tests.bat` も使用できます。テストはPostgreSQLや外部サービスへ実接続しません。

NSSMで常時起動する場合は、Applicationを仮想環境のPython、Argumentsを `-m app`、AppDirectoryをプロジェクトルートに設定します。待ち受けポートは `.env` の `APP_PORT`（サーバー用PCは `8013`）を使用します。NSSMサービスの実行アカウントには、Google認証JSON、NASフォルダ、`data`、`logs`、および `DRAWING_PRINTER_NAME` のプリンターを利用できる権限が必要です。

## 将来PostgreSQLを有効にする場合

SQLAlchemyモデル、Repository、Alembicマイグレーションは、将来履歴の永続化が必要になった場合の選択肢として残しています。現在は設定も実行も不要です。

`PERSISTENCE_MODE=postgresql` を選択する場合だけ、PostgreSQLの作成、`DATABASE_URL` の設定、`alembic upgrade head` が必要です。

## 今後の検討事項

- 加工図と工程内検査シートの画面分割
- 加工図の複数ページ表示
- SharePointの連番以外の枝番・改訂番号を含む検査シート検索規則
- 最新状態以外の履歴が必要になった場合の永続化

確定事項と未確定事項は [要件整理](docs/REQUIREMENTS.md)、内部構成は [アーキテクチャ](docs/ARCHITECTURE.md)、変更履歴は [CHANGELOG](docs/CHANGELOG.md) を参照してください。

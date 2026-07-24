# アーキテクチャ

## 全体構成

```text
Browser / Tablet
       |
FastAPI routers + Jinja2 templates
       |
Production / Document services
       |
GoogleSheetsMemorySyncService -------- SampleDataService
       |            |                         |
       |            +-- SharePointService     +-- machines.json
       |            |      |
       |            |      +-- Microsoft Graph / SharePoint
       |            |
       |            +-- NasDrawingService -- NAS PDF
       |
MemoryDashboardStore -- プロセス内メモリ -- 号機一覧
       |
       +-- dashboard_snapshot.json

DOCUMENT_REFRESH_TIMES
       +-- GoogleSheetsMemorySyncService.sync()
       +-- Google Sheets「生産中」/ SharePoint / NASを完全同期

ScheduledOperationsService
       +-- Google Sheets 翌営業日 B36:K36 / B40:K40
       +-- SharePoint / NAS 照合 → ARAICHAT（13:00、14:30）
       +-- NAS PDF → Windows Printer（15:00）
       +-- scheduled_job_state.json
```

FastAPIは画面と操作APIを公開します。Jinja2、vanilla CSS、最小限のJavaScriptで構成します。

ブラウザ向けの静的ファイルは `/static` で配信し、サイドバーの ARAI ロゴは `docs/DESIGN` を `/design-assets` としてマウントした画像を参照します。タブ用 favicon、ホーム画面用アイコン、Web App Manifest は `app/static/icons/` と `app/static/manifest.json` に置き、HTML の head は `app/templates/includes/pwa_head.html` で共通化します。号機一覧など共通画面のタブ、ブックマーク、Apple向けWebアプリ名、Manifestの通常名・短縮名は「稼働中工程内検査シート」に統一し、加工図の専用タブだけは「号機_品番_加工図面」とします。表示名、テーマ色、アイコンキャッシュ版数、CSS・JavaScript・Manifestの内容ハッシュは `app/pwa.py` で管理します。Service Workerは使用せず、インストール後も画面の自動再読込や手動更新は通常のブラウザ表示と同じ `app/static/js/app.js` の処理です。

`app/main.py` はアプリの生成と起動・終了処理だけを担当し、バックグラウンド処理の時刻判定と実行制御は `app/scheduling.py` に分離します。これにより、HTTPアプリの初期化と定時処理を個別に確認・テストできます。

## 現在の保存方針

標準設定は `PERSISTENCE_MODE=memory` です。PostgreSQLへ接続・保存しません。

`MemoryDashboardStore` が次をプロセス内に保持します。

- 号機ごとの現在品番、品名、稼働状態
- 工程内検査シートと加工図のURL・取得状態
- 最終更新日時と外部エラー状態

ストアはロック付きで同一プロセス内の複数リクエストから利用できます。返却時はデータを複製し、画面処理から内部状態が意図せず変更されないようにします。

最新の `DashboardData` はJSONスナップショットへ原子的に保存し、再起動時に復元してから完全同期します。外部検索エラー時は前回の正常リンクを再利用しません。メモリと定時処理ロックは複数ワーカー間で共有されないため、Uvicornは1ワーカーで起動します。

## 各層の役割

- `app/routers`: HTTP入力、画面表示、手動更新API
- `app/pwa.py`: PWA表示名、テーマ色、アイコンキャッシュ版数（`STATIC_ICONS_VERSION`）、CSS・JavaScript・Manifestの内容版数（`STATIC_ASSETS_VERSION`）
- `app/scheduling.py`: 定期同期と13:00・14:30・15:00処理の実行制御
- `app/services`: 業務判断、メモリ保持、サンプル切替、外部連携
- `app/services/document_search.py`: SharePointなどの資料検索で共通利用する結果型
- `app/services/next_day_notification.py`: 13:00・14:30の利用者向け通知文生成
- `app/services/memory_store.py`: 画面データのプロセス内保持と最新スナップショット保存
- `app/schemas`: UIとメモリストアで共通利用する型付きデータ
- `app/templates/includes/pwa_head.html`: favicon、apple-touch-icon、manifest、`theme-color`、`application-name`、`apple-mobile-web-app-title` の共通head断片
- `app/utils`: 品番正規化、号機自然順、UTF-8ログ
- `sample_data/machines.json`: 号機構成と画面確認用の初期データ

## データの流れ

本番では `GoogleSheetsMemorySyncService` が「生産中」シートのA/D/H/I列を取得します。同じ同期処理で、設定したSharePointフォルダ配下を再帰検索し、H列の品番をファイル名の拡張子を除いた文字列と正規化せず照合します。完全一致を優先し、完全一致しないファイルは`品番-[1-9][0-9]*`の場合だけ関連ファイルとして扱います。NASは従来どおり同名PDFだけを検索します。D列に存在する号機だけで `MemoryDashboardStore` を置き換え、画面と更新APIは同じストアを共有します。

完全同期では同じ品番が複数号機に設定されていても、SharePointとNASの検索は品番ごとに1回だけ行い、結果を各号機の表示へ展開します。SharePointの照合は、ファイルごとに完全一致または末尾の連番を1回判定し、全品番との総当たりを避けます。

```text
Google Sheets ─┐
SharePoint  ───┼→ GoogleSheetsMemorySyncService → MemoryDashboardStore → 号機一覧
NAS PDF ───────┘
```

サンプルモードでは `SampleDataService` がJSONから号機を生成します。本番では起動時と手動更新時にGoogle Sheets、SharePoint、NASを完全同期します。`AUTO_REFRESH_SECONDS` の間隔ではGoogle Sheetsの前回値と号機番号で比較し、H列の品番が新規・変更された号機だけSharePointとNASを再検索します。`DOCUMENT_REFRESH_TIMES` の指定時刻には、Google Sheetsの「生産中」シートを再取得して画面へ反映し、その時点の全号機についてSharePointとNASも完全更新します。ブラウザはダッシュボードの更新完了時刻を `DASHBOARD_REVISION_POLL_SECONDS` の間隔（既定300秒）と画面復帰時に確認し、表示中の値から変化していればページを再読込します。同期途中や失敗時には更新完了時刻が変わらないため再読込せず、利用者による更新・印刷操作中は再読込を保留します。

更新確認APIは更新完了時刻だけをメモリストアから読み取り、号機一覧全体の複製を行いません。このAPIを各ブラウザが設定間隔で呼び出しても、号機数に比例する不要なコピーが発生しない構成です。

## キャッシュと品番変更

メモリ内の品番管理には `normalize_part_number()` の結果も保持しますが、SharePointとNASの照合にはGoogle Sheetsから取得した元の品番文字列を使用します。完全同期のたびに外部サービスを再検索します。

加工図プレビューはPDFの更新日時とサイズをキーに、最大64件かつ128MiBまでアプリ内へキャッシュします。同じPDFへの同時アクセスは1回だけ変換し、他の要求はその結果を再利用します。

現在の加工図表示は、「号機_品番_加工図面」形式の専用タブで開く1ページ目JPEGプレビューです。ヘッダー中央のボタン操作とタッチ端末の2本指操作で50〜300%に拡大・縮小し、表示領域からはみ出した画像はPointer Eventsとスクロール位置を使ってマウスの左ドラッグで上下左右へ移動します。`100dvh`とセーフエリアを使ってモバイルブラウザの表示高さへ追従します。`NasDrawingPreviewService` を介しているため、工程内検査シートとの分割表示や複数ページ表示へ変更する際も、NAS検索・アクセス制御を保ったまま表示方式を差し替えられます。

SharePoint連携はクライアント資格情報フローでMicrosoft Graphのアクセストークンを取得し、設定した `driveId` / `folderId` を起点に配下の全サブフォルダを幅優先で再帰走査します。各フォルダのページングを最後まで取得し、同じフォルダIDは重複走査しません。権限は `Sites.Selected` と対象サイトの `Read` に限定し、アプリからファイルの作成・更新・削除は行いません。

SharePoint候補は完全一致、連番の数値、ファイル名、相対フォルダの順で安定して並べます。候補が複数の場合、`DocumentState` に候補名・URL・相対フォルダを保持し、`/inspections/{machine_id}` の選択画面へ遷移します。候補URLはHTTPまたはHTTPSだけを許可します。

サイドバーの工程内検査シート、出荷検査表、測定機器点検表は、`.env` に設定した共通URLをそのまま別タブで開く静的リンクです。品番別のSharePoint検索処理とは独立しています。

## レスポンシブUI

号機一覧はCSS Gridで構成し、表示幅に応じて5列、3列、2列、1列へ切り替えます。901px以上は通常サイドバー、681〜900pxはアイコンだけのサイドバー、680px以下は上部メニューボタンとオフキャンバス式サイドバーを使用します。モバイルメニューを閉じている間は`aria-hidden`と`inert`で操作対象から外し、開いている間は背景スクロールと背面操作を抑止します。

号機グループは`details`／`summary`で折りたためる構造です。PC・タブレットでは全グループを開き、680px以下では最初のグループだけを開いて初期スクロール量を抑えます。タッチ端末では品番・品名の省略表示を解除し、資料ボタンとモバイル操作ボタンは44px以上を確保します。

`viewport-fit=cover`、`env(safe-area-inset-*)`、`100dvh`でiPhone／iPadのノッチ、ホームインジケーター、動的なブラウザバーへ対応します。レスポンシブ構造は`tests/test_responsive_layout.py`で静的に確認し、代表的なPC、iPad、iPhone、Android相当の表示幅でもブラウザ検証します。

## 静的ファイルとPWA

| 種別 | 配置 | 用途 |
| --- | --- | --- |
| CSS / JavaScript | `app/static/css/`、`app/static/js/` | レスポンシブレイアウト、モバイルメニュー、図面操作、クライアント側の更新検知 |
| アプリアイコン一式 | `app/static/icons/` | favicon、Apple Touch Icon、manifest 用 192px / 512px。マスター画像は `machine_document_portal.png` |
| Web App Manifest | `app/static/manifest.json` | 表示名・短縮名「稼働中工程内検査シート」、`display: standalone`、テーマ色 |
| サイドバーロゴ | `docs/DESIGN/arai_logo.png`（`/design-assets/`） | 画面内ブランド表示。PWAアイコンとは別 |

アイコン画像を差し替えた場合は、必要なサイズを再生成し、`app/pwa.py` の `STATIC_ICONS_VERSION` を更新してfaviconのブラウザキャッシュを無効化します。CSS、JavaScript、Manifestは各ファイルの内容から`STATIC_ASSETS_VERSION`を自動生成するため、変更時の手動更新は不要です。`manifest.json` 内の`name`／`short_name`／`theme_color`／`background_color`と`app/pwa.py`の定数は整合させます。

Service Worker は導入していないため、オフライン動作やクライアント側の HTML キャッシュ制御は行いません。Chrome / Edge の「アプリとしてインストール」は HTTPS 環境で利用しやすくなりますが、データ同期と画面再読込は従来どおりサーバー API と `app.js` のポーリングに依存します。

## 定時通知と印刷

13:00に翌営業日シートの `B36:K36` と `B40:K40` をGoogle Sheetsの1回の一括取得で読み込み、列ごとに日付と品番を対応させます。B36:K36の日付が対象日より前の列を除外し、対象日と同じ日付または対象日より後の列だけをSharePointとNASで確認します。13:00通知の見出しは「【翌営業日セット予定分の検査シート・加工図面確認通知】」です。14:30に13:00で確定した同じシートを再取得し、同じ日付条件で残っている不足だけを「【翌営業日セット予定分の再確認（14:30）】」として、別の冪等キーで再通知します。通知本文は品番単位で必要な対応をまとめ、SharePointとNASの保存場所を表示します。資料確認用のサイドバー状態は保持しません。15:00にも同じシートの両範囲を再取得し、同じ日付条件で対象となった品番について、NASに存在するPDFをRAW印刷ジョブとしてWindowsプリンターへ送信します。対象日付、シート名、`sheetId`、スプレッドシートIDから重複防止キーを生成し、13:00通知、14:30通知、品番別印刷状態をJSONへ原子的に保存します。

15:00時点で存在したPDFをプリンターへ送信できなかった品番は、`PRINT_RETRY_DELAYS_SECONDS` の間隔で自動再実行します。既定の `180,300,600` では、最初の失敗から3分後、5分後、10分後に未印刷品番だけを処理します。15:00時点でPDFが存在しない品番は `manual_required` として記録し、自動再検索・自動印刷・「印刷の確認」サイドバーの対象から除外します。品番ごとの `pending`、`failed`、`manual_required`、`uncertain`、`submitted` を同じJSONへ保存し、アプリ再起動後も送信済み品番を除外します。プリンター送信の自動再実行を終えても未完了の場合だけ、左サイドバーに利用者向けの「印刷の確認」を表示します。手動操作もサーバー側の `RawPdfPrinter` を呼び出すため、ブラウザを開いている端末のプリンターは使用しません。

本番切替では、従来の印刷スクリプトやタスクスケジューラを停止してから定時処理を有効化します。スケジューラーは起動後30秒ごとに日本時間を確認するため、13:00以降の起動では13:00処理を、14:30以降では再確認処理も、15:00以降では印刷処理も順に開始します。旧処理と状態ファイルを共有しないため、両方を同時稼働させません。

## エラー時の扱い

外部検索に失敗した場合は前回の正常リンクを保持せず、対象資料をエラー状態にします。ARAICHATや印刷の処理は正常終了した項目だけを完了として記録します。ARAICHATの送信結果が不明な場合は `ambiguous` として自動再送を止めます。印刷データを書き込み始めた後に結果が不明になった品番も自動再印刷せず、利用者による用紙確認を待ちます。利用者画面には現在必要な操作だけを表示し、処理履歴と技術的なエラー詳細はログだけに記録します。

## PostgreSQL構成

SQLAlchemyモデル、Repository、Alembicマイグレーションは、将来永続化が必要になった場合の選択肢として残しています。`PERSISTENCE_MODE=postgresql` を明示しない限り、DB Sessionは生成されません。

## ログ

ログは業務データの保存先ではありません。Python `logging` と `RotatingFileHandler` を使用し、動作状況とエラー詳細だけをUTF-8でファイル出力します。認証情報や資料内容は記録しません。

## 品質管理

実行依存は `requirements.txt`、テスト・静的解析を含む開発依存は `requirements-dev.txt` に固定します。`run_tests.bat` はRuffの静的解析、Python構文確認、pytestを順番に実行します。

定時処理状態が存在しない場合だけ空の初期状態を生成します。状態ファイルが壊れている、形式が不正、読み書きできない場合は新規状態として処理を続けず、定時通知・自動印刷・手動再印刷を安全停止します。通常のダッシュボード表示は継続し、技術的な詳細は開発者向けログだけに記録します。

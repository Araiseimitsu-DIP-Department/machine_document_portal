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
       +-- GoogleSheetsMemorySyncService.refresh_documents()
       +-- SharePoint / NASだけを全号機分更新

ScheduledOperationsService
       +-- Google Sheets 翌営業日 B40:K40
       +-- SharePoint / NAS 照合 → ARAICHAT（13:00）
       +-- NAS PDF → Windows Printer（15:00）
       +-- scheduled_job_state.json
```

FastAPIは画面と操作APIを公開します。Jinja2、vanilla CSS、最小限のJavaScriptで構成します。

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
- `app/services`: 業務判断、メモリ保持、サンプル切替、外部連携の拡張点
- `app/services/memory_store.py`: 画面データのプロセス内保持と最新スナップショット保存
- `app/schemas`: UIとメモリストアで共通利用する型付きデータ
- `app/utils`: 品番正規化、号機自然順、UTF-8ログ
- `sample_data/machines.json`: 号機構成と画面確認用の初期データ

## データの流れ

本番では `GoogleSheetsMemorySyncService` が「生産中」シートのA/D/H/I列を取得します。同じ同期処理で、設定したSharePointフォルダ配下を再帰検索し、H列の品番をファイル名の拡張子を除いた文字列と正規化せず完全一致で照合します。NASからも同名PDFを検索します。D列に存在する号機だけで `MemoryDashboardStore` を置き換え、画面と更新APIは同じストアを共有します。

```text
Google Sheets ─┐
SharePoint  ───┼→ GoogleSheetsMemorySyncService → MemoryDashboardStore → 号機一覧
NAS PDF ───────┘
```

サンプルモードでは `SampleDataService` がJSONから号機を生成します。本番では起動時と手動更新時にGoogle Sheets、SharePoint、NASを完全同期します。`AUTO_REFRESH_SECONDS` の間隔ではGoogle Sheetsの前回値と号機番号で比較し、H列の品番が新規・変更された号機だけSharePointとNASを再検索します。`DOCUMENT_REFRESH_TIMES` の指定時刻には、Google Sheetsを読まずに現在の全号機についてSharePointとNASだけを完全更新します。

## キャッシュと品番変更

メモリ内の品番管理には `normalize_part_number()` の結果も保持しますが、SharePointとNASの照合にはGoogle Sheetsから取得した元の品番文字列を使用します。完全同期のたびに外部サービスを再検索します。

加工図プレビューはPDFの更新日時とサイズをキーに、最大64件かつ128MiBまでアプリ内へキャッシュします。同じPDFへの同時アクセスは1回だけ変換し、他の要求はその結果を再利用します。

現在の加工図表示は、専用の別タブで開く1ページ目JPEGプレビューです。`NasDrawingPreviewService` を介しているため、工程内検査シートとの分割表示や複数ページ表示へ変更する際も、NAS検索・アクセス制御を保ったまま表示方式を差し替えられます。

SharePoint連携はクライアント資格情報フローでMicrosoft Graphのアクセストークンを取得し、設定した `driveId` / `folderId` を起点に配下の全サブフォルダを幅優先で再帰走査します。各フォルダのページングを最後まで取得し、同じフォルダIDは重複走査しません。権限は `Sites.Selected` と対象サイトの `Read` に限定し、アプリからファイルの作成・更新・削除は行いません。

サイドバーの工程内検査シート、出荷検査表、測定機器点検表は、`.env` に設定した共通URLをそのまま別タブで開く静的リンクです。品番別のSharePoint検索処理とは独立しています。

## 定時通知と印刷

13:00に翌営業日シートの `B40:K40` を取得し、SharePointとNASの不足資料をARAICHATルームへ送信します。15:00には13:00に決定した同じシートを再取得し、NASに存在するPDFをRAW印刷ジョブとしてWindowsプリンターへ送信します。対象日付、シート名、`sheetId`、スプレッドシートIDから重複防止キーを生成し、通知状態と品番別印刷状態をJSONへ原子的に保存します。

## エラー時の扱い

外部検索に失敗した場合は前回の正常リンクを保持せず、対象資料をエラー状態にします。ARAICHATや印刷の処理は正常終了した項目だけを完了として記録します。ARAICHATの送信結果が不明な場合は `ambiguous` として自動再送を止めます。

## PostgreSQL構成

SQLAlchemyモデル、Repository、Alembicマイグレーションは、将来永続化が必要になった場合の選択肢として残しています。`PERSISTENCE_MODE=postgresql` を明示しない限り、DB Sessionは生成されません。

## ログ

ログは業務データの保存先ではありません。Python `logging` と `RotatingFileHandler` を使用し、動作状況とエラー詳細だけをUTF-8でファイル出力します。認証情報や資料内容は記録しません。

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
       |                                      |
MemoryDashboardStore                         machines.json
       |
プロセス内メモリ
       |
Google Sheets（生産中）
```

FastAPIは画面と操作APIを公開します。Jinja2、vanilla CSS、最小限のJavaScriptで構成します。

## 現在の保存方針

標準設定は `PERSISTENCE_MODE=memory` です。PostgreSQLへ接続・保存しません。

`MemoryDashboardStore` が次をプロセス内に保持します。

- 号機ごとの現在品番、品名、稼働状態
- 工程内検査シートと加工図のURL・取得状態
- 正規化品番をキーとした資料リンクキャッシュ
- 最終更新日時、外部エラー、前回データ状態

ストアはロック付きで同一プロセス内の複数リクエストから利用できます。返却時はデータを複製し、画面処理から内部状態が意図せず変更されないようにします。

アプリ再起動、プロセス終了、またはストアのクリアで状態は消えます。複数ワーカー間では共有されないため、当面はUvicornを1ワーカーで起動します。

## 各層の役割

- `app/routers`: HTTP入力、画面表示、手動更新API
- `app/services`: 業務判断、メモリ保持、サンプル切替、外部連携の拡張点
- `app/services/memory_store.py`: 画面データと資料キャッシュのプロセス内保持
- `app/schemas`: UIとメモリストアで共通利用する型付きデータ
- `app/utils`: 品番正規化、号機自然順、UTF-8ログ
- `sample_data/machines.json`: 号機構成と画面確認用の初期データ

## データの流れ

本番では `GoogleSheetsMemorySyncService` が「生産中」シートのA/D/H/I列を取得し、D列に存在する号機だけで `MemoryDashboardStore` を置き換えます。画面と更新APIは同じストアを共有します。

```text
Google Sheets → GoogleSheetsMemorySyncService → MemoryDashboardStore → 号機一覧
```

サンプルモードでは `SampleDataService` がJSONから号機を生成します。本番ではアプリが `AUTO_REFRESH_SECONDS` の設定値に従ってGoogle Sheetsを1回だけ定期同期し、各ブラウザはメモリ上の最新状態を再読込します。`0`は自動更新を無効にします。

## キャッシュと品番変更

検索キーは `normalize_part_number()` の結果です。同一品番の工程内検査シートと加工図の結果はメモリキャッシュから再利用します。有効期限は `MEMORY_CACHE_TTL_SECONDS` で設定し、`0`は期限なしです。キャッシュは再起動で消えるため、起動後の初回取得時には外部サービスを再検索します。

加工図プレビューはPDFの更新日時とサイズをキーに、最大64件かつ128MiBまでアプリ内へキャッシュします。同じPDFへの同時アクセスは1回だけ変換し、他の要求はその結果を再利用します。

現在の加工図表示は暫定的な1ページ目JPEGプレビューです。`NasDrawingPreviewService` を介しているため、別タブPDF表示や工程内検査シートとの分割表示へ変更する際も、NAS検索・アクセス制御を保ったまま表示方式を差し替えられます。

## エラー時のフォールバック

外部検索に失敗し、同じプロセス内に前回の正常リンクが残っている場合は、そのリンクを保持して `stale`（前回データ）表示にします。再起動後は前回データがないため、外部エラー状態をそのまま表示します。

## PostgreSQL構成

SQLAlchemyモデル、Repository、Alembicマイグレーションは、将来永続化が必要になった場合の選択肢として残しています。`PERSISTENCE_MODE=postgresql` を明示しない限り、DB Sessionは生成されません。

## ログ

ログは業務データの保存先ではありません。Python `logging` と `RotatingFileHandler` を使用し、動作状況とエラー詳細だけをUTF-8でファイル出力します。認証情報や資料内容は記録しません。

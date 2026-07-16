# アーキテクチャ

## 全体構成

```text
Browser / Tablet
       |
FastAPI routers + Jinja2 templates
       |
Production / Document services
       |
MemoryDashboardStore -------- SampleDataService
       |                              |
プロセス内メモリ                 machines.json
       |
Google Sheets / Google Drive / SharePoint（第2～4段階）
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

第1段階では `SampleDataService` がJSONから号機を生成し、`MemoryDashboardStore` が保持します。画面と手動更新APIは同じストアを共有します。

```text
machines.json → SampleDataService → MemoryDashboardStore → 号機一覧
```

第2段階以降はGoogleスプレッドシートから取得した号機情報でメモリ状態を置き換えます。前回の正規化品番と比較し、変更された号機だけ資料を再検索します。

## キャッシュと品番変更

検索キーは `normalize_part_number()` の結果です。同一品番の工程内検査シートと加工図の結果はメモリキャッシュから再利用します。有効期限は `MEMORY_CACHE_TTL_SECONDS` で設定し、`0`は期限なしです。キャッシュは再起動で消えるため、起動後の初回取得時には外部サービスを再検索します。

## エラー時のフォールバック

外部検索に失敗し、同じプロセス内に前回の正常リンクが残っている場合は、そのリンクを保持して `stale`（前回データ）表示にします。再起動後は前回データがないため、外部エラー状態をそのまま表示します。

## PostgreSQL構成

SQLAlchemyモデル、Repository、Alembicマイグレーションは、将来永続化が必要になった場合の選択肢として残しています。`PERSISTENCE_MODE=postgresql` を明示しない限り、DB Sessionは生成されません。

## ログ

ログは業務データの保存先ではありません。Python `logging` と `RotatingFileHandler` を使用し、動作状況とエラー詳細だけをUTF-8でファイル出力します。認証情報や資料内容は記録しません。

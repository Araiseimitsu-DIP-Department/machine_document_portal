# 稼働中工程内検査シート — 自動更新・定時処理メモ

---

## 1. アプリの役割

Googleスプレッドシート「生産中」の号機情報をもとに、SharePoint（検査シート・数値検査用）と NAS（加工図PDF）を検索し、号機一覧画面に表示する社内Webアプリ。

- データはサーバーPCのメモリに保持
- 再起動時はスナップショットから復元したうえで再同期
- PostgreSQL は使用しない（`PERSISTENCE_MODE=memory`）

---

## 2. 更新の種類（一覧）

| 種類 | トリガー | Google Sheets | SharePoint / NAS | 画面の自動再読込 |
| --- | --- | --- | --- | --- |
| 起動時同期 | アプリ起動 | 全取得 | 全号機 完全検索 | 起動直後の表示 |
| 手動更新 | 「最新情報に更新」ボタン | 全取得 | 全号機 完全検索 | ボタン押下後 |
| 定期同期 | `AUTO_REFRESH_SECONDS` ごと | 全取得 | 品番が変わった号機だけ再検索 | 成功時に検知 |
| 定時完全同期 | `DOCUMENT_REFRESH_TIMES` の時刻 | 全取得 | 全号機 完全検索 | 成功時に検知 |
| 翌営業日処理 | 毎日 13:00 / 14:30 / 15:00（有効時のみ） | 翌営業日シート | 不足確認・印刷用 | 印刷状態のみ別途 |

---

## 3. 現在の本番設定（.env）

| 設定 | 現在値 | 意味 |
| --- | --- | --- |
| `AUTO_REFRESH_SECONDS` | 1800（30分） | 定期同期の間隔。0 で無効 |
| `DOCUMENT_REFRESH_TIMES` | 13:10 | 毎日13:10に全号機の完全同期（日本時間） |
| `DASHBOARD_REVISION_POLL_SECONDS` | 300（5分） | 各ブラウザが同期完了を確認する間隔 |
| `SCHEDULED_OPERATIONS_ENABLED` | false | 13:00通知・14:30再確認・15:00印刷は未稼働 |
| `APP_PORT` | 8013 | 待ち受けポート |
| `PERSISTENCE_MODE` | memory | DBは使わない |
| `USE_SAMPLE_DATA` | false | 本番モード |

**注意:** `USE_SAMPLE_DATA=true` の場合、自動同期・定時処理はすべて動かない。

---

## 4. 各更新の詳細仕様

### 4-1. 起動時・手動更新（完全同期）

**いつ**

- アプリ起動時
- 画面の「最新情報に更新」ボタン

**処理内容**

1. Google Sheets「生産中」シートを取得（A=状態, D=号機, H=品番, I=品名）
2. D列に号機がある行だけ画面に表示（追加・削除は次回同期で反映）
3. 全号機について SharePoint・NAS を検索

**実装**

- 起動時: `app/main.py`
- 手動: `POST /api/refresh`
- 処理本体: `GoogleSheetsMemorySyncService.sync()`

---

### 4-2. 定期同期（差分のみ資料再検索）

**いつ**

- 起動後、`AUTO_REFRESH_SECONDS`（現在30分）ごと

**処理内容**

1. Google Sheets を再取得
2. H列の品番が新規・変更された号機だけ SharePoint・NAS を再検索
3. A列（状態）や I列（品名）だけの変更では資料は再検索しない

**失敗時**

- ログに記録
- 更新完了時刻は変わらない → 画面は再読込しない

**実装**

- `app/scheduling.py` → `sync_changed()`

---

### 4-3. 定時完全同期

**いつ**

- `DOCUMENT_REFRESH_TIMES` で指定した日本時間（現在は毎日 13:10）

**処理内容**

1. Google Sheets「生産中」を再取得・画面反映
2. その時点の全号機について SharePoint・NAS を完全再検索

**複数時刻の指定例**

- `10:30,14:30`（カンマ区切り）
- 空欄で無効

**実装**

- `app/scheduling.py` → `sync()`

---

### 4-4. 資料の照合ルール

| 資料 | 検索先 | 一致条件 |
| --- | --- | --- |
| 工程内検査シート | SharePoint フォルダ配下 | 品番と完全一致、または `品番-1`, `品番-2` … |
| 数値検査用 | 出荷検査表と同じ SharePoint | 完全一致、または品番直後が `_` `-` スペース `・` |
| 加工図 | NAS の PDF | 品番と完全一致のファイル名 |

---

## 5. ブラウザの自動再読込

サーバー側の同期が正常完了すると、メモリ上の「最終更新日時」が更新される。

各端末のブラウザは次のタイミングで `/api/dashboard/revision` を確認し、時刻が変わっていればページを再読込する。

- 5分ごと（`DASHBOARD_REVISION_POLL_SECONDS=300`）
- タブに戻ったとき（画面が非表示→表示になったとき）

### 再読込しない場合

- 同期が失敗・途中のとき（更新完了時刻が変わらない）
- 利用者が「最新情報に更新」や印刷操作中のとき（操作完了後に再読込）
- 号機一覧以外の画面（加工図タブなど）は対象外
  - 加工図は倍率をタブ内に保持し、再読込後も復元

### 静的ファイルのキャッシュ

- CSS / JS は内容ハッシュ付きURLで配信
- Service Worker は使用しない

---

## 6. 翌営業日の定時処理（現在未有効）

`SCHEDULED_OPERATIONS_ENABLED=false` のため、現在は動いていない。

本番切替時は、従来のスクリプト・タスクスケジューラを止めてから有効化すること。並行稼働すると二重通知・二重印刷になる。

| 時刻 | 処理内容 |
| --- | --- |
| 13:00 | 翌営業日シート（`〇〇S`）の B36:K36（日付）と B40:K40（品番）を取得。対象日より前の列は除外。不足があれば ARAICHAT 通知 |
| 14:30 | 同じシートを再取得。まだ不足があれば再通知（別の重複防止キー） |
| 15:00 | 同条件で NAS にある PDF を Windows プリンターへ 1品番1部印刷 |

### その他のルール

- 金曜に月曜分を処理済みなら、土日は繰り返さない
- 15:00 時点で無い PDF は自動印刷しない（アップロード後に手動）
- 印刷失敗時のみ 3分・5分・10分後に自動再試行（`PRINT_RETRY_DELAYS_SECONDS=180,300,600`）
- 状態は `data/scheduled_job_state.json` に保存（重複通知・二重印刷防止）
- 時刻判定は 30秒ごとに日本時間を確認（`app/scheduling.py`）

---

## 7. データの保存場所

| ファイル | 内容 |
| --- | --- |
| `data/dashboard_snapshot.json` | 号機一覧の最新スナップショット（再起動時復元用） |
| `data/scheduled_job_state.json` | 定時通知・印刷の処理済み状態 |
| `logs/` | UTF-8 ローテーションログ（技術的な詳細） |

---

## 8. 運用上の注意

1. Uvicorn は1ワーカーで起動する（メモリと定時処理ロックはプロセス間で共有されない）
2. NSSM 常時起動時は、実行アカウントに NAS・プリンター・認証JSON の権限が必要
3. 外部エラー時は前回の正常リンクを再利用せず、資料ボタンをエラー表示にする
4. 定時処理の状態ファイルが壊れた場合は通知・印刷を安全停止。号機一覧の表示は継続
5. `.env` を変更したら NSSM サービス再起動が必要

---

## 9. 処理の流れ

```
[更新トリガー]
  ├ 起動時
  ├ 手動ボタン
  ├ AUTO_REFRESH（30分ごと）
  └ DOCUMENT_REFRESH（13:10）

        ↓

[サーバーPC]
  GoogleSheetsMemorySyncService
        ↓
  MemoryDashboardStore
        ↓
  dashboard_snapshot.json

        ↓

[各端末ブラウザ]
  5分ごと + 画面復帰時に revision 確認
        ↓
  変更あればページ再読込
```

---

## 10. 最近の主な変更（2026-07-31 時点）

- 数値検査用列を号機カードに追加（3資料列構成）
- 加工図を PDF.js で高精細表示（失敗時のみ JPEG フォールバック）
- ホーム画面追加を `display: browser` に変更（通常ブラウザで起動）
- `DASHBOARD_REVISION_POLL_SECONDS` を分離（サーバー同期間隔とブラウザ確認間隔を別管理）

詳細は `docs/CHANGELOG.md` を参照。

---

## 11. 確認・トラブル時の見方

| 確認したいこと | 見る場所 |
| --- | --- |
| 同期が動いたか | `logs/` のログ（`Scheduled ... completed` など） |
| 最終更新時刻 | 号機一覧画面「最新情報に更新」の右側 |
| 定時処理の状態 | `data/scheduled_job_state.json` |
| 手動で全同期 | 画面ボタン、または `POST /api/refresh` |
| 仕様の詳細 | `README.md` / `docs/ARCHITECTURE.md` / `docs/REQUIREMENTS.md` |

---

## 12. 関連ドキュメント（リポジトリ内）

- `README.md` — 全体概要・設定一覧
- `docs/ARCHITECTURE.md` — 内部構成・データの流れ
- `docs/REQUIREMENTS.md` — 要件・確定事項
- `docs/CHANGELOG.md` — 変更履歴
- `docs/GOOGLE_SHEETS_PRODUCTION.md` — Google Sheets 本番設定
- `docs/SHAREPOINT_INSPECTION_SHEETS.md` — SharePoint 連携設定

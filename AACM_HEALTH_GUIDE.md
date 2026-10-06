# AACM 連携ヘルスチェック実装ガイド (AACM Health Check Guide)

このドキュメントは、管理棟アプリ **AACM (Arai App Control Manager)** に新規アプリや既存アプリを登録・監視させる際、
**「ヘルス異常」「タイムアウト（2.0秒）」を起こさず安定稼働させるためのヘルスチェック実装仕様・落とし穴と対策・テンプレートコード** をまとめたものです。

---

## 1. AACM のヘルスチェック監視仕様

AACM のバックエンド（`app/infrastructure/health_checker.py`）は以下のルールでアプリを監視します。

| 項目 | 仕様 | 注意点 |
| :--- | :--- | :--- |
| **タイムアウト** | **2.0 秒** (`timeout=2.0`) | **2秒以内にレスポンス完了が必須**。DB接続の遅延等で2秒を超えると「タイムアウト」判定。 |
| **監視間隔** | フロントエンド表示時は **5 秒ごと**、バックグラウンド時は定周期（通常1分ごと） | 毎秒のような高頻度接続にも耐える軽量さが必須。 |
| **リダイレクト** | `follow_redirects=False` | **リダイレクト（301/302）は不可**。末尾スラッシュの有無などでリダイレクトされると fail 判定。 |
| **判定条件** | HTTP ステータス `200` かつ JSON の `"status": "ok"` | 200 以外、または status が "ok" 以外はすべて異常扱い。 |
| **期待する JSON** | `{"status": "ok", "version": "1.0", "access_total": <int>}` | `version` と `access_total` は AACM の画面・グラフ表示に自動反映される。 |

### 期待されるレスポンス例 (HTTP 200)
```json
{
  "status": "ok",
  "version": "1.0",
  "access_total": 1284,
  "database": "ok"
}
```

---

## 2. Windows 環境で発生する重要トラップと対策

### ① Windows の `localhost` による IPv6 (`::1`) 2秒遅延問題【最重要】
- **原因**:
  - Windows では `localhost` の名前解決で IPv6（`::1`）が優先されます。
  - Webサーバー（Waitress や Uvicorn 等）を IPv4（`127.0.0.1`）のみで起動していると、AACM が `http://localhost:.../health` にアクセスした際に **IPv6 への TCP SYN がタイムアウト（約2秒）するまで待たされてから IPv4 にフォールバック** します。
  - このため、アプリ側の処理がどれだけ速くても接続だけで約 2 秒消費し、AACM の 2.0 秒タイムアウトに抵触して「ヘルス異常（タイムアウト）」になります。
- **対策**:
  1. **アプリ側**: Waitress 待受を IPv4 と IPv6 の **デュアルスタック** でリッスンする。
     ```python
     # Waitress の場合: listen 引数で 127.0.0.1 と [::1] の両方を指定
     serve(app, listen=f"127.0.0.1:{port} [::1]:{port}", threads=8)
     ```
  2. **AACM 設定側**: `apps.yaml` の `health_url` には `localhost` ではなく **`http://127.0.0.1:ポート/...`** を指定する。

---

### ② リモート DB 疎通チェックの遅延・タイムアウト
- **原因**:
  - `/health` の中で毎回 MySQL や PostgreSQL 等の DB 接続を行うと、リモート接続のハンドシェイクに 1.0〜1.3 秒かかります。
  - 5 秒間隔でポーリングされた場合、DB 接続が枯渇したり、ネットワークのわずかなジッターで 2.0 秒を超過します。
  - `connect_timeout` を未指定だと、万一 DB が停止・再起動した際にソケットが 10〜60 秒ハングし、アプリ全体が停止します。
- **対策**:
  1. DB 接続には必ず **`connect_timeout=1.0, read_timeout=1.0`** を設定する。
  2. ヘルスチェックの DB 疎通結果は **短時間（10〜15 秒）メモリキャッシュ** する。
     - キャッシュヒット時は **1ms 以内** に即答し、DB への接続頻度を 1/2〜1/3 に低減。

---

### ③ `/health` アクセスによるカウンター水増し・ログ肥大化
- **原因**:
  - AACM が 5 秒ごとにポーリングするため、通常のページアクセスと同様にカウントすると 1 時間で 720 回、1 日で 17,000 回以上 `access_total` が増えてしまい、実際のユーザー利用数が把握できなくなります。
  - また、ログファイル（`app.log`）が `/health 200` のログだけで溢れます。
- **対策**:
  - `before_request`（カウント処理）および `after_request`（アクセスログ出力）で `/health` を除外する。

---

## 3. 実装テンプレート (Flask + Waitress)

Python (Flask + Waitress) で新規アプリを作成する際、そのままコピー＆ペーストして使える実装テンプレートです。

```python
import datetime
import json
import logging
from logging.handlers import RotatingFileHandler
import os
import sys
import threading
import time

from flask import Flask, jsonify, request
import pymysql
from waitress import serve

app = Flask(__name__)

# app.log の初期化は _load_access_total() より前に行う（詳細は第6章）
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.getenv("APP_DATA_DIR") or BASE_DIR
os.makedirs(DATA_DIR, exist_ok=True)
logger = logging.getLogger("aacm_app")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(
        os.path.join(DATA_DIR, "app.log"),
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(handler)
    logger.propagate = False

# ==============================================================================
# 1. 累計アクセス数（access_total）の永続化管理
# ==============================================================================
ACCESS_COUNTER_FILE = os.path.join(DATA_DIR, "access_counter.json")
_access_total = 0
_counter_lock = threading.Lock()


def _load_access_total():
    global _access_total
    if os.path.exists(ACCESS_COUNTER_FILE):
        try:
            with open(ACCESS_COUNTER_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                _access_total = int(data.get("access_total", 0))
        except Exception as e:
            logger.warning(f"access_counter.json 読込失敗: {e}")


def increment_access_total():
    global _access_total
    with _counter_lock:
        _access_total += 1
        total = _access_total
        try:
            tmp = ACCESS_COUNTER_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"access_total": total}, f)
            os.replace(tmp, ACCESS_COUNTER_FILE)
        except Exception:
            pass
        return total


def get_access_total():
    with _counter_lock:
        return _access_total


_load_access_total()


# ==============================================================================
# 2. 監視アクセス・静的ファイルの除外フィルター
# ==============================================================================
def is_monitoring_or_static(path: str) -> bool:
    """ヘルスチェックや静的アセットなど、集計・ログから除外するパスを判定"""
    if path.startswith("/static/") or path in ("/favicon.ico", "/robots.txt"):
        return True
    clean = path.rstrip("/")
    if clean.endswith("/health"):
        return True
    return False


@app.before_request
def record_access_count():
    # ユーザーアクセスのみカウント（ヘルスチェックや静的アセットは除外）
    if is_monitoring_or_static(request.path):
        return
    increment_access_total()


@app.after_request
def log_request_result(response):
    if not is_monitoring_or_static(request.path):
        remote = request.headers.get("X-Forwarded-For", request.remote_addr or "-")
        logger.info(f'{remote} "{request.method} {request.path}" {response.status_code}')
    return response


# ==============================================================================
# 3. キャッシュ付き DB 疎通チェック & ヘルスエンドポイント
# ==============================================================================
_last_db_check_time = 0.0
_last_db_status = "ok"
_db_check_lock = threading.Lock()


def check_db_health(cache_ttl_seconds: float = 10.0) -> str:
    """DB疎通チェック（AACM等の高頻度チェックで遅延・枯渇が出ないよう短時間キャッシュ）"""
    global _last_db_check_time, _last_db_status
    now = time.time()
    if now - _last_db_check_time < cache_ttl_seconds:
        return _last_db_status

    with _db_check_lock:
        now = time.time()
        if now - _last_db_check_time < cache_ttl_seconds:
            return _last_db_status
        try:
            # 必ず connect_timeout / read_timeout を設定してハングを防止
            conn = pymysql.connect(
                host=os.environ.get("DB_HOST", "192.168.1.111"),
                port=int(os.environ.get("DB_PORT", "3306")),
                user=os.environ.get("DB_USER", "user"),
                password=os.environ.get("DB_PASS", "password"),
                db=os.environ.get("DB_NAME", "my_db"),
                connect_timeout=1.0,
                read_timeout=1.0,
            )
            cur = conn.cursor()
            cur.execute("SELECT 1")
            cur.fetchone()
            cur.close()
            conn.close()
            _last_db_status = "ok"
        except Exception as e:
            _last_db_status = f"ng: {e}"
            logger.warning(f"ヘルスチェックDB疎通エラー: {e}")
        _last_db_check_time = time.time()
        return _last_db_status


# strict_slashes=False により /health と /health/ の両方にリダイレクトなしで 200 応答
@app.route("/health", methods=["GET"], strict_slashes=False)
def health():
    db_status = check_db_health()
    is_healthy = (db_status == "ok")
    return (
        jsonify({
            "status": "ok" if is_healthy else "error",
            "version": "1.0",
            "access_total": get_access_total(),
            "database": db_status,
        }),
        200 if is_healthy else 503
    )


# ==============================================================================
# 4. サーバー起動（IPv4 / IPv6 デュアルスタック対応）
# ==============================================================================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8001"))
    host_env = os.environ.get("HOST", "127.0.0.1")

    # Windows で localhost 宛ての IPv6 (::1) がタイムアウトするのを防ぐためデュアルスタック待受
    if host_env in ("127.0.0.1", "localhost"):
        listen_arg = f"127.0.0.1:{port} [::1]:{port}"
    elif host_env == "0.0.0.0":
        listen_arg = f"*:{port}"
    else:
        listen_arg = f"{host_env}:{port}"

    logger.info(f"Waitress 起動待受: {listen_arg}")
    serve(app, listen=listen_arg, threads=8)
```

---

## 4. FastAPI (Uvicorn) での実装例

FastAPI で作成する場合は以下のように実装します。

```python
from fastapi import FastAPI, Response, status
import time

app = FastAPI()

_access_total = 0
_last_db_time = 0.0
_last_db_status = "ok"

@app.get("/health")
def health(response: Response):
    global _last_db_time, _last_db_status
    # DBチェックやキャッシュ処理...
    is_healthy = (_last_db_status == "ok")
    if not is_healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": "ok" if is_healthy else "error",
        "version": "1.0",
        "access_total": _access_total,
        "database": _last_db_status
    }

# Uvicorn 起動時の注意:
# uvicorn app:app --host 127.0.0.1 --port 8000 で起動した場合、IPv6 (::1) では待ち受けません。
# そのため AACM の health_url には必ず "http://127.0.0.1:8000/health" を指定してください。
```

---

## 5. AACM 側（`apps.yaml`）の設定推奨ルール

AACM 管理棟アプリの `apps.yaml` にアプリを追加する際は、以下の設定を推奨します。

```yaml
apps:
  - id: machine_check
    name: 機械点検管理システム
    # 【推奨】localhost ではなく 127.0.0.1 を指定するとホスト名解決遅延がゼロになる
    health_url: http://127.0.0.1:8001/machine_check_app/health
    url: http://127.0.0.1:8001/machine_check_app/
    start_cmd: "powershell -ExecutionPolicy Bypass -File start.ps1"
    stop_cmd: "powershell -ExecutionPolicy Bypass -File stop.ps1"
    category: manufacturing
    tags: [flask, python, mysql]
```

### チェックリスト
- [ ] `health_url` は **`http://127.0.0.1:ポート/...`** で登録されているか？
- [ ] `/health` はリダイレクトなし（HTTP 200）で返るか？（末尾スラッシュの有無で 308/301 になっていないか）
- [ ] レスポンス JSON に `"status": "ok"`、`"version": "..."`、`"access_total": <数値>` が含まれているか？
- [ ] DB 疎通チェックに 1.0 秒以内のタイムアウトとキャッシュが設定されているか？
- [ ] サーバー（Waitress 等）が IPv4/IPv6 デュアルスタック、または 127.0.0.1 で確実に稼働しているか？

---

## 6. app.log の設定・保存・ローテーション

### 6.1 参考にした実装と既定値

確認日: 2026-10-06。参考: [inspection_record_app.py](https://github.com/Araiseimitsu-DIP-Department/inspection_record/blob/afbf6533e83f477dbe542b8d6ef7bf0aaef2b41a/inspection_record_app.py) および同コミットの `inspection_record_app_psql.py`。

参照リポジトリでは、専用ロガーと `RotatingFileHandler` を使用して、アクセスログ・起動情報・警告を `app.log` に保存しています。

| 項目 | 参照実装の設定 |
| :--- | :--- |
| 保存先 | 環境変数 `APP_DATA_DIR`。未設定・空の場合はアプリのPythonファイルがあるディレクトリ |
| ファイル名 | `app.log` |
| 文字コード | UTF-8 |
| 出力レベル | INFO以上（INFO / WARNING / ERROR / CRITICAL） |
| 切り替えサイズ | `5 * 1024 * 1024` バイト（5 MiB） |
| 過去ログ | 5ファイル（`app.log.1` ～ `app.log.5`） |
| 書式 | `%(asctime)s [%(levelname)s] %(message)s` |
| 二重出力対策 | ハンドラーの重複登録を避け、`logger.propagate = False` にする |

最新の履歴は `app.log.1`、最も古い履歴は `app.log.5` です。切り替え時に最も古い履歴が削除されます。現行ログを含む保存量の目安は約30 MiBですが、サイズは厳密な容量制限ではありません。保存期間を日数で保証する設定ではありません。

第3章にはこの既定値の初期化を組み込みました。参照実装に加えて、保存先ディレクトリを `os.makedirs(..., exist_ok=True)` で作成します。サービス実行ユーザーに書き込み権限のあるローカルディレクトリを指定してください。

### 6.2 PowerShell で保存先を設定する

アプリを起動する `start.ps1` などで、Python起動前に設定します。

```powershell
$env:APP_DATA_DIR = 'C:\AraiApps\my_app\data'
New-Item -ItemType Directory -Path $env:APP_DATA_DIR -Force | Out-Null
# この後に既存のアプリ起動コマンドを実行する
```

この例では `C:\AraiApps\my_app\data\app.log` に保存されます。第3章のアクセスカウンターも同じフォルダーに保存します。`.env` を使う場合は、`load_dotenv()` をロガー初期化より前に呼び出してください。環境変数の変更はアプリを再起動して反映します。

### 6.3 レベル・サイズ・履歴数も環境変数で変更する場合

以下は**このガイドで追加する拡張例**です。参照リポジトリが対応している環境変数は `APP_DATA_DIR` であり、`APP_LOG_LEVEL` / `APP_LOG_MAX_BYTES` / `APP_LOG_BACKUP_COUNT` はこのコードを導入した場合に利用できます。

第3章の `BASE_DIR` から `logger.propagate = False` までを、以下に置き換えます。必要な `os` / `logging` / `RotatingFileHandler` は第3章でインポート済みです。

```python
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.getenv("APP_DATA_DIR") or BASE_DIR
os.makedirs(DATA_DIR, exist_ok=True)

level_name = os.getenv("APP_LOG_LEVEL", "INFO").strip().upper()
levels = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}
if level_name not in levels:
    raise ValueError("APP_LOG_LEVEL は DEBUG/INFO/WARNING/ERROR/CRITICAL を指定してください")

max_bytes = int(os.getenv("APP_LOG_MAX_BYTES", str(5 * 1024 * 1024)))
backup_count = int(os.getenv("APP_LOG_BACKUP_COUNT", "5"))
if max_bytes <= 0 or backup_count <= 0:
    raise ValueError("ログサイズと履歴数は正の整数を指定してください")

logger = logging.getLogger("aacm_app")  # アプリごとに一意の名前にする
logger.setLevel(levels[level_name])
if not logger.handlers:
    handler = RotatingFileHandler(
        os.path.join(DATA_DIR, "app.log"),
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(handler)
logger.propagate = False
```

```powershell
$env:APP_DATA_DIR = 'C:\AraiApps\my_app\data'
$env:APP_LOG_LEVEL = 'INFO'
$env:APP_LOG_MAX_BYTES = '5242880'
$env:APP_LOG_BACKUP_COUNT = '5'
```

通常のアクセスログを残す場合は `INFO` を使用します。`WARNING` 以上にすると、`logger.info` によるアクセスログ・起動情報は保存されません。値が不正な場合や保存先に書き込めない場合は起動時にエラーになるため、運用開始前に確認してください。

### 6.4 記録内容と除外対象

第3章の `after_request` は、接続元IP、HTTPメソッド、パス、HTTPステータスを記録します。

```text
2026-10-06 09:00:00,123 [INFO] 192.168.1.20 "GET /" 200
2026-10-06 09:01:00,456 [WARNING] access_counter.json 読込失敗: ...
```

- `/health`（末尾スラッシュやパス接頭辞付きも含む）、`/static/`、`/favicon.ico`、`/robots.txt` は通常のアクセスログと集計から除外します。
- DB疎通エラーは監視リクエストに起因しても `WARNING` として残します。
- `X-Forwarded-For` はリバースプロキシが適切に設定されている場合に利用します。外部から渡された値を無条件に信頼しないでください。
- パスだけを記録し、パスワード・トークン・リクエスト本文・クエリ文字列はこのアクセスログに追加しないでください。

専用ロガーに明示的に出したメッセージが保存対象です。Flask / Waitress / Uvicorn の全ログや未処理例外が自動でこのファイルに集約される設定ではありません。必要な例外は例外処理内で `logger.exception("処理に失敗しました")` などを使用します。

### 6.5 FastAPI に適用する場合

第6.3節の初期化はFastAPIでも使えます。`/health` の処理から参照する前にロガーを初期化し、通常アクセスの記録には次のミドルウェアを追加します。既存のアクセスログ処理がある場合はそちらへ統合し、二重記録を避けてください。

```python
from fastapi import Request

def is_monitoring_or_static(path: str) -> bool:
    if path.startswith("/static/") or path in ("/favicon.ico", "/robots.txt"):
        return True
    return path.rstrip("/").endswith("/health")

@app.middleware("http")
async def record_access_log(request: Request, call_next):
    response = await call_next(request)
    if not is_monitoring_or_static(request.url.path):
        remote = request.client.host if request.client else "-"
        logger.info('%s "%s %s" %s', remote, request.method,
                    request.url.path, response.status_code)
    return response
```

この例はレスポンスを返したリクエストを記録します。`call_next` が例外を送出した場合の記録は別途例外処理で対応します。Uvicornのアクセスログは独立しているため、この除外フィルターはUvicorn側のログには適用されません。ファイル出力は同期処理なので、高負荷環境では `QueueHandler` / `QueueListener` などによる非同期化を検討してください。

### 6.6 運用上の確認

- [ ] アプリ実行ユーザーで保存先に書き込めるか？
- [ ] 通常画面へのアクセスで `app.log` にINFOログが追加されるか？
- [ ] `/health` を繰り返し呼んでも通常アクセスログが増えないか？
- [ ] 検証用保存先でサイズを小さく設定し、履歴ファイルの生成と上限数を確認したか？
- [ ] 再起動・再読み込みでログが二重に出力されないか？

`RotatingFileHandler` は複数プロセスで同じファイルをローテーションする構成には対応しません。この例は単一プロセスで利用してください。Uvicornの複数ワーカーなどを使う場合は、プロセスごとのファイル、ログ集約サービス、または標準出力からの収集へ切り替えます。

テスト時はアプリをインポートする前に `APP_DATA_DIR` を一時ディレクトリへ変更し、運用中の `app.log` と `access_counter.json` を汚さないようにしてください。

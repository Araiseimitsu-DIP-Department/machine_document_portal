# 社内アプリ共通デザインガイド

## 目的

このドキュメントは、本アプリ（材料ミルシート管理）を含む社内アプリの標準デザインの基準を定義する。

対象は業務担当者が日常的に使用する社内アプリであり、装飾性よりも「検索しやすい」「入力しやすい」「一覧を確認しやすい」「操作に迷わない」ことを優先する。

レイアウト・情報密度・コンポーネント構成は現行UIを踏襲しつつ、配色とロゴは新井精密のコーポレートサイト（araiseimitsu.com）のイメージに合わせた薄い青を基調とする。

## 実装方針

- スタイルは **vanilla CSS**（CSSカスタムプロパティ）で実装する。CSSフレームワーク（Tailwind等）には依存しない。
- 配色・余白・角丸などはすべて `:root` のCSS変数（トークン）として定義し、各コンポーネントは変数を参照する。
- 左ペイン（サイドバー）はトグルで開閉でき、折りたたみ時はアイコンのみを表示する。
- アイコンは lucide 系のSVGパスをインラインで埋め込み、外部ライブラリに依存しない。

## デザイン原則

- 業務画面として、情報密度を保ちながら視認性を落とさない。
- 画面全体は静かで実務的な印象にし、過度な装飾や大きなビジュアル表現は使わない。
- 操作導線は左ナビゲーション、ページ見出し、条件カード、結果カードの順で統一する。
- 主要操作はアイコン付きボタンで明示し、補助操作は控えめなスタイルにする。
- 一覧・帳票・マスタ管理など、反復利用する業務に向いたレイアウトを基準にする。

## ブランドテーマ

配色は新井精密コーポレートサイトの基調色（明るい青 `#1e88e5`、濃い青 `#005cac`、本文グレー `#505050`）を基準とする。主色は明るい青、リンク・ホバー・濃い強調には濃い青を使い、背景は白〜ごく薄い青みグレーでまとめる。

### カラートークン

| 用途 | トークン | 値 | 使用方針 |
| --- | --- | --- | --- |
| 画面・カード背景 | `--color-surface` | `#ffffff` | カード、入力欄、サイドバー |
| アプリ背景 | `--color-surface-secondary` | `#f4f8fc` | メイン背景、ホバー背景（ごく薄い青みグレー） |
| 補助背景 | `--color-surface-tertiary` | `#e9f1f9` | 追加の区切りや弱い面 |
| 境界線 | `--color-border` | `#dce5ee` | カード、入力、表ヘッダー境界 |
| 弱い境界線 | `--color-border-subtle` | `#eef3f8` | 表の行境界 |
| 本文 | `--color-text` | `#2b2f36` | 見出し、主要テキスト |
| 補助テキスト | `--color-text-secondary` | `#646b75` | ラベル、非アクティブナビ |
| 弱いテキスト | `--color-text-tertiary` | `#9aa3ad` | プレースホルダー、補足 |
| 主色 | `--color-accent` | `#1e88e5` | 主要ボタン、リンク、アクティブ表示 |
| 主色ホバー | `--color-accent-hover` | `#005cac` | 主要ボタンのホバー、濃い強調 |
| 主色背景 | `--color-accent-soft` | `rgba(30, 136, 229, 0.10)` | 選択状態、未納などの弱い強調 |
| フォーカス | `--color-accent-ring` | `rgba(30, 136, 229, 0.25)` | 入力・ボタンのフォーカスリング |
| 成功 | `--color-success` | `#10b981` | 完了、成功状態 |
| 成功背景 | `--color-success-soft` | `rgba(16, 185, 129, 0.10)` | 完了バッジ背景 |
| 危険 | `--color-danger` | `#ef4444` | エラー、削除、必須マーク |
| 危険背景 | `--color-danger-soft` | `rgba(239, 68, 68, 0.10)` | エラーメッセージ背景 |
| 警告 | `--color-warning` | `#f59e0b` | 注意喚起 |

### 色の使い方

- 主色は明るい青 `#1e88e5` を基準とし、ボタン・リンク・選択状態・フォーカスに限定して使う。
- リンクの強調やボタンのホバーなど、より強い青が必要な場合は濃い青 `#005cac` を使う。
- 背景は白とごく薄い青みグレーを中心にし、画面全体を単色で塗りつぶさない。
- 成功・危険・警告色は状態表現のみに使い、通常の装飾には使わない。
- バッジや選択状態は濃色ベタ塗りではなく、薄い背景色と濃い文字色の組み合わせを基本にする。

## タイポグラフィ

### フォント

新井精密サイトと同系統の日本語ゴシックを優先する。

```css
--font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Hiragino Sans", "Yu Gothic Medium", "Yu Gothic", Meiryo, "Noto Sans JP", sans-serif;
--font-mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
```

### 文字サイズ

| 用途 | サイズ | 太さ | 備考 |
| --- | --- | --- | --- |
| ページタイトル | `text-2xl` | `font-semibold` | 画面上部の主見出し |
| 通常本文 | `text-sm` | `font-normal` | フォーム、表、説明文 |
| ラベル | `text-xs` | `font-medium` | 入力項目名、表ヘッダー |
| ボタン | `text-sm` | `font-medium` | アイコンと併用 |
| 補足・フッター | `text-xs` | `font-normal` | 弱い情報 |

### 表記ルール

- 日本語UIでは短く具体的なラベルを使う。
- ボタン文言は「検索」「登録」「Excel出力」のように動詞または操作名で統一する。
- 業務用語は既存業務の呼称を優先し、一般化しすぎない。
- 数値は右寄せし、必要に応じて `tabular-nums` を使う。

## レイアウト

### アプリ全体

- 画面は `h-screen` の固定アプリレイアウトを基本にする。
- 背景は `surface-secondary`、本文色は `text` を使う。
- 左にサイドバー、右にメインコンテンツを配置する。
- メイン領域は `overflow-auto` とし、画面内で業務一覧をスクロールできるようにする。
- メイン内側は `p-6`、最大幅は `max-w-7xl` を基準にする。

### サイドバー

- 幅は通常 `15rem`、折りたたみ時 `4rem`。開閉は `width` のトランジションで滑らかに切り替える。
- 背景は `surface`、右境界に `border-border` を使う。
- 上部ヘッダーにロゴ（または画面名）と折りたたみトグルボタンを配置する。
- 折りたたみトグルは常に表示し、`aria-label` / `title` で開閉状態を示す。
- 展開時はロゴ＋ナビラベルを表示し、折りたたみ時はラベルを隠してアイコンのみを中央寄せで表示する。
- ナビゲーションはアイコンとラベルを横並びにする。
- 現在ページは `accent-soft` 背景と `text`、アクティブアイコンは `accent` 色で示す。
- 非アクティブ項目は `text-secondary`、ホバー時は `surface-secondary` にする。

#### ロゴ

- サイドバーヘッダーには新井精密の「ARAI」ロゴ画像を配置する。
- ロゴ画像は `frontend/src/assets/`（または `public/`）に配置し、相対参照で読み込む。
- 展開時はロゴ画像を表示し、折りたたみ時はロゴを隠すか、頭文字アイコンに切り替える。
- ロゴの高さはヘッダー内に収まる範囲（目安 `1.5rem`〜`2rem`）とし、縦横比を保つ。
- ロゴ画像には `alt="新井精密"` を付ける。

### ページ構成

標準画面は以下の順序で構成する。

1. ページヘッダー
2. 条件・入力カード
3. 状態表示
4. 結果・詳細カード

検索画面では、条件カードの下に結果テーブルカードを置く。
登録画面では、入力カードを主役にし、送信ボタンは右下に配置する。

## コンポーネント基準

表記はCSSの実値で示す（クラス名は実装の `app.css` を正とする）。

### PageHeader

- ページタイトルは `font-size: 1.5rem; font-weight: 600; letter-spacing: -0.025em;`、色は `--color-text`。
- 補足説明がある場合のみ、タイトル下に `font-size: 0.875rem;`・`--color-text-secondary` で配置する。
- 見出し周辺には過度な説明文を置かない。

### Card

- 背景は `--color-surface`。
- 角丸は `--radius-xl`（`0.75rem`）を基本にする。
- 境界線は `1px solid var(--color-border)`。
- 影は `0 1px 2px rgba(0, 0, 0, 0.05)` に留める。
- 検索条件カードは `padding: 1.25rem; margin-bottom: 1.25rem;`。
- 登録フォームカードは `padding: 1.5rem;` を基準にする。
- 表カードは `overflow: hidden` とし、内側で横スクロールさせる。

### Button

共通仕様:

- `display: inline-flex; align-items: center; justify-content: center; gap: 0.5rem;`
- `padding: 0.5rem 1rem;`
- `border-radius: var(--radius-lg);`（`0.5rem`）
- `font-size: 0.875rem; font-weight: 500;`
- アイコンサイズは原則 `16px`
- フォーカス時はアクセントのリング（`--color-accent-ring`）を表示する

種類:

| 種類 | 用途 | スタイル |
| --- | --- | --- |
| primary | 登録、検索、集計などの主操作 | 青背景、白文字 |
| secondary | Excel出力、補助操作 | 白背景、境界線 |
| ghost | ナビ内操作、控えめな操作 | 透明背景 |
| danger | 削除、危険操作 | 赤背景 |
| success | 成功確定操作 | 緑背景 |

### Form

- ラベルは入力欄の上に置く。
- ラベル色は `--color-text-secondary`、サイズは `0.75rem`、太さは `500`。
- 入力欄は `font-size: 0.875rem;`、標準パディング `0.5rem 0.75rem`。
- 角丸は `var(--radius-lg)`（`0.5rem`）。
- フォーカス時は `--color-accent` の境界線とフォーカスリングを表示する。
- 読み取り専用項目は `--color-surface-secondary` 背景と `--color-text-secondary` で編集不可を示す。
- 必須項目はラベル横に `--color-danger` の `*` を付ける。

### Table

- 表は業務アプリの主表示として扱い、横スクロールを許容する。
- ヘッダーは `--color-surface-secondary` 背景、`--color-text-secondary`、`font-weight: 600`。
- セルは `0.75rem 1rem`、ヘッダーは `0.625rem 1rem`。
- 行境界は `--color-border-subtle`。
- 行ホバー時は `--color-surface-secondary` 背景にする。
- 日付・文字列は左寄せ、数値・金額は右寄せにする。
- 空状態は表内に「該当データがありません」を中央表示する。

### Badge

- 状態バッジは `display: inline-flex; align-items: center; padding: 0.125rem 0.5rem; border-radius: var(--radius-lg); font-size: 0.75rem; font-weight: 500;`。
- 完了状態は `--color-success-soft` 背景と `--color-success` 文字。
- 未完了・処理中などの通常状態は `--color-accent-soft` 背景と `--color-accent` 文字。
- 危険・エラー状態のみ `--color-danger-soft` 背景と `--color-danger` 文字を使う。

### Icon

- アイコンは `lucide` 系を基準にし、SVGパスをインラインで埋め込む。
- ナビゲーションアイコンは `18px`。
- ボタンアイコンは `16px`。
- アクティブなナビゲーションでは `stroke-width` を少し太くする。
- アイコンだけのボタンには必ず `aria-label` または `title` を付ける。

### Footer

- アプリ全体の最下部にフッターを配置し、著作権表記と作成元を控えめに示す。
- 文字色は `--color-text-tertiary`、サイズは `0.75rem`、配置は中央寄せにする。
- 上端に `1px solid var(--color-border-subtle)` の境界線を引き、本文領域と区切る。
- 背景は `--color-surface` または `--color-surface-secondary` とし、装飾は加えない。
- フッター文言は以下を標準とする。

```
© ARAISEIMITSU 2026 - Created By DIP Department
```

## UXルール

### 検索・一覧

- 検索条件は1枚のカードにまとめる。
- 条件項目は横並び（`display: flex; flex-wrap: wrap; align-items: flex-end; gap: 1rem;`）にし、狭い画面では折り返す。
- 実行ボタン群は `margin-left: auto` で右端に寄せる。
- 検索中はスピナーと「読み込み中…」を中央表示する。
- 結果がない場合は空状態を表内に表示する。

### 登録・編集

- 入力フォームは2カラムを基本にし、狭い画面では1カラムにする。
- 関連する入力項目は同じカード内にまとめる。
- 自動補完・読み取り専用の項目は、編集可能項目と視覚的に区別する。
- 登録などの確定操作は右下に配置する。
- 破壊的操作は通常画面に常時露出せず、確認を挟む。

### フィードバック

- ローディング、空状態、エラーは必ず画面上に表示する。
- エラーは `danger-soft` 背景と `danger` 文字で表示する。
- 成功・完了は緑、未完了・通常状態は青で表す。
- `alert` だけに依存せず、可能な限り画面内にも状態を残す。

### アクセシビリティ

- フォーカス可能な操作要素には視認できるフォーカスリングを付ける。
- アイコンのみのボタンにはラベルを付ける。
- 色だけで状態を伝えず、状態テキストも併記する。
- テーブルはヘッダーと値の対応が分かる構造にする。

## 実装ルール

### 推奨スタック

- Svelte
- vanilla CSS（CSSカスタムプロパティ。CSSフレームワークには依存しない）
- lucide 系アイコン（SVGパスをインライン埋め込み）
- 共通コンポーネント: `PageHeader`、`Card`、`Button`

### CSSトークン

テーマは `:root` のCSSカスタムプロパティとして定義し、全コンポーネントは変数を参照する。色をハードコードしない。

```css
:root {
  --color-surface: #ffffff;
  --color-surface-secondary: #f4f8fc;
  --color-surface-tertiary: #e9f1f9;
  --color-border: #dce5ee;
  --color-border-subtle: #eef3f8;
  --color-text: #2b2f36;
  --color-text-secondary: #646b75;
  --color-text-tertiary: #9aa3ad;
  --color-accent: #1e88e5;
  --color-accent-hover: #005cac;
  --color-accent-soft: rgba(30, 136, 229, 0.10);
  --color-accent-ring: rgba(30, 136, 229, 0.25);
  --color-success: #10b981;
  --color-success-soft: rgba(16, 185, 129, 0.10);
  --color-danger: #ef4444;
  --color-danger-soft: rgba(239, 68, 68, 0.10);
  --color-warning: #f59e0b;

  --radius-lg: 0.5rem;
  --radius-xl: 0.75rem;
  --sidebar-width: 15rem;
  --sidebar-collapsed-width: 4rem;
}
```

### 禁止事項

- 業務アプリの通常画面で、ヒーローセクションやマーケティング風の大きな装飾を使わない。
- 背景に強いグラデーション、装飾的な図形、意味のないビジュアルを置かない。
- カードを入れ子にして画面を複雑にしない。
- ボタンやラベルの文言をページごとにばらつかせない。
- 表の数値を左寄せにしない。
- 状態色を通常装飾として使わない。

## 標準画面パターン

クラス名は実装の `app.css` を正とする（`.page`, `.card`, `.card-filter`, `.card-table`, `.filter-row`, `.filter-actions`, `.table-scroll`, `.card-form`, `.form-grid`, `.form-actions`, `.btn` 系）。

### 検索一覧画面

```svelte
<div class="page">
  <header class="page-header">
    <h1 class="page-title">購入実績照会</h1>
  </header>

  <div class="card card-filter">
    <div class="filter-row">
      <!-- 検索条件 -->
      <div class="filter-actions">
        <button class="btn btn-primary">検索</button>
        <button class="btn btn-secondary">Excel出力</button>
      </div>
    </div>
  </div>

  <div class="card card-table">
    <div class="table-scroll">
      <table>
        <!-- 一覧 -->
      </table>
    </div>
  </div>
</div>
```

### 登録画面

```svelte
<div class="page">
  <header class="page-header">
    <h1 class="page-title">新規登録</h1>
  </header>

  <div class="card card-form">
    <div class="form-grid">
      <!-- 入力項目（2カラム、狭い画面で1カラム） -->
    </div>

    <div class="form-actions">
      <button class="btn btn-primary">登録</button>
    </div>
  </div>
</div>
```

## 判断基準

新規アプリや新規画面を作るときは、次の条件を満たすことを合格基準にする。

- 左サイドバー、ページヘッダー、カード、表、フォームの見た目が本ガイドと一致している。
- 主操作と補助操作の視覚的な強弱が明確である。
- 業務一覧は横スクロールを含めて破綻せず確認できる。
- 入力項目の必須・読み取り専用・エラー状態が見分けられる。
- 画面上の余白、角丸、境界線、色が過度に強くない。
- 反復利用する社内業務に向いた落ち着いた密度になっている。

# SharePoint 工程内検査シート連携

工程内検査シートは、SharePointの指定フォルダとその配下の全サブフォルダを再帰検索し、読み取り専用で取得します。サブフォルダが複数階層ある場合も対象となり、Microsoft Graphのページングを最後まで取得します。Googleスプレッドシート「生産中」のH列（品番）と、SharePointファイル名の拡張子を除いた文字列を正規化せず照合します。

例えば、H列が `AB-100` の場合は、`AB-100.xlsx`、`AB-100-1.xlsx`、`AB-100-2.xlsm`を対象にします。`AB-100-01.xlsx`、`AB-100-0.xlsx`、`AB-100-A.xlsx`、`ab-100.xlsx`、`ＡＢ－１００.xlsx`、`AB 100.xlsx`は対象外です。

品番自体が`MAM8140X-1`のように数字付きハイフンで終わる場合、`MAM8140X-1.xlsx`を完全一致、`MAM8140X-1-1.xlsx`を関連ファイルとして扱い、`MAM8140X.xlsx`には戻しません。稼働中の別品番へ完全一致するファイルは、連番関連付けより完全一致を優先します。

候補が1件の場合は元のSharePointファイルを直接別タブで開きます。複数の場合は号機カードに件数を表示し、別タブの選択画面へ完全一致、`-1`、`-2`、`-10`の順で全ファイルを表示します。同名ファイルが別フォルダにある場合も保存場所を併記してすべて表示します。

## 必要なEntra ID設定

Microsoft Entra IDでアプリ登録を作成し、以下を `.env` に設定します。クライアントシークレットはGitに追加しません。

```dotenv
MICROSOFT_TENANT_ID=
MICROSOFT_CLIENT_ID=
MICROSOFT_CLIENT_SECRET=
SHAREPOINT_DRIVE_ID=
SHAREPOINT_FOLDER_ID=
SHAREPOINT_PROCESS_INSPECTION_URL=
SHAREPOINT_SHIPPING_INSPECTION_URL=
```

アプリにはMicrosoft Graphのアプリケーション権限 `Sites.Selected` を設定し、対象SharePointサイトだけに `Read` 権限を付与します。`Files.ReadWrite.All` や全サイト対象の権限は必要ありません。

## Drive ID / Folder ID の取得

SharePoint管理者に、対象のドキュメントライブラリの `driveId` と、検査シート保存フォルダの `folderId` を依頼します。対象フォルダのみに限定せず、対象サイトに対してアプリの `Read` 権限を付与してください。

設定後、アプリはGoogle Sheetsの同期時にフォルダ一覧を一度だけ取得し、品番を照合します。ファイルの追加・更新・削除は次回の同期で反映されます。

## 確認

設定値を反映するためアプリを再起動します。起動時と「最新情報に更新」では完全同期します。`AUTO_REFRESH_SECONDS` 間隔では品番が新規・変更された号機だけを検索し、`DOCUMENT_REFRESH_TIMES` の指定時刻には全号機のSharePoint・NAS資料だけを完全更新します。検査シートのアイコンが有効になれば、別タブで元ファイルを開けます。

認証または権限設定に失敗した場合、アイコンはエラー状態となり、Google SheetsとNAS図面の表示は継続します。

## サイドバーの共通リンク

次の設定値を指定すると、サイドバーの「外部リンク」グループに共通リンクを表示します。各リンクは新しいタブで開きます。

- `SHAREPOINT_PROCESS_INSPECTION_URL`: 工程内検査シート
- `SHAREPOINT_SHIPPING_INSPECTION_URL`: 出荷検査表
- `NOTION_MEASUREMENT_EQUIPMENT_INSPECTION_URL`: Notionの測定機器点検表

これらは品番別のMicrosoft Graph検索とは独立した共通リンクです。サイドバーを折りたたんだ場合も外部リンク記号を表示します。

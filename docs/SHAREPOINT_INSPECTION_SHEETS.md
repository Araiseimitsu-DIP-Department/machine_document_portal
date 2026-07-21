# SharePoint 工程内検査シート連携

工程内検査シートは、SharePointの指定フォルダから読み取り専用で取得します。Googleスプレッドシート「生産中」のH列（品番）と、SharePointファイル名の**拡張子を除いた完全一致**で対応付けます。

例えば、H列が `AB-100` のときは `AB-100.xlsx` を表示します。`AB-100-1.xlsx` は一致として扱いません。該当ファイルのボタンを押すと、元のSharePointファイルを新しいタブで開きます。

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

設定値を反映するためアプリを再起動し、「最新情報に更新」を押します。検査シートのアイコンが有効になれば、別タブで元ファイルを開けます。

認証または権限設定に失敗した場合、アイコンはエラー状態となり、Google SheetsとNAS図面の表示は継続します。

## サイドバーの共通リンク

次の設定値を指定すると、サイドバーの「外部リンク」グループに共通リンクを表示します。各リンクは新しいタブで開きます。

- `SHAREPOINT_PROCESS_INSPECTION_URL`: 工程内検査シート
- `SHAREPOINT_SHIPPING_INSPECTION_URL`: 出荷検査表
- `NOTION_MEASUREMENT_EQUIPMENT_INSPECTION_URL`: Notionの測定機器点検表

これらは品番別のMicrosoft Graph検索とは独立した共通リンクです。サイドバーを折りたたんだ場合も外部リンク記号を表示します。

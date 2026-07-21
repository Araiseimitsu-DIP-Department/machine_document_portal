# Google Sheets production setup

The application reads the `生産中` sheet using a Google Cloud service account. It does not require PostgreSQL. The dashboard displays only the non-empty machine IDs in column D; adding a machine ID to the sheet makes it appear after the next refresh, and removing it makes it disappear.

The latest sheet data is held only in the application process. A restart automatically fetches the sheet again; if Google Sheets is unavailable at startup, the dashboard remains empty until a later successful refresh. Synchronization history is not retained after restart.

## Spreadsheet layout

| Column | Meaning |
| --- | --- |
| A | Production status |
| D | Machine ID |
| H | Part number |
| I | Product name |

Use machine IDs in the `group-number` form (for example, `A-1`) for the expected group and numeric sort order. New groups are supported. Duplicate machine IDs stop the sync.

## Google Cloud

1. Create a dedicated service account for this application in the production Google Cloud project.
2. Enable the Google Sheets API for that project.
3. Create a JSON key for the service account and place it on the application host as `secrets/google-service-account.json`.
4. Share the target spreadsheet with the service account's `client_email` as **Viewer**.

Never commit the key file. The `secrets/` directory is ignored by Git.

## NAS drawings

Set `NAS_DRAWING_DIRECTORY` to the directory containing drawing PDFs. The application looks for an exact filename match with the part number in column H, adding `.pdf` when the part number has no extension. When the user selects the drawing button, the application opens a dedicated browser tab and renders the first page as a JPEG preview; the PDF and NAS path are not exposed to the browser. Generated previews are cached while the application runs.

The separate-tab first-page preview is the current display mode. Split-screen display with the inspection sheet and multi-page navigation can be introduced later without changing the NAS lookup rule.

The account that starts the application must have read permission for the NAS directory.

For the SharePoint inspection-sheet setup, see [SHAREPOINT_INSPECTION_SHEETS.md](SHAREPOINT_INSPECTION_SHEETS.md).

## Production environment file

Create the ignored `.env` file on the application host. Substitute the key path and spreadsheet ID. The spreadsheet ID is the portion between `/d/` and `/edit` in its URL.

```dotenv
APP_ENV=production
DEBUG=false
USE_SAMPLE_DATA=false
PERSISTENCE_MODE=memory

GOOGLE_CREDENTIALS_PATH=secrets/google-service-account.json
GOOGLE_SPREADSHEET_ID=replace-with-spreadsheet-id
GOOGLE_SPREADSHEET_SHEET_NAME=生産中
GOOGLE_SPREADSHEET_START_ROW=2
GOOGLE_SPREADSHEET_STATUS_COLUMN=A
GOOGLE_SPREADSHEET_MACHINE_COLUMN=D
GOOGLE_SPREADSHEET_PART_NUMBER_COLUMN=H
GOOGLE_SPREADSHEET_PRODUCT_NAME_COLUMN=I
NAS_DRAWING_DIRECTORY=\\server\share\drawings
AUTO_REFRESH_SECONDS=300
DOCUMENT_REFRESH_TIMES=10:30,14:30
```

## Deploy and verify

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Start the application. It performs a complete Google Sheets, SharePoint, and NAS refresh on startup, and the refresh button (or `POST /api/refresh`) performs the same refresh again. At the interval set by `AUTO_REFRESH_SECONDS`, the application reads Google Sheets and rechecks SharePoint/NAS only for machines whose part number is new or changed. `DOCUMENT_REFRESH_TIMES` performs a complete SharePoint/NAS-only refresh at comma-separated Japan-time values such as `10:30,14:30`; leave it blank to disable this schedule. Restart the application after editing `.env` so the new values are loaded. The service account has read-only access and the application never writes to the spreadsheet.

When `SCHEDULED_OPERATIONS_ENABLED=true`, the same spreadsheet is also inspected at 13:00 for the next available `〇〇S` sheet. The application reads `B40:K40`, sends missing SharePoint/NAS documents to ARAICHAT, and re-reads the same sheet at 15:00 before printing available NAS PDFs. Keep this setting `false` until ARAICHAT and printer configuration has been verified.

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

Set `NAS_DRAWING_DIRECTORY` to the directory containing drawing PDFs. The application looks for an exact filename match with the part number in column H, adding `.pdf` when the part number has no extension. When the user selects the drawing button, the application opens a dedicated browser tab and renders the first page in the browser with the locally bundled PDF.js 5.7.284. The NAS path is never exposed. The authenticated application endpoint returns only the current machine's PDF with private one-hour browser caching, validators, and byte-range support.

PDF.js is the primary display and the application does not show a JPEG first. The existing JPEG preview is requested only if PDF loading or rendering fails; fallback previews remain cached in the application process. The separate-tab first-page view is the current display mode. Split-screen display with the inspection sheet and multi-page navigation can be introduced later without changing the NAS lookup rule.

The PDF.js module, worker, CMaps, standard fonts, and WASM decoders are served locally without a CDN. Current Chrome/Edge use the modern build; Safari and Apple mobile devices use the matching legacy build. Before production rollout, verify representative large drawings on the actual Windows PC, iPhone, iPad, and Android tablet over the production Wi-Fi. Safari 16.4 or later and a current Android Chrome are recommended.

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
DASHBOARD_REVISION_POLL_SECONDS=300
DOCUMENT_REFRESH_TIMES=13:10
```

## Deploy and verify

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Start the application. It performs a complete Google Sheets, SharePoint, and NAS refresh on startup, and the refresh button (or `POST /api/refresh`) performs the same refresh again. At the interval set by `AUTO_REFRESH_SECONDS`, the application reads Google Sheets and rechecks SharePoint/NAS only for machines whose part number is new or changed. `DOCUMENT_REFRESH_TIMES` re-reads the configured Google Sheets production sheet and then completely refreshes SharePoint/NAS for every current machine at Japan-time values such as `13:10`; comma-separated multiple times such as `10:30,14:30` are also supported, and a blank value disables this schedule. After either scheduled synchronization completes successfully, each open browser detects the new dashboard revision within `DASHBOARD_REVISION_POLL_SECONDS` (300 seconds by default) or when the tab becomes visible, then reloads the page. Set it to `0` to disable automatic revision checks. A reload is deferred while a user refresh or print action is in progress. Restart the application after editing `.env` so the new values are loaded. The service account has read-only access and the application never writes to the spreadsheet.

When `SCHEDULED_OPERATIONS_ENABLED=true`, the same spreadsheet is inspected at 13:00 for the next available `〇〇S` sheet. The application reads the column dates from `B36:K36` together with the part numbers from `B40:K40`. A part-number column is skipped when its date is earlier than the target date; columns dated on or after the target date continue. The application sends the 13:00 ARAICHAT message under `【翌営業日セット予定分の検査シート・加工図面確認通知】` only when SharePoint inspection sheets or NAS drawings are missing. At 14:30 it re-reads both ranges from the same sheet, applies the same date filter, rechecks both locations, and sends only the items that are still missing under `【翌営業日セット予定分の再確認（14:30）】`. At 15:00 it re-reads both ranges, applies the same filter, and prints the NAS PDFs available at that time. A drawing unavailable at the 15:00 cutoff is recorded for manual printing and is not searched or printed automatically later. Only printer-submission failures for PDFs found at 15:00 are retried after 3, 5, and 10 minutes when `PRINT_RETRY_DELAYS_SECONDS=180,300,600`. Keep scheduled operations disabled until ARAICHAT, NAS, and printer access have been verified on the production server. At cutover, stop the legacy print script or scheduled task first, enable scheduled operations before 13:00, and restart the NSSM service. Starting after 13:00 can run the initial notification, starting after 14:30 can also run the recheck, and starting after 15:00 can then run the print operation, so the legacy process and this application must not run in parallel.

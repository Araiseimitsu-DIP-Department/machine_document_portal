"""`.env` の APP_PORT を読み取って Uvicorn を起動する。"""

import uvicorn

from app.config import get_settings
from app.main import app


def main() -> None:
    settings = get_settings()
    uvicorn.run(app, host="0.0.0.0", port=settings.app_port, access_log=False)


if __name__ == "__main__":
    main()

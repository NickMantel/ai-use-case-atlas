"""Entry point for containers and Databricks Apps.

Binds to $DATABRICKS_APP_PORT (Databricks Apps), $PORT (Cloud Run, Azure Container
Apps, most PaaS) or 8000.
"""
import os

import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("DATABRICKS_APP_PORT") or os.environ.get("PORT") or 8000)
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, proxy_headers=True, forwarded_allow_ips="*")

import uvicorn
from .config import settings

if __name__ == "__main__":
    uvicorn.run("app.web:app", host=settings.web_host, port=settings.web_port, log_level="info")

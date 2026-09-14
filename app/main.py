from contextlib import asynccontextmanager
import logging
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api.routes import router as api_router
from app.core.config import settings
from app.db.session import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("phone_intel")


from app.engine.geographic_matcher import police_scraper
import asyncio

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing database...")
    await init_db()
    logger.info("Database initialized successfully.")

    # Launch background police directory discovery without blocking startup
    async def _discovery_loop():
        try:
            await asyncio.sleep(8)  # Gentle warm-up delay
            await police_scraper.run_discovery_cycle()
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.warning("Background discovery task error: %s", exc)

    discovery_task = asyncio.create_task(_discovery_loop())

    yield

    discovery_task.cancel()
    logger.info("Shutting down application...")


app = FastAPI(
    title="Phone Number Intelligence Aggregator",
    description="Production-grade telecom intelligence engine for Portuguese (+351) and International phone numbers. Integrates ANACOM PNN prefix allocation, libphonenumber, multi-source asynchronous reputation scraping, and commercial entity verification.",
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static and template directories
static_dir = Path(__file__).resolve().parent / "static"
template_dir = Path(__file__).resolve().parent / "templates"

static_dir.mkdir(parents=True, exist_ok=True)
template_dir.mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
templates = Jinja2Templates(directory=str(template_dir))

# Include API Router
app.include_router(api_router, prefix="/api/v1", tags=["Intelligence API"])


@app.get("/", summary="Dashboard UI")
async def render_dashboard(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "app_name": settings.APP_NAME,
            "version": settings.APP_VERSION,
        },
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=True)

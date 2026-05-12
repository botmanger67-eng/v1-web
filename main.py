import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app.database import engine, Base
from app.routers import auth, products, cart, orders, admin, users

# ----------------------------------------------------------------------
# Lifespan context manager for startup/shutdown events
# ----------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create database tables (if using SQLite/PostgreSQL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    # Shutdown: dispose engine
    await engine.dispose()

# ----------------------------------------------------------------------
# FastAPI application instance
# ----------------------------------------------------------------------
app = FastAPI(
    title="E-Commerce Platform",
    description="A complete e-commerce platform built with FastAPI",
    version="1.0.0",
    lifespan=lifespan,
)

# ----------------------------------------------------------------------
# CORS middleware – allow frontend origin (adjust in production)
# ----------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        os.getenv("FRONTEND_URL", "http://localhost:8000"),
        # In production, restrict to your actual frontend domain
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------------------------------------------------------------
# Session middleware – stores session data in encrypted cookies
# ----------------------------------------------------------------------
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET_KEY", "change-this-secret-key-in-production"),
    session_cookie="ecommerce_session",
    max_age=3600 * 24 * 7,  # 1 week
)

# ----------------------------------------------------------------------
# Static files (CSS, JS, images, etc.)
# ----------------------------------------------------------------------
app.mount(
    "/static",
    StaticFiles(directory=os.path.join(os.path.dirname(__file__), "app", "static")),
    name="static",
)

# ----------------------------------------------------------------------
# Jinja2 templates
# ----------------------------------------------------------------------
templates = Jinja2Templates(
    directory=os.path.join(os.path.dirname(__file__), "app", "templates")
)

# Inject templates into app state so routers can use it
app.state.templates = templates

# ----------------------------------------------------------------------
# Include routers
# ----------------------------------------------------------------------
app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(products.router, prefix="/products", tags=["Products"])
app.include_router(cart.router, prefix="/cart", tags=["Cart"])
app.include_router(orders.router, prefix="/orders", tags=["Orders"])
app.include_router(admin.router, prefix="/admin", tags=["Admin"])
app.include_router(users.router, prefix="/users", tags=["Users"])

# Optional: root redirect or health check
@app.get("/health")
async def health_check():
    return {"status": "ok"}
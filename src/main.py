from fastapi import FastAPI
from contextlib import asynccontextmanager

from .core import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup operations
    init_db()
    yield
    # Shutdown operations (if any)


app = FastAPI(
    title="Better-Start",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/")
def get_root():
    """Health Route"""
    return {"Message": "Welcome To BetterStart"}

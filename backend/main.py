import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from db import init_db

DB_PATH = os.getenv("DB_PATH", "mgc.db")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db(DB_PATH)
    yield


app = FastAPI(title="MGC PoC API", version="0.1.0", lifespan=lifespan)

frontend_origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[frontend_origin, "http://localhost:5173"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok", "service": "mgc-backend", "version": "0.1.0"}


@app.get("/")
def root():
    return {"message": "MGC PoC API. See /health and /docs."}

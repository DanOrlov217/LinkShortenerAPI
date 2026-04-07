import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI
from links.router import router as links_router
from auth.users import fastapi_users, auth_backend
from auth.schemas import UserRead, UserCreate
from cache import init_cache, close_cache


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_cache()
    yield
    await close_cache()


app = FastAPI(title="URL Shortener", lifespan=lifespan)


app.include_router(
    fastapi_users.get_auth_router(auth_backend),
    prefix="/auth/jwt",
    tags=["auth"],
)

app.include_router(
    fastapi_users.get_register_router(UserRead, UserCreate),
    prefix="/auth",
    tags=["auth"],
)

app.include_router(links_router)


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

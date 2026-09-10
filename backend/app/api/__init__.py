from fastapi import APIRouter

from app.api import accounts, emails, notifications, settings, system

api_router = APIRouter()
api_router.include_router(system.router)
api_router.include_router(settings.router)
api_router.include_router(accounts.router)
api_router.include_router(emails.router)
api_router.include_router(notifications.router)

from fastapi import APIRouter

from app.api import accounts, ai, drafts, emails, notifications, sender_lists, settings, system
from app.api import digest

api_router = APIRouter()
api_router.include_router(system.router)
api_router.include_router(settings.router)
api_router.include_router(accounts.router)
api_router.include_router(emails.router)
api_router.include_router(notifications.router)
api_router.include_router(drafts.router)
api_router.include_router(ai.router)
api_router.include_router(sender_lists.router)
api_router.include_router(digest.router)

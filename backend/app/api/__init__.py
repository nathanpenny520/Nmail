from fastapi import APIRouter

from app.api import accounts, ai, chats, contacts, emails, ext, extkeys, folders, jobs, notifications, oauth, profiles, sender_lists, settings, system
from app.api import compose_extras, digest, meta, user_drafts

api_router = APIRouter()
api_router.include_router(system.router)
api_router.include_router(settings.router)
api_router.include_router(meta.router)
api_router.include_router(jobs.router)
api_router.include_router(accounts.router)
api_router.include_router(folders.router)
api_router.include_router(oauth.router)
api_router.include_router(oauth.callback_router)
api_router.include_router(emails.router)
api_router.include_router(notifications.router)
api_router.include_router(user_drafts.router)
api_router.include_router(compose_extras.router)
api_router.include_router(ai.router)
api_router.include_router(chats.router)
api_router.include_router(profiles.router)
api_router.include_router(sender_lists.router)
api_router.include_router(contacts.router)
api_router.include_router(digest.router)
api_router.include_router(ext.router)
api_router.include_router(extkeys.router)

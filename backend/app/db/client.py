"""Supabase client singleton."""

from supabase import Client, ClientOptions, create_client

from app.config import settings

_client: Client | None = None


def get_supabase() -> Client:
    global _client
    if _client is None:
        url = settings.supabase_url or "https://placeholder.supabase.co"
        key = settings.supabase_key or "placeholder"
        options = ClientOptions(
            postgrest_client_timeout=10,
            storage_client_timeout=10,
        )
        _client = create_client(url, key, options=options)
    return _client

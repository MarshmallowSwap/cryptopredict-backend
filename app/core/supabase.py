from functools import lru_cache
from app.core.config import settings
from app.core.readonly_db import ReadOnlySupabase


@lru_cache(maxsize=1)
def get_supabase():
    # Lazy construction: health checks and rejected requests need no DB client.
    from supabase import create_client
    return ReadOnlySupabase(create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY))

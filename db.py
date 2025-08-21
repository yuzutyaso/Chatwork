import os
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

SUPABASE_URL: str = os.getenv("SUPABASE_URL")
SUPABASE_KEY: str = os.getenv("SUPABASE_KEY")

# Supabaseクライアントをグローバルに定義
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

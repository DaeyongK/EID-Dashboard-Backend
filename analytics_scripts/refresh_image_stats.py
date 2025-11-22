import os
import asyncio

from supabase import create_client, Client
from dotenv import load_dotenv

from analytics_scripts.run_model_prediction import run_model_prediction_on_images
from analytics_scripts.calculate_image_confusion import (
    calculate_image_confusion,
    update_model_confusion,
)


async def refresh_image_stats(supabase: Client, SIGNED_URL_TTL="", run_all: bool = False, predict_null_only = True):
    supabase.rpc("refresh_image_stats", {}).execute()
    if not run_all:
        return

    await run_model_prediction_on_images(supabase, SIGNED_URL_TTL, null_only=predict_null_only)
    calculate_image_confusion(supabase)
    update_model_confusion(supabase)

if __name__ == "__main__":
    load_dotenv()

    url: str = os.environ.get("SUPABASE_URL")
    key: str = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    supabase: Client = create_client(url, key)
    SIGNED_URL_TTL = int(os.getenv("SIGNED_URL_TTL", "3600"))

    asyncio.run(
        refresh_image_stats(supabase, SIGNED_URL_TTL, run_all=True)
    )
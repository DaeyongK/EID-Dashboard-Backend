import os
from supabase import create_client, Client
from dotenv import load_dotenv


def calculate_image_confusion(supabase: Client):
    supabase.rpc("calculate_confusion", {}).execute()


def update_model_confusion(supabase: Client):
    supabase.rpc("update_model_confusion", {}).execute()


if __name__ == "__main__":
    load_dotenv()

    url: str = os.environ.get("SUPABASE_URL")
    key: str = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    supabase: Client = create_client(url, key)

    calculate_image_confusion(supabase)
    update_model_confusion(supabase)

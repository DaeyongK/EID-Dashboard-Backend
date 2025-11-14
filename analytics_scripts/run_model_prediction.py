import os
import asyncio
import datetime
from supabase import create_client, Client
from dotenv import load_dotenv

from utils import supabase_utils, inference


async def run_model_prediction_on_images(
    supabase: Client, SIGNED_URL_TTL, null_only: bool = True, batch_size: int = 100
):
    inference.download_model()
    model = inference.load_model()
    offset = 0
    i = 1
    while True:
        print(f"Running batch {i}")
        print("Fetching rows with NULL model prediction")
        if null_only:
            resp = (
                supabase.table("image_stats")
                .select("image_id, model_prediction, images(storage_path)")
                .is_("model_prediction", None)
                .range(offset, offset + batch_size - 1)
                .execute()
            )
        else:
            resp = (
                supabase.table("image_stats")
                .select("image_id, model_prediction, images(storage_path)")
                .range(offset, offset + batch_size - 1)
                .execute()
            )
        image_ids = resp.data or []
        if not image_ids:
            print("No images found with NULL model predictions")
            break

        for row in image_ids:
            image_id = row["image_id"]
            storage_path = row["images"]["storage_path"]
            img_url = supabase_utils._signed_url_for_storage_path(
                storage_path, supabase, SIGNED_URL_TTL
            )
            pred_class = await asyncio.to_thread(
                inference.make_inference, model, img_url
            )
            update_resp = (
                supabase.table("image_stats")
                .update({"model_prediction": pred_class})
                .eq("image_id", image_id)
                .execute()
            )
            if update_resp.data:
                print(f"Updated image {image_id} with prediction: {pred_class}")
            else:
                print(f"Failed to update image {image_id}")

            update_resp = (
                supabase.table("image_stats")
                .update({"computed_at": datetime.datetime.now().isoformat()})
                .eq("image_id", image_id)
                .execute()
            )

        offset += batch_size
        i += 1


if __name__ == "__main__":
    load_dotenv()

    url: str = os.environ.get("SUPABASE_URL")
    key: str = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    supabase: Client = create_client(url, key)
    SIGNED_URL_TTL = int(os.getenv("SIGNED_URL_TTL", "3600"))

    asyncio.run(
        run_model_prediction_on_images(supabase, SIGNED_URL_TTL, null_only=False)
    )

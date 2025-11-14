# supabase_utils.py
from datetime import datetime
import uuid
from fastapi import HTTPException, UploadFile
from supabase import Client
from typing import Optional
from .util_types.supabase_types import ImagesRow, CommentsRow
from pydantic import BaseModel
import numpy as np


class CommentCreate(BaseModel):
    damage_sev: int
    body: str


def _ext_from_content_type(ct: str) -> str:
    """
    idk why this is important but it fixed an issue i had ty chatgpt
    """
    mapping = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/webp": ".webp",
        "image/gif": ".gif",
    }
    return mapping.get((ct or "").lower(), "")


def upload_image_helper(
    supabase: Client, file: UploadFile, content: bytes
) -> ImagesRow:
    bucket = "images"

    ext = _ext_from_content_type(file.content_type)
    if not ext and file.filename and "." in file.filename:
        ext = "." + file.filename.rsplit(".", 1)[1].lower()
    key = f"{datetime.utcnow():%Y/%m}/{uuid.uuid4()}{ext}"

    # Try uploading image to images bucket
    try:
        supabase.storage.from_(bucket).upload(
            key,
            content,
            {
                "contentType": file.content_type or "application/octet-stream",
                "upsert": False,
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {e}")

    # Try inserting row into images table
    try:
        resp = supabase.table("images").insert({"storage_path": key}).execute()
        if resp.data and len(resp.data) > 0:
            row = resp.data[0]
        else:
            fetched = (
                supabase.table("images")
                .select("*")
                .eq("storage_path", key)
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
            if not fetched.data:
                raise RuntimeError(
                    "Insert succeeded but follow-up select returned no rows"
                )
            row = fetched.data[0]
    except Exception as e:
        # try remove failed insert
        try:
            supabase.storage.from_(bucket).remove([key])
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Images Table Insert Failed: {e}")


def _signed_url_for_storage_path(
    storage_path: str, supabase: Client, SIGNED_URL_TTL
) -> Optional[str]:
    """
    Creates url for frontend to load from the images bucket
    """
    bucket = "images"
    key = storage_path
    try:
        signed = supabase.storage.from_(bucket).create_signed_url(key, SIGNED_URL_TTL)
        return signed.get("signedURL")
    except Exception as e:
        return None


def get_images(supabase: Client, start: int, end: int, SIGNED_URL_TTL):
    """
    Gets the images for gallery and singular image (inclusive)
    """
    res = (
        supabase.table("images")
        .select("*")
        .gte("ordinal", start)
        .lte("ordinal", end)
        .order("ordinal", desc=False)
        .execute()
    )

    rows = res.data or []
    out: list[ImagesRow] = []
    for r in rows:
        out.append(
            ImagesRow(
                id=r["id"],
                storage_path=r["storage_path"],
                created_at=r.get("created_at"),
                ordinal=r["ordinal"],
                url=_signed_url_for_storage_path(
                    r["storage_path"], supabase, SIGNED_URL_TTL
                ),
            )
        )

    return out


def get_images_labeled(
    supabase: Client, start: int, end: int, user_email, SIGNED_URL_TTL
):
    """
    Gets the labeled images for user_email and limits to range in (start, end), ordered by most recent
    """
    res = (
        supabase.table("comments")
        .select(
            "*, images(storage_path, ordinal)"
        )  # join tables, only keep storage_path and ordinal from images table
        .eq("email_id", user_email)
        .order("created_at", desc=True)
        .range(start - 1, end - 1)
        .execute()
    )

    rows = res.data or []
    out: list[ImagesRow] = []
    for r in rows:
        out.append(
            ImagesRow(
                id=r["image_id"],
                storage_path=r["images"]["storage_path"],  # from nested entry
                created_at=r["created_at"],  # technically labeled at
                ordinal=r["images"]["ordinal"],  # from nested entry
                url=_signed_url_for_storage_path(
                    r["images"]["storage_path"], supabase, SIGNED_URL_TTL
                ),
            )
        )

    return out


def get_damage_aggregates_for_images(
    supabase: Client, start: int, end: int, SIGNED_URL_TTL: int
) -> list[ImagesRow]:
    """
    Fetches images in the given range and aggregates comment damage severities (0–3) for each image.
    Returns list of ImagesRow objects with damage_counts dict.
    """
    images = get_images(supabase, start, end, SIGNED_URL_TTL)
    if not images:
        return []
    image_ids = [img.id for img in images]
    res = (
        supabase.table("comments")
        .select("image_id, damage_sev")
        .in_("image_id", image_ids)
        .execute()
    )
    comment_rows = res.data or []
    damage_map: dict[str, dict[int, int]] = {}
    for c in comment_rows:
        img_id = c["image_id"]
        sev = c.get("damage_sev")
        if img_id not in damage_map:
            damage_map[img_id] = {0: 0, 1: 0, 2: 0, 3: 0}
        if sev in damage_map[img_id]:
            damage_map[img_id][sev] += 1
    for img in images:
        img.damage_severities = damage_map.get(img.id, {0: 0, 1: 0, 2: 0, 3: 0})

    return images


def _get_image_id(supabase, n: int) -> str:
    """
    Gets the image id (primary key) based on ordinal
    """
    res = supabase.table("images").select("id").eq("ordinal", n).single().execute()
    if not res.data:
        raise HTTPException(status_code=404, detail=f"Image with ordinal {n} not found")
    return res.data["id"]


def create_comment_helper(supabase, user_email, ordinal, comment, damage):
    """
    Publishes comment
    """
    image_id = _get_image_id(supabase, ordinal)

    res = (
        supabase.table("comments")
        .insert(
            {
                "email_id": user_email,
                "image_id": image_id,
                "body": comment,
                "damage_sev": damage,
            }
        )
        .execute()
    )

    if not res.data:
        raise HTTPException(status_code=500, detail="Insert failed")


def read_user_comment_helper(
    supabase, user_email: str, ordinal: int
) -> Optional[CommentsRow]:
    """
    Reads most recent comment from a user
    """
    image_id = _get_image_id(supabase, ordinal)

    res = (
        supabase.table("comments")
        .select("*")
        .eq("image_id", image_id)
        .eq("email_id", user_email)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )

    rows = res.data or []
    if not rows:
        return None

    r = rows[0]
    return CommentsRow(
        email_id=r["email_id"],
        image_id=r["image_id"],
        body=r["body"],
        damage=r["damage_sev"],
        created_at=r["created_at"],
    )


def update_user_comment_helper(supabase, user_email, ordinal, comment, damage):
    """
    Update comments table with new damage and comment
    """
    image_id = _get_image_id(supabase, ordinal)

    res = (
        supabase.table("comments")
        .update({"body": comment, "damage_sev": damage})
        .match({"email_id": user_email, "image_id": image_id})
        .execute()
    )

    if not res.data:
        raise HTTPException(status_code=500, detail="Update failed")


def get_user_num_comments(supabase, user_email):
    """
    Gets number of comments user has made
    """
    resp = supabase.table("comments").select("*").eq("email_id", user_email).execute()
    return len(resp.data) or 0


def get_damage_aggregates_for_user(supabase, user_email):
    """
    Gets the number of each damage level a user has labeled and the skew
    """
    resp = (
        supabase.table("comments")
        .select("email_id, damage_sev")
        .eq("email_id", user_email)
        .execute()
    )
    dmg_aggregates = {
        "sev_0_count": 0,
        "sev_1_count": 0,
        "sev_2_count": 0,
        "sev_3_count": 0,
    }
    if not resp.data:
        return dmg_aggregates
    for row in resp.data:
        sev_num = row["damage_sev"]
        dmg_aggregates[f"sev_{sev_num}_count"] += 1

    dmg_values = np.array(list(dmg_aggregates.values()))
    std_dev = np.std(dmg_values, ddof=1)
    if std_dev == 0:
        skew = 0
        return dmg_aggregates, skew

    mean = np.mean(dmg_values)
    diff = (dmg_values - mean) / std_dev
    skew = 2 * np.sum(diff**3) / 3

    return dmg_aggregates, skew


def get_predictions_and_confusions_for_user(supabase, user_email):
    """
    Gets the model predictions and confusions for the images the user has labeled
    """
    resp = supabase.rpc(
        "get_predictions_and_confusions_for_user", {"u_email": user_email}
    ).execute()
    return resp.data or []


def get_damage_aggregates_all(supabase):
    """
    Gets total damage aggregates across all images
    """
    resp = supabase.rpc("get_damage_aggregates_all", {}).execute()
    if not resp.data[0]:
        return {
            "sev_0_count": 0,
            "sev_1_count": 0,
            "sev_2_count": 0,
            "sev_3_count": 0,
        }, 0

    dmg_aggregates = resp.data[0]

    dmg_values = np.array(list(dmg_aggregates.values()))
    std_dev = np.std(dmg_values, ddof=1)
    if std_dev == 0:
        skew = 0
        return dmg_aggregates, skew

    mean = np.mean(dmg_values)
    diff = (dmg_values - mean) / std_dev
    skew = 2 * np.sum(diff**3) / 3

    return dmg_aggregates, skew


def get_top_ds_and_avg_ds_all(supabase):
    """
    Gets list of top damage severity vs average damage severity for each image with confusion
    """
    resp = (
        supabase.table("image_stats")
        .select("top_severity, avg_damage_sev, confusion")
        .execute()
    )
    return resp.data or []

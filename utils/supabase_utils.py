# supabase_utils.py
from datetime import datetime
import uuid
from fastapi import HTTPException, UploadFile
from supabase import Client
from typing import Optional
from .util_types.supabase_types import ImagesRow, CommentsRow

def _ext_from_content_type(ct: str) -> str:
    """
    idk why this is important but it fixed an issue i had ty chatgpt
    """
    mapping = {"image/png": ".png","image/jpeg": ".jpg","image/jpg": ".jpg","image/webp": ".webp","image/gif": ".gif"}
    return mapping.get((ct or "").lower(), "")

def upload_image_helper(supabase: Client, file: UploadFile, content: bytes) -> ImagesRow:
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
            {"contentType": file.content_type or "application/octet-stream", "upsert": False},
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
                raise RuntimeError("Insert succeeded but follow-up select returned no rows")
            row = fetched.data[0]
    except Exception as e:
        # try remove failed insert
        try:
            supabase.storage.from_(bucket).remove([key])
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Images Table Insert Failed: {e}")

    return ImagesRow(
        id=row["id"],
        storage_path=row["storage_path"],
        created_at=row["created_at"],
        ordinal=row["ordinal"]
    )

def _signed_url_for_storage_path(storage_path: str, supabase: Client, SIGNED_URL_TTL) -> Optional[str]:
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
        out.append(ImagesRow(
            id=r["id"],
            storage_path=r["storage_path"],
            created_at=r.get("created_at"),
            ordinal=r["ordinal"],
            url=_signed_url_for_storage_path(r["storage_path"], supabase, SIGNED_URL_TTL),
        ))

    return out

def _get_image_id(supabase, n: int) -> str:
    """
    Gets the image id (primary key) based on ordinal
    """
    res = (
        supabase.table("images")
        .select("id")
        .eq("ordinal", n)
        .single()
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail=f"Image with ordinal {n} not found")
    return res.data["id"]

def create_comment_helper(supabase, user_email, ordinal, comment):
    """
    Publishes comment
    """
    image_id = _get_image_id(supabase, ordinal)

    res = (
        supabase.table("comments")
        .insert({"email_id": user_email, "image_id": image_id, "body": comment})
        .execute()
    )

    if not res.data:
        raise HTTPException(status_code=500, detail="Insert failed")

    row = res.data[0]

    return CommentsRow(
        email_id = row["email_id"],
        image_id = row["image_id"],
        body = row["body"],
        created_at = row["created_at"]
    )

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
        created_at=r["created_at"],
    )
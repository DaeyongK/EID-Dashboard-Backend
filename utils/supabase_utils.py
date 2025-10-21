# supabase_utils.py
from datetime import datetime
import uuid
from fastapi import HTTPException, UploadFile
from supabase import Client
from typing import Optional
from .util_types.supabase_types import ImagesRow

def _ext_from_content_type(ct: str) -> str:
    mapping = {"image/png": ".png","image/jpeg": ".jpg","image/jpg": ".jpg","image/webp": ".webp","image/gif": ".gif"}
    return mapping.get((ct or "").lower(), "")

def upload_image_helper(supabase: Client, file: UploadFile, content: bytes) -> ImagesRow:
    bucket = "images"

    ext = _ext_from_content_type(file.content_type)
    if not ext and file.filename and "." in file.filename:
        ext = "." + file.filename.rsplit(".", 1)[1].lower()
    key = f"{datetime.utcnow():%Y/%m}/{uuid.uuid4()}{ext}"

    # 1) Upload to Storage (path first, then bytes)
    try:
        supabase.storage.from_(bucket).upload(
            key,
            content,
            {"contentType": file.content_type or "application/octet-stream", "upsert": False},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {e}")

    # 2) Insert DB row
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
    bucket = "images"
    key = storage_path
    try:
        signed = supabase.storage.from_(bucket).create_signed_url(key, SIGNED_URL_TTL)
        return signed.get("signedURL")
    except Exception as e:
        return None

def get_images(supabase: Client, start: int, end: int, SIGNED_URL_TTL):
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
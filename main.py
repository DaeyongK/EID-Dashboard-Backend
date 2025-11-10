from typing import Optional

from fastapi import FastAPI, Request, Body, UploadFile, File, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import os
from dotenv import load_dotenv
from fastapi.responses import RedirectResponse, JSONResponse
from authlib.integrations.starlette_client import OAuth
from starlette.middleware.sessions import SessionMiddleware
from supabase import create_client, Client
import uuid, io
from datetime import datetime
from utils.util_types.supabase_types import ImagesRow, CommentsRow
from utils import inference, supabase_utils
from utils.supabase_utils import CommentCreate
import json
import asyncio

load_dotenv()

app = FastAPI(
    title="EID_Dashboard_Backend", description="Backend API for the EID Dashboard"
)

FRONTEND_URL = os.getenv("FRONTEND_URL")
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
SIGNED_URL_TTL = int(os.getenv("SIGNED_URL_TTL", "3600"))

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

oauth = OAuth()
CONF_URL = "https://accounts.google.com/.well-known/openid-configuration"
oauth.register(
    name="google",
    server_metadata_url=CONF_URL,
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    client_kwargs={"scope": "openid email profile"},
)

app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET_KEY"))
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL, "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup_event():
    inference.download_model()
    global model
    model = inference.load_model()


@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.get("/login", summary="Initiate Google OAuth login")
async def login(request: Request):
    """
    Redirects the user to Google's OAuth 2.0 authorization page.

    The user will be prompted to log in to their Google account and
    grant permissions for this app. After successful login, Google
    will redirect the user to the `/auth` endpoint with an authorization code.

    Returns:
        RedirectResponse: Redirects the user's browser to Google's login page.
    """
    redirect_uri = request.url_for("auth")
    return await oauth.google.authorize_redirect(request, redirect_uri)


@app.post("/logout", summary="Handle Google OAuth logout")
async def logout(request: Request):
    """
    Logs out the current user by clearing their authentication cookie.

    Returns:
        JSONResponse: JSON object indicating successful logout.
    """
    response = JSONResponse({"ok": True})
    response.delete_cookie(key="user")
    return response


@app.get("/auth", summary="Handle Google OAuth callback")
async def auth(request: Request):
    """
    Handles the OAuth 2.0 callback from Google after the user logs in.

    This endpoint exchanges the authorization code for an access token,
    retrieves the user's profile information (email, name, etc.), and
    optionally stores it in a cookie or database. Finally, it redirects
    the user back to the frontend.

    Returns:
        RedirectResponse: Redirects the user to the frontend URL, setting
        a cookie with their email.
    """
    token = await oauth.google.authorize_access_token(request)
    user = token.get("userinfo")

    if not user:
        raise HTTPException(status_code=400, detail="No User info from Google")

    frontend_url = os.getenv("FRONTEND_URL")
    response = RedirectResponse(url=f"{frontend_url}/")
    response.set_cookie(
        key="user",
        value=json.dumps(
            {
                "email": user["email"],
                "picture": user["picture"],
            }
        ),
    )
    return response


@app.get("/me", summary="Get current authenticated user")
async def me(request: Request):
    """
    Returns information about the currently logged-in user.

    This endpoint reads the 'user' cookie set during the OAuth login
    flow to determine whether the user is authenticated.

    Returns:
        dict: A JSON object with:
            - "authenticated" (bool): True if the user is logged in.
            - "email" (str, optional): The user's email if authenticated.
    """
    user_cookie = request.cookies.get("user")
    
    if not user_cookie:
        return {"authenticated": False}
    
    user = json.loads(user_cookie)
    
    return {
        "authenticated": True,
        "email": user["email"],
        "picture": user["picture"],
    }


@app.post(
    "/images", summary="Upload an Image to Supabase Database", response_model=ImagesRow
)
async def upload_image(
    file: UploadFile = File(...),
):
    """
    Only if we want to add the feature of uploading more photos down the line
    """
    content = await file.read()
    
    if not content:
        raise HTTPException(status_code=400, detail="Empty File")

    supabase_utils.upload_image_helper(supabase, file, content)


@app.get(
    "/images/range",
    summary="Get images in an inclusive ordinal range",
    description="max_window (20) prevents massive responses",
    response_model=list[ImagesRow],
)
def get_images_range(
    start: int = Query(..., ge=1),
    end: int = Query(..., ge=1),
):
    """
    Inclusive Get Function for Images based on Ordinal
    """
    max_window: int = 20  # guardrail to prevent huge responses; tweak as needed

    if end < start:
        raise HTTPException(status_code=400, detail="end must be >= start")
    if (end - start + 1) > max_window:
        raise HTTPException(
            status_code=400, detail=f"range too large; max {max_window}"
        )

    return supabase_utils.get_images(supabase, start, end, SIGNED_URL_TTL)

@app.get(
    "/images/aggregate_damages",
    summary="Get images with aggregated damage severities",
    description="Fetches images in range and summarizes comment severity counts for each image.",
    response_model=list[ImagesRow],
)
def get_images_with_damage_aggregates(
    start: int = Query(..., ge=1),
    end: int = Query(..., ge=1),
):
    """
    For each image in the range [start, end], return an ImagesRow with a damage_counts dict
    """
    max_window = 20
    if end < start:
        raise HTTPException(status_code=400, detail="end must be >= start")
    if (end - start + 1) > max_window:
        raise HTTPException(status_code=400, detail=f"Range too large; max {max_window}")

    return supabase_utils.get_damage_aggregates_for_images(
        supabase, start, end, SIGNED_URL_TTL
    )

@app.post(
    "/comments/write/{n}",
    summary="Writes comment to database, updates if comment exists",
)
def create_comment(
    n: int,
    request: Request,
    comment: CommentCreate,
):
    """
    Publishes comment to database for users
    """
    user_cookie = request.cookies.get("user")
    user_email = json.loads(user_cookie).get("email") if user_cookie else None
    
    if not user_cookie:
        raise HTTPException(
            status_code=401, detail="No user identity, please authenticate"
        )
    
    if not (0 <= comment.damage_sev <= 3):
        raise HTTPException(
            status_code=422,
            detail="Damage severity must be between 0 and 3 (inclusive)",
        )
    
    if not supabase_utils.read_user_comment_helper(supabase, user_email, n):
        supabase_utils.create_comment_helper(
            supabase, user_email, n, comment.body, comment.damage_sev
        )

    supabase_utils.update_user_comment_helper(supabase, user_email, n, comment.body, comment.damage_sev)


@app.get(
    "/comments/read/{n}",
    summary="Reads comments from database, returns null if no record",
    response_model=Optional[CommentsRow],
)
def read_comment(n: int, request: Request):
    """
    Given ordinal of image, read the user's previous comment, if no comment for that user in that image
    return null
    """
    user_cookie = request.cookies.get("user")
    user_email = json.loads(user_cookie).get("email") if user_cookie else None

    if not user_cookie:
        raise HTTPException(
            status_code=401, detail="No user identity, please authenticate"
        )

    return supabase_utils.read_user_comment_helper(supabase, user_email, n)


@app.get(
    "/infer/{ordinal}",
    summary="Performs model inference on an image by ordinal",
    response_model=int,
)
async def infer_image(ordinal: int):
    """
    Asynchronous endpoint to perform inference on an image by ordinal.
    """
    images = await asyncio.to_thread(
        supabase_utils.get_images, supabase, ordinal, ordinal, SIGNED_URL_TTL
    )
    if not images:
        raise HTTPException(
            status_code=404, detail=f"No image found with ordinal {ordinal}"
        )
    img_url = images[0].url
    pred_class = await asyncio.to_thread(inference.make_inference, model, img_url)
    return pred_class

@app.get(
    "/images/labeled/",
    summary="Get a range of LABELLED images for current user",
    description="max_window (20) prevents massive responses",
    response_model=list[ImagesRow],
)
def get_images_labeled_range(
    request: Request,
    start: int = Query(..., ge=1), # mandatory(...), greater than or equal to 1
    end: int = Query(..., ge=1) # mandatory(...), greater than or equal to 1

    
):
    """
    Get Function for Labeled Images - images in range (start, end) from the table of labeled images for current user, newest first
    """
    max_window: int = 20  # guardrail to prevent huge responses; tweak as needed

    if end < start:
        raise HTTPException(status_code=400, detail="end must be >= start")
    if (end - start + 1) > max_window:
        raise HTTPException(
            status_code=400, detail=f"range too large; max {max_window}"
        )
    
    user_cookie = request.cookies.get("user")
    user_email = json.loads(user_cookie).get("email") if user_cookie else None

    if not user_email:
        raise HTTPException(
            status_code=401, detail="No user identity, please authenticate"
        )

    return supabase_utils.get_images_labeled(supabase, start, end, user_email, SIGNED_URL_TTL)
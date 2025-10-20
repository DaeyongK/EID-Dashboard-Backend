from typing import Optional

from fastapi import FastAPI, Request, Depends, UploadFile, File, Form, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import os
from dotenv import load_dotenv
from fastapi.responses import RedirectResponse
from authlib.integrations.starlette_client import OAuth
from starlette.middleware.sessions import SessionMiddleware
from supabase import create_client, Client
import uuid, io
from datetime import datetime

load_dotenv()

app = FastAPI()

FRONTEND_URL = os.getenv("FRONTEND_URL")
SUPABASE_URL = os.environ["SUPABASE_URL"]
# Worry about this when we hosting
# SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
SIGNED_URL_TTL = int(os.getenv("SIGNED_URL_TTL", "3600"))


oauth = OAuth()
CONF_URL = 'https://accounts.google.com/.well-known/openid-configuration'
oauth.register(
    name='google',
    server_metadata_url=CONF_URL,
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    client_kwargs={'scope': 'openid email profile'}
)

app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET_KEY"))
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL, "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
    redirect_uri = request.url_for('auth')
    return await oauth.google.authorize_redirect(request, redirect_uri)

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
    user = token.get('userinfo')
    frontend_url = os.getenv("FRONTEND_URL")
    response = RedirectResponse(url=f"{frontend_url}/")
    response.set_cookie(key="user", value=user["email"])
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
    user_email = request.cookies.get("user")
    if not user_email:
        return {"authenticated": False}
    return {"authenticated": True, "email": user_email}
# Setup Instructions

1. Create Virtual Environment with
```bash
python3 -m venv venv
```

2. Activate venv
```bash
# macOS / Linux
source venv/bin/activate

# Windows (PowerShell)
venv\Scripts\Activate.ps1

# Windows (CMD)
venv\Scripts\activate.bat
```
3. Install requirements
```bash
pip install -r requirements.txt
```

4. Create .env file in root (refer to text channels for client ID and secret)
```bash
ENVIRONMENT=development
FRONTEND_URL=http://localhost:3000
BACKEND_URL=http://localhost:8000
GOOGLE_CLIENT_ID={your_local_google_client_id}
GOOGLE_CLIENT_SECRET={your_local_google_secret}
SESSION_SECRET_KEY={your_session_secret_key}
```

5. Launch app
```bash
uvicorn main:app --reload
```

6. Reference backend API descriptions by navigating to [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)



# Deploy FastAPI on Render

Use this repo as a template to deploy a Python [FastAPI](https://fastapi.tiangolo.com) service on Render.

See https://render.com/docs/deploy-fastapi or follow the steps below:

## Manual Steps

1. You may use this repository directly or [create your own repository from this template](https://github.com/render-examples/fastapi/generate) if you'd like to customize the code.
2. Create a new Web Service on Render.
3. Specify the URL to your new repository or this repository.
4. Render will automatically detect that you are deploying a Python service and use `pip` to download the dependencies.
5. Specify the following as the Start Command.

    ```shell
    uvicorn main:app --host 0.0.0.0 --port $PORT
    ```

6. Click Create Web Service.

Or simply click:

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/render-examples/fastapi)

## Thanks

Thanks to [Harish](https://harishgarg.com) for the [inspiration to create a FastAPI quickstart for Render](https://twitter.com/harishkgarg/status/1435084018677010434) and for some sample code!
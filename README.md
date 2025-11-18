# EID Dashboard Backend

## Description

This repository contains the backend services for our web application. Built with FastAPI, it integrates a Supabase PostgreSQL database and provides endpoints that support frontend features such as image display and rating submission.

The backend also handles model inference by downloading a PyTorch model from Google Cloud Platform (GCP) and running it on user-submitted images. It includes an interactive, auto-generated API documentation page, making it easy for developers to explore and test endpoints.

In addition, the backend supports user authentication, allowing us to track user-specific data. For the website’s analysis page, it also features endpoints that compute and return the data visualized there.

## Installation

1. Download the codebase
 ```
 git clone https://github.com/DaeyongK/EID-Dashboard-Backend.git
 ```

3. Create Virtual Environment with
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

4. Copy backend `.env` file into root

5. Copy `gcs_credentials.json` into root directory

## Execution

1. Launch app (Note: you will also need to launch frontend if you want to see the full website)
```bash
uvicorn main:app --reload
```

2. Reference backend API descriptions by navigating to [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

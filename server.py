from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse
import uvicorn
import requests
import csv
import io
from typing import List, Dict, Any, Optional

app = FastAPI()

# Baubuddy API credentials and endpoints
LOGIN_URL = "https://api.baubuddy.de/index.php/login"
VEHICLES_URL = "https://api.baubuddy.de/dev/index.php/v1/vehicles/select/active"
LABEL_URL = "https://api.baubuddy.de/dev/index.php/v1/labels/{}"
USERNAME = "365"
PASSWORD = "1"
AUTH_HEADER = "Basic QVBJX0V4cGxvcmVyOjEyMzQ1NmlzQUxhbWVQYXNz"


def get_access_token() -> str:
    payload = {"username": USERNAME, "password": PASSWORD}
    headers = {
        "Authorization": AUTH_HEADER,
        "Content-Type": "application/json"
    }
    response = requests.post(LOGIN_URL, json=payload, headers=headers)
    if response.status_code != 200:
        raise HTTPException(status_code=500, detail="Failed to authenticate with Baubuddy API.")
    data = response.json()
    return data["oauth"]["access_token"]


def fetch_vehicles(access_token: str) -> List[Dict[str, Any]]:
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(VEHICLES_URL, headers=headers)
    if response.status_code != 200:
        raise HTTPException(status_code=500, detail="Failed to fetch vehicles from Baubuddy API.")
    return response.json()


def fetch_label_color(label_id: str, access_token: str) -> Optional[str]:
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(LABEL_URL.format(label_id), headers=headers)
    if response.status_code != 200:
        return None
    data = response.json()
    return data.get("colorCode")


def parse_csv(file_bytes: bytes) -> List[Dict[str, Any]]:
    text = file_bytes.decode("utf-8")
    reader = csv.DictReader(io.StringIO(text))
    return [row for row in reader]


def merge_vehicles(api_vehicles: List[Dict[str, Any]], csv_vehicles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    # Use rnr as unique key if available, else fallback to id
    seen = set()
    merged = []
    for v in api_vehicles + csv_vehicles:
        key = v.get("rnr") or v.get("id")
        if key and key not in seen:
            seen.add(key)
            merged.append(v)
    return merged


def filter_vehicles_with_hu(vehicles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [v for v in vehicles if v.get("hu")]


def resolve_label_colors(vehicles: List[Dict[str, Any]], access_token: str) -> None:
    for v in vehicles:
        label_ids = v.get("labelIds")
        if isinstance(label_ids, str):
            try:
                import json as _json
                label_ids = _json.loads(label_ids)
            except Exception:
                label_ids = []
        if not isinstance(label_ids, list):
            label_ids = []
        v["labelColors"] = []
        for label_id in label_ids:
            color = fetch_label_color(str(label_id), access_token)
            if color:
                v["labelColors"].append(color)


@app.post("/vehicles")
async def process_vehicles(file: UploadFile = File(...)):
    try:
        file_bytes = await file.read()
        csv_vehicles = parse_csv(file_bytes)
        access_token = get_access_token()
        api_vehicles = fetch_vehicles(access_token)
        merged = merge_vehicles(api_vehicles, csv_vehicles)
        filtered = filter_vehicles_with_hu(merged)
        resolve_label_colors(filtered, access_token)
        return JSONResponse(content=filtered)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

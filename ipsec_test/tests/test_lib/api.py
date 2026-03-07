import requests
from config import API_BASE


def get(path, params=None):
    r = requests.get(f"{API_BASE}{path}", params=params)

    if r.status_code >= 400:
        print("API ERROR:", r.status_code, r.text)

    r.raise_for_status()
    return r.json()

def post(path, payload=None):
    r = requests.post(f"{API_BASE}{path}", json=payload, timeout=15)

    if r.status_code >= 400:
        print("\nAPI ERROR")
        print("Status:", r.status_code)
        print("Response:", r.text)

    #r.raise_for_status()

    return r.json()
    
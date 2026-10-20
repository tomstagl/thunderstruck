import requests


def fetch_profile(user_id):
    return requests.get(f"https://api.example.com/users/{user_id}", timeout=5).json()  # boundary: HTTP

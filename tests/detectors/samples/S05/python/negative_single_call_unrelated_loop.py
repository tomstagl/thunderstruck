import requests


def check_releases(url):
    response = requests.get(url, timeout=3)
    response.raise_for_status()
    releases = []
    for release in response.json():
        if not release["prerelease"]:
            releases.append(release["tag_name"])
    return releases

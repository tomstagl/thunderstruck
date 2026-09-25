def poll(session, homepage_url):
    while True:
        resp = session.post("https://auth.example.com/token", timeout=5)
        access_token = resp.json()["access_token"]
        r = session.get(homepage_url, headers={"Authorization": access_token}, timeout=5)
        if r.ok:
            return r.json()

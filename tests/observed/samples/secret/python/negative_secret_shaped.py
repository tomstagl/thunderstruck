import hvac

client = hvac.Client()


def ledger_password():
    # client.secrets.kv.v2.read_secret_version(path="ledger/commented")
    secret = client.secrets.kv.v2.read_secret_version(path="AbCdEfGhIjKlMnOpQrStUvWxYz0123456789AbCd")
    return secret["data"]["data"]["password"]

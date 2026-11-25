import hvac

client = hvac.Client()


def ledger_password():
    secret = client.secrets.kv.v2.read_secret_version(path="ledger/db")
    return secret["data"]["data"]["password"]

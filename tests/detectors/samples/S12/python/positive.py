MAX_RETRIES = 5


def charge(payment):
    retries = 0
    while retries < MAX_RETRIES:
        try:
            return gateway.charge(payment)
        except GatewayError:
            retries += 1
    raise RuntimeError("gave up")

def to_error(response):
    if response.status_code == 429:
        return RateLimitedError(response)
    if response.status_code >= 500:
        return UpstreamError(response)
    return None

import boto3


def table():
    return boto3.client("dynamodb", region_name="eu-west-1")  # boundary: cloud SDK

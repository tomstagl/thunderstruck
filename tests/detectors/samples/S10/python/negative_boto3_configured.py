import boto3
from botocore.config import Config
s3 = boto3.client("s3", config=Config(retries={"max_attempts": 2, "mode": "standard"}))

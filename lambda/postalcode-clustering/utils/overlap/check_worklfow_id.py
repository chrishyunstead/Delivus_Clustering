import re

import boto3

s3 = boto3.client("s3")


def workflow_exists_in_s3(workflow_id, bucket, s3_prefix):
    workflow_id = str(workflow_id).strip()
    if not s3_prefix.endswith("/"):
        s3_prefix += "/"

    print(
        f"Checking for workflow_id: {workflow_id} in bucket: {bucket} with prefix: {s3_prefix}"
    )

    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=s3_prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith(".json") and key.startswith(f"{s3_prefix}{workflow_id}"):
                print(f"Found: {key}")
                return True

    print(f"Not found: workflow_id={workflow_id}")
    return False


def get_next_overlap_workflow_id(workflow_id, bucket_name, s3_prefix):
    try:
        paginator = s3.get_paginator("list_objects_v2")
        page_iterator = paginator.paginate(Bucket=bucket_name, Prefix=s3_prefix)
    except Exception:
        return f"{workflow_id}_OL_1"

    max_number = 0
    pattern = re.compile(
        rf"{re.escape(s3_prefix)}{re.escape(workflow_id)}_OL_(\d+)(?:_.*)?\.json$"
    )

    for page in page_iterator:
        for obj in page.get("Contents", []):
            key = obj["Key"]
            match = pattern.match(key)
            if match:
                number = int(match.group(1))
                max_number = max(max_number, number)

    next_number = max_number + 1
    return f"{workflow_id}_OL_{next_number}"

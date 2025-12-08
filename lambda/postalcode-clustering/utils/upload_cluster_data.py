import io
import os

import boto3
import pandas as pd

s3 = boto3.client("s3")


def preprocess_shipping_data(df):
    df = df.copy()

    df = df.rename(
        columns={
            "code": "sector_code",
            "driver_type": "cluster_type",
            "cluster_label": "cluster_id",
        }
    )

    if "cluster_id" in df.columns:
        df["cluster_id"] = df["cluster_id"].str.replace("-", "", regex=False)
        df["cluster_no"] = (
            df["cluster_id"].str.extract(r"(\d+)").astype(float).astype("Int64")
        )

    print(df.info())
    return df


def upload_clustered_data_to_s3(df, bucket, s3_prefix):

    df = preprocess_shipping_data(df)

    for cluster_id, group_df in df.groupby("cluster_id"):
        if "workflow_id" not in group_df.columns:
            continue

        workflow_id = group_df["workflow_id"].iloc[0]
        filename = f"{workflow_id}_{cluster_id}.json"
        s3_key = f"{s3_prefix}{filename}"

        # JSON으로 변환
        json_buffer = io.StringIO()
        group_df.to_json(json_buffer, orient="records", force_ascii=False, lines=True)

        # S3 업로드
        s3.put_object(
            Bucket=bucket,
            Key=s3_key,
            Body=json_buffer.getvalue(),
            ContentType="application/json",
        )

        print(f"Uploaded: s3://{bucket}/{s3_key}")

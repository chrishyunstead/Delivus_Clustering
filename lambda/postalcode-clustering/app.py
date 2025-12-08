import asyncio
import json
import os

import pandas as pd
from utils.common import is_weekend, normalize_region
from utils.data.db_handler import DBHandler
from utils.data.db_handler_pg import PostgresDBHandler
from utils.data.preprocess_params import (
    cal_time_difference,
    parse_event_params,
    uuid_list_to_int,
    uuid_list_to_str,
)
from utils.data.schedule_processor import ScheduleProcessor
from utils.data.shipping_processor import ShippingProcessor
from utils.overlap.check_worklfow_id import (
    get_next_overlap_workflow_id,
    workflow_exists_in_s3,
)
from utils.overlap.processor import overlap_processor
from utils.run_clustering import run_clustering
from utils.slack.send_slack_message import SendSlackMessage
from utils.upload_cluster_data import upload_clustered_data_to_s3
from utils.zipcode.pg_zip_processor import ZipCodeGroupProcessor
from utils.data.model_processor import load_data_from_google_sheets


def run_async(func, *args, **kwargs):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(func(*args, **kwargs))


def lambda_handler(event, context):
    print(f"Event: {event}")
    # def lambda_handler(event, context):
    # initialize the params and events_detail variables
    ACCOUNT_ENV = os.environ["ACCOUNT_ENV"]
    BUCKET_NAME = os.environ.get("BUCKET_NAME")
    print(f"Lambda 실행 환경: {ACCOUNT_ENV}")
    send_slack_message = SendSlackMessage()

    # Extract parameters from event
    params = parse_event_params(event)
    workflow_id = params["workflow_id"]

    # Extract workflow date information
    workflow_year, workflow_month, workflow_day = (
        workflow_id[:4],
        workflow_id[4:6],
        workflow_id[6:8],
    )

    s3_prefix = f"json-data/postalcode-clustering-1.0/{workflow_year}/{workflow_month}/{workflow_day}/"
    s3_prefix_ol = f"json-data/postalcode-clustering-ol-1.0/{workflow_year}/{workflow_month}/{workflow_day}/"

    workflow_date = f"{workflow_id[:4]}-{workflow_id[4:6]}-{workflow_id[6:8]}"

    # Convert UUID lists and timestamps
    pickup_batch_uuids = uuid_list_to_str(params["pickup_batch_uuid_list"])
    return_order_shop_uuids = uuid_list_to_str(params["return_order_shop_uuid_list"])
    shipping_shop_uuids = uuid_list_to_str(params["shipping_shop_uuid_list"])
    exclude_sector_ids = uuid_list_to_int(params["exclude_sector_ids"])
    delivery_date_shop_uuids = uuid_list_to_str(params["delivery_date_shop_uuid_list"])
    start_time = cal_time_difference(params["difference_in_minute"])
    end_time = cal_time_difference(params["difference_end_in_minute"])
    delivery_date = params["delivery_date"]

    print(f"Workflow ID: {workflow_id}")
    print(f"Workflow Date: {workflow_date}")
    print(f"Time Range: {start_time} ~ {end_time}")

    # Initialize processors
    db_handler = DBHandler()
    db_handler_pg = PostgresDBHandler()
    zip_processor = ZipCodeGroupProcessor(db_handler_pg)
    schedule_processor = ScheduleProcessor(db_handler)
    shipping_processor = ShippingProcessor(db_handler)

    # Run overlap clustering if file with workflow_id exists
    check_workflow = workflow_exists_in_s3(workflow_id, BUCKET_NAME, s3_prefix)
    if check_workflow:

        # Generate new workflow_id
        new_workflow_id = get_next_overlap_workflow_id(
            workflow_id, BUCKET_NAME, s3_prefix_ol
        )

        # Send slack message (start)
        send_slack_message.send_start_slack_message(new_workflow_id, ACCOUNT_ENV)

        # Fetch cluster data frrom Daas
        plan_no = int(workflow_id.split("_")[1])
        df_cluster_data = shipping_processor.get_cluster_data(workflow_date, plan_no)

        print(f"Cluster Data Loaded: {len(df_cluster_data)}")
        print(f"Cluster Data Columns: {df_cluster_data.columns}")

        # Fetch new shpping data
        new_df_shipping = run_async(
            shipping_processor.get_shipping_items_dataset,
            pickup_batch_uuids=pickup_batch_uuids,
            return_order_shop_uuids=return_order_shop_uuids,
            start_time=start_time,
            end_time=end_time,
            shipping_shop_uuids=shipping_shop_uuids,
            exclude_sector_ids=exclude_sector_ids,
            delivery_date=delivery_date,
            delivery_date_shop_uuids=delivery_date_shop_uuids,
        )
        # new_df_shipping = pd.read_csv("utils/data/20250308_overlap.csv")

        lat_null_count = new_df_shipping["lat"].isnull().sum()
        if lat_null_count > 0:

            send_slack_message.send_lat_alert_slack_message(
                workflow_id, ACCOUNT_ENV, lat_null_count
            )

            return {
                "statusCode": 500,
                "body": json.dumps(
                    {
                        "message": f"Failed to load Shipping data: {lat_null_count} latitudes are null"
                    }
                ),
            }

        print(f"New Shipping Data Loaded: {len(new_df_shipping)}")
        print(f"New Shipping Data Columns: {new_df_shipping.columns}")

        # Merge cluster data with new shipping data
        df_cluster_data = df_cluster_data.drop_duplicates(subset="shipping_uuid")
        new_df_shipping = new_df_shipping.drop_duplicates(subset="shipping_uuid")

        merged_df = pd.merge(
            new_df_shipping, df_cluster_data, on="shipping_uuid", how="left"
        )
        # Preporcessing merged data
        merged_df = merged_df.drop(
            columns=[col for col in merged_df.columns if col.endswith("_y")]
        )
        merged_df = merged_df.rename(
            columns={col: col[:-2] for col in merged_df.columns if col.endswith("_x")}
        )

        # Extract overlap shipping data
        df_overlap_shipping = merged_df[merged_df["cluster_label"].isna()]

        print(f"Overlap Shipping Data: {len(df_overlap_shipping)}")
        print(f"Overlap Shipping Data Columns: {df_overlap_shipping.columns}")

        # Generate overlap cluster
        df_result_data = overlap_processor(df_overlap_shipping, df_cluster_data)

        print(f"Result Data: {len(df_result_data)}")
        print(f"Result Data Columns: {df_result_data.columns}")

        # Upload result data to S3
        df_result_data["workflow_id"] = new_workflow_id
        upload_clustered_data_to_s3(df_result_data, BUCKET_NAME, s3_prefix_ol)

        # Send slack message (end)
        send_slack_message.send_end_slack_message(
            new_workflow_id, ACCOUNT_ENV, cluster_items_count=len(df_result_data)
        )
        return {
            "statusCode": 200,
            "body": json.dumps({"message": "Workflow ID already exists in S3"}),
        }
    
    # Fetch zip code data
    results = zip_processor.fetch_all_data()
    # required_keys = ["df_regular", "df_weekend"]
    required_keys = ["df_zipcode"]

    # Handle error if results are None, missing keys, or any DataFrame is None
    if (
        not results
        or not all(k in results for k in required_keys)
        or any(results[k] is None for k in required_keys)
    ):
        print("Failed to load data: fetch_all_data() returned None or incomplete data")
        return {
            "statusCode": 500,
            "body": json.dumps({"message": "Failed to load ZipCode data"}),
        }

    # Assign DataFrames from result dictionary
    # df_regular = results["df_regular"]
    # df_weekend = results["df_weekend"]

    df_zipcode = results["df_zipcode"]

    # print(
    #     f"ZipCode Data Loaded: Regular({len(df_regular)}), Weekend({len(df_weekend)})"
    # )
    print(
        f"ZipCode Data Loaded: ({len(df_zipcode)})"
    )

    print(f"pickup_batch_uuids: {pickup_batch_uuids}")
    print(f"return_order_shop_uuids: {return_order_shop_uuids}")
    print(f"shipping_shop_uuids: {shipping_shop_uuids}")
    print(f"exclude_sector_ids: {exclude_sector_ids}")
    print(f"delivery_date_shop_uuids: {delivery_date_shop_uuids}")
    print(f"delivery_date: {delivery_date}")

    df_shipping = run_async(
        shipping_processor.get_shipping_items_dataset,
        pickup_batch_uuids=pickup_batch_uuids,
        return_order_shop_uuids=return_order_shop_uuids,
        start_time=start_time,
        end_time=end_time,
        shipping_shop_uuids=shipping_shop_uuids,
        exclude_sector_ids=exclude_sector_ids,
        delivery_date=delivery_date,
        delivery_date_shop_uuids=delivery_date_shop_uuids,
    )

    lat_null_count = df_shipping["lat"].isnull().sum()
    if lat_null_count > 0:

        send_slack_message.send_lat_alert_slack_message(
            workflow_id, ACCOUNT_ENV, lat_null_count
        )

        return {
            "statusCode": 500,
            "body": json.dumps(
                {
                    "message": f"Failed to load Shipping data: {lat_null_count} latitudes are null"
                }
            ),
        }

    send_slack_message.send_start_slack_message(workflow_id, ACCOUNT_ENV)

    if df_shipping is None:
        print("Failed to load data: get_shipping_items_dataset() returned None")
        send_slack_message.send_end_slack_message(
            workflow_id, ACCOUNT_ENV, cluster_items_count=0
        )
        return {
            "statusCode": 500,
            "body": json.dumps({"message": "Failed to load Shipping data"}),
        }

    df_schedule = schedule_processor.fetch_schedules(workflow_date)

    # df_shipping = pd.read_csv("utils/data/20250308_shipping_items.csv")
    # df_schedule = pd.read_csv("utils/data/20250308_bunny.csv")

    print(f"Shipping Data Loaded: {len(df_shipping)}")
    print(f"Schedule Data Loaded: {len(df_schedule)}")

    # Extract date and identify BLUE areas
    blue_areas = []

    if not df_schedule.empty and "Date" in df_schedule.columns:
        dt_series = df_schedule["Date"].drop_duplicates()
        if not dt_series.empty:
            dt = dt_series.iloc[0]
            year, month, day = dt.year, dt.month, dt.day
            if "Type" in df_schedule.columns and "Area" in df_schedule.columns:
                blue_areas = list(
                    df_schedule.loc[df_schedule["Type"] == "BLUE", "Area"]
                )
    else:
        year = int(workflow_id[:4])
        month = int(workflow_id[4:6])
        day = int(workflow_id[6:8])
    print(f"\nBLUE areas: {blue_areas}")

    # Process weekday/weekend zipcode groups
    # if is_weekend(year, month, day):
    #     df_weekend["region"] = df_weekend["region"].apply(normalize_region)
    #     chosen_df_weekend = df_weekend[~df_weekend["region"].isin(blue_areas)]

    #     chosen_zipcode_groups = chosen_df_weekend
    #     chosen_zipcode_groups.reset_index(drop=True, inplace=True)

    # else:
    #     df_regular["region"] = df_regular["region"].apply(normalize_region)
    #     chosen_df_regular = df_regular[~df_regular["region"].isin(blue_areas)]

    #     chosen_zipcode_groups = chosen_df_regular
    #     chosen_zipcode_groups.reset_index(drop=True, inplace=True)

    chosen_zipcode_groups = df_zipcode[~df_zipcode["region"].isin(blue_areas)]
    chosen_zipcode_groups.reset_index(drop=True, inplace=True)
    print(f"\nChosen Zipcode Groups after excluding BLUE areas:\n{chosen_zipcode_groups}")

    # 우편번호 5자리 맞추기
    df_shipping = df_shipping.astype({"zipcode": str})
    df_shipping["zipcode"] = df_shipping["zipcode"].astype(str).str.zfill(5)

    max_df = load_data_from_google_sheets()

    # 클러스터링 실행
    all_KMeans_dfs, leftover_drivers = run_clustering(
        zipcode_groups=chosen_zipcode_groups,
        workflow_day_shipping_items_df=df_shipping,
        workflow_day_bunny_df=df_schedule,
        max_df = max_df
    )

    # 전체 그룹들 중 20개 미만인 지역
    all_KMeans_dfs_20_less = (
        all_KMeans_dfs.groupby("cluster_label")
        .agg({"shipping_uuid": "count"})
        .reset_index()
    )
    all_KMeans_dfs_20_less_group = all_KMeans_dfs_20_less[
        all_KMeans_dfs_20_less["shipping_uuid"] < 20
    ]

    # 드라이버 할당 되지 않은 그룹들중 20개 미만인 지역
    all_KMeans_dfs_sam = (
        all_KMeans_dfs.groupby("group")
        .agg({"shipping_uuid": "count", "driver_type": "count"})
        .reset_index()
    )
    all_KMeans_dfs_sam_20less = all_KMeans_dfs_sam[
        all_KMeans_dfs_sam["driver_type"] == 0
    ]
    KMeans_dfs_none_driver_20less_group = all_KMeans_dfs_sam_20less[
        all_KMeans_dfs_sam_20less["shipping_uuid"] < 20
    ]

    # 결과 확인
    print("\n=== 벌크 지역 ===")
    print(blue_areas)
    print("\n=== 배정받지 못한 고정 기사 ===")
    print(leftover_drivers)
    print("\n=== 배정되지 않은 그룹들 중 물량 20개 미만인 지역 ===")
    print(KMeans_dfs_none_driver_20less_group)
    print("\n=== 전체 그룹들 중 물량 20개 미만인 지역 ===")
    print(all_KMeans_dfs_20_less_group)

    # Add workflow_id to the DataFrame
    all_KMeans_dfs["workflow_id"] = workflow_id

    upload_clustered_data_to_s3(all_KMeans_dfs, BUCKET_NAME, s3_prefix)

    send_slack_message.send_end_slack_message(
        workflow_id, ACCOUNT_ENV, cluster_items_count=len(all_KMeans_dfs)
    )

    # Return the response within the Lambda's output
    return {
        "statusCode": 200,
        "body": json.dumps({"message": ACCOUNT_ENV}),
    }

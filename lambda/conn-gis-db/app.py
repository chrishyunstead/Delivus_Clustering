from utils.db_handler_pg import PostgresDBHandler
from utils.zipcode.zip_processor import ZipCodeGroupProcessor


def lambda_handler(event, context):
    try:
        db_handler_pg = PostgresDBHandler()
        zip_processor = ZipCodeGroupProcessor(db_handler_pg)

        results = zip_processor.fetch_all_data()
        df_regular = results["df_regular"]
        df_weekend = results["df_weekend"]

        print("Regular DataFrame:")
        print(df_regular)
        print("Weekend DataFrame:")
        print(df_weekend)

        return {
            "statusCode": 200,
            "body": "ZipCodeGroupProcessor initialized successfully.",
        }

    except Exception as e:
        return {"statusCode": 500, "body": f"Error: {str(e)}"}

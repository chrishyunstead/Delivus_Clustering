import gspread
import pandas as pd
from google.oauth2.service_account import Credentials
import os

def load_data_from_google_sheets():
    try:
        BASE_DIR = os.path.dirname(os.path.abspath(__file__))
        MAX_DELIVERY_KEY_PATH = os.path.join(BASE_DIR, "max-delivery-key.json")
        SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

        creds = Credentials.from_service_account_file(MAX_DELIVERY_KEY_PATH, scopes=SCOPES)
        gc = gspread.authorize(creds)

        SPREADSHEET_KEY = "1ciVZdzU6GnlV8YZuo0frIOmsoaAdGngNLBgE4cDBjek"
        SHEET_NAME = "max"
        worksheet = gc.open_by_key(SPREADSHEET_KEY).worksheet(SHEET_NAME)

        records = worksheet.get_all_records(expected_headers=[
            "Area",
            "day",
            "deliveries",
            "predicted_time_per_delivery",
            "available_delivery_time",
            "MAX_shipping",
            "max_shipping_buffer",
            "max_shipping_update",
            "MAX"
        ])

        df = pd.DataFrame(records)

        if df.empty:
            print("⚠️ 시트는 열렸지만 데이터가 비어 있습니다.")
        else:
            print(f"✅ max_sheet OPEN, shape: {df.shape}")

        return df

    except FileNotFoundError:
        print("❌ JSON 키파일을 찾을 수 없습니다.")
        return pd.DataFrame()

    except gspread.exceptions.WorksheetNotFound:
        print(f"❌ '{SHEET_NAME}' 시트를 찾을 수 없습니다.")
        return pd.DataFrame()

    except Exception as e:
        print(f"❌ 예기치 못한 오류: {e}")
        return pd.DataFrame()

import json
import pandas as pd

file_name = "sector_divided"

# JSON 파일 로드
with open(f"data/{file_name}.json", "r", encoding="utf-8") as file:
    raw_data = json.load(file)


# JSON을 DataFrame으로 변환하는 함수
def transform_zipcode_data(data):
    records = []

    for region_name, zipcodes in data.items():

        records.append(
            {
                "region": region_name,
                "zipcodes": json.dumps(zipcodes),  # JSON 리스트 형태 유지
            }
        )
    return pd.DataFrame(records)

# DataFrame 생성
df = transform_zipcode_data(raw_data)
df.to_csv(f"output/{file_name}.csv")

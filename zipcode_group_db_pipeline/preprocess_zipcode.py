import json
import pandas as pd

file_name = "regular_zipcode_groups_1"
weekday = 0

# JSON 파일 로드
with open(f"data/{file_name}.json", "r", encoding="utf-8") as file:
    raw_data = json.load(file)


# JSON을 DataFrame으로 변환하는 함수
def transform_zipcode_data(data):
    records = []

    for region, groups in data.items():
        region_name = (
            region.replace("_zipcode_groups", "")
            .replace("_주말", "")
            .replace("_평일", "")
        )

        for group_name, zipcodes in groups.items():
            group_letter = group_name.split("_")[1][0]  # "강북구_A_Zipcode" → "A"

            records.append(
                {
                    "region": region_name,
                    "group_name": group_letter,
                    "zipcodes": json.dumps(zipcodes),  # JSON 리스트 형태 유지
                    "weekday": weekday,
                }
            )

    return pd.DataFrame(records)


# DataFrame 생성
df = transform_zipcode_data(raw_data)
df.to_csv(f"output/{file_name}.csv")

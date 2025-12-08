import json
import pandas as pd
from shapely.geometry import shape, Polygon, MultiPolygon

# JSON 파일 로드
with open("data/merged.json", "r", encoding="utf-8") as file:
    data = json.load(file)


# 좌표 변환 함수 (위도, 경도를 경도, 위도로 변경)
def swap_coordinates(geometry):
    if isinstance(geometry, Polygon):
        new_coords = [(lon, lat) for lat, lon in list(geometry.exterior.coords)]
        return Polygon(new_coords)

    elif isinstance(geometry, MultiPolygon):
        new_polygons = []
        for poly in geometry.geoms:
            new_coords = [(lon, lat) for lat, lon in list(poly.exterior.coords)]
            new_polygons.append(Polygon(new_coords))
        return MultiPolygon(new_polygons)

    return geometry


# 데이터를 DataFrame으로 변환
records = []
for feature in data["features"]:
    properties = feature["properties"]
    # 좌표 변환 없이 그대로 사용
    geometry = shape(feature["geometry"])
    # 좌표 변환
    swapped_geometry = swap_coordinates(geometry)

    record = {
        "BAS_ID": properties.get("BAS_ID"),
        "BAS_AR": properties.get("BAS_AR"),
        "BAS_MGT_SN": properties.get("BAS_MGT_SN"),
        "CTP_KOR_NM": properties.get("CTP_KOR_NM"),
        "SIG_CD": properties.get("SIG_CD"),
        "SIG_KOR_NM": properties.get("SIG_KOR_NM"),
        "NTFC_DE": properties.get("NTFC_DE"),
        # WKT 형식으로 변환하여 저장
        "geometry": swapped_geometry.wkt,
    }

    records.append(record)

# DataFrame 생성
df = pd.DataFrame(records)

# CSV로 저장 (옵션)
df.to_csv("output/geojson_data.csv", index=False, encoding="utf-8")

# 결과 출력
print(df.head())
print(len(df))

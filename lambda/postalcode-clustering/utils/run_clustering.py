import pandas as pd
import numpy as np
from .common import normalize_region
from .process_region import process_region


def run_clustering(
    zipcode_groups,
    workflow_day_shipping_items_df,
    workflow_day_bunny_df,
    max_df
):
    """
    전체 지역(zipcode_groups) 순회하며
    1) process_region() 호출 -> 기사 배정
    2) 최종적으로 지역별 DataFrame 통합
    3) leftover 기사를 별도 DataFrame에 저장
    4) 시각화 결과 HTML 생성 (visualize_clusters)
    """

    # 통합할 DF
    all_filtered_geo_dfs = pd.DataFrame()
    all_KMeans_dfs = pd.DataFrame()

    # 고정기사 DF
    leftover_all_fix_drivers = pd.DataFrame()

    # 원본 df_shipping 복사
    df_shipping = workflow_day_shipping_items_df.copy()

    # 지역별 처리
    for region_name in zipcode_groups["region"].unique():

        # norm_region = normalize_region(region_name)
        region_df = df_shipping[df_shipping["Area"] == region_name]

        if region_df.empty:
            print(
                f"스킵: {region_name} - 해당 지역 데이터 없음"
            )
            
            continue
        (
            df_shipping_region,
            filtered_geo_df,
            leftover_all_fix_drivers,
        ) = process_region(
            region_name=region_name,
            norm_region=region_name,
            zipcode_groups=zipcode_groups,
            df_shipping=df_shipping,
            workflow_day_bunny_df=workflow_day_bunny_df,
            leftover_all_fix_drivers=leftover_all_fix_drivers,
            max_df = max_df
        )

        # 처리된 주문은 원본에서 제거 (이미 배정된 주문)
        df_shipping = df_shipping[
            ~df_shipping["shipping_uuid"].isin(df_shipping_region["shipping_uuid"])
        ]

        # 지역별 결과 통합
        all_filtered_geo_dfs = pd.concat(
            [all_filtered_geo_dfs, filtered_geo_df], ignore_index=True
        )
        all_KMeans_dfs = pd.concat(
            [all_KMeans_dfs, df_shipping_region], ignore_index=True
        )

    # 남은 미배정 주문(df_shipping)도 합침
    all_KMeans_dfs = pd.concat([all_KMeans_dfs, df_shipping], ignore_index=True)

    # 칼럼자체에 그룹이 없는 경우(배송 지역 물품이 아닌 경우 또는 내가 미처 zipcode_group 설정하지 못했을 때)
    if "group" not in all_KMeans_dfs.columns:
        all_KMeans_dfs['group']=np.nan
        all_KMeans_dfs['driver_type']=np.nan
        all_KMeans_dfs['driver_code']=np.nan

    # 그룹이 있는데 기사정보가 없는 행은 driver_type='WHITE'로 지정
    mask = (~all_KMeans_dfs["group"].isna()) & (all_KMeans_dfs["driver_type"].isna())
    all_KMeans_dfs.loc[mask, "driver_type"] = "WHITE"

    # 그룹이 없고, 기사정보가 없는 행은 driver_type = 'BLUE'로 지정 => 벌크
    mask1 = (all_KMeans_dfs["group"].isna()) & (all_KMeans_dfs["driver_type"].isna())
    all_KMeans_dfs.loc[mask1, "driver_type"] = "BLUE"

    # 1. driver_type 매핑 문자 정의
    type_mapping = {
        "WHITE": "W",
        "RAINBOW": "R",
        "YELLOW": "Y",
        "ORANGE": "O",
        # 나머지는 'B'로 처리
    }

    # 2. (Area, driver_type, group)가 모두 있는 행만 추출 (NaN은 제외)
    unique_rows = (
        all_KMeans_dfs[["Area", "driver_type", "group"]]
        .dropna(subset=["Area", "driver_type", "group"])
        .drop_duplicates()
    )

    # 3. Area별 + driver_type별 순번을 관리할 dict
    dict_area_type_seq = {}

    # 4. 최종 라벨 매핑 딕셔너리: dict_of_labels[(Area, driver_type, group)] = "강남W1" 등
    dict_of_labels = {}

    # unique_rows 순회하면서 순번 부여
    for _, row in unique_rows.iterrows():
        area_val = row["Area"]
        d_type = row["driver_type"]
        grp = row["group"]

        # (Area, driver_type) 별로 seq 1부터 시작
        key_area_type = (area_val, d_type)
        if key_area_type not in dict_area_type_seq:
            dict_area_type_seq[key_area_type] = 1
        else:
            dict_area_type_seq[key_area_type] += 1

        seq = dict_area_type_seq[key_area_type]

        # driver_type이 매핑 사전에 없으면 'B'
        letter = type_mapping.get(d_type, "B1")
        # 실제 라벨 형식: "강남-W1"
        label = f"{area_val}{letter}{seq}"

        # 해당 그룹(Area, driver_type, group)에 라벨 저장
        dict_of_labels[(area_val, d_type, grp)] = label

    # 각 행에서 (Area, driver_type, group)으로 dict_of_labels 조회
    for i in all_KMeans_dfs.index:
        area_val = all_KMeans_dfs.at[i, "Area"]
        d_type = all_KMeans_dfs.at[i, "driver_type"]
        grp = all_KMeans_dfs.at[i, "group"]

        key = (area_val, d_type, grp)
        # 매핑 딕셔너리에 있으면 그 라벨을, 없으면 기존 값을 유지
        if key in dict_of_labels:
            all_KMeans_dfs.at[i, "cluster_label"] = dict_of_labels[key]
        else:
            if pd.notna(area_val) and pd.notna(d_type):
                letter = type_mapping.get(d_type, "B1")
                all_KMeans_dfs.at[i, "cluster_label"] = f"{area_val}{letter}"

    # leftover 기사 출력
    print("\n### 전체 지역에서 '배정받지 못한 고정 기사' 모음 ###")
    if leftover_all_fix_drivers.empty:
        print("모든 고정 기사 배정 완료(남은 기사 없음)")
    else:
        print(leftover_all_fix_drivers)

    return all_KMeans_dfs, leftover_all_fix_drivers

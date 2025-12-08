import ast

import geopandas as gpd

# 알고리즘
import numpy as np

# 데이터 파이프라인
import pandas as pd
from shapely import wkt
import string
# 데이터 처리
from shapely.ops import unary_union

from .drivers.assign_drivers_handler import AssignDriversHandler
from .drivers.white_drivers_handler import WhiteDriversHandler

assignDriversHandler = AssignDriversHandler()
assign_fixed_drivers = assignDriversHandler.assign_fixed_drivers

whiteDriversHandler = WhiteDriversHandler()
isolate_white_clusters = whiteDriversHandler.isolate_white_clusters

# 5개 이하 클러스터 병합 기능 추후 구현
merge_tiny_clusters = whiteDriversHandler.merge_tiny_clusters

# def group_and_map_zipcodes(zipcode_groups, raw_shipping_items):

#     result_gdf = zipcode_groups

#     # 우편번호-그룹 매핑 생성
#     zipcode_to_group = {}
#     for _, row in result_gdf.iterrows():
#         group = row["group_name"]
#         # 문자열 형태의 zipcodes를 리스트로 변환
#         zipcodes_group = ast.literal_eval(row["zipcodes"])
#         for zipcode in zipcodes_group:
#             zipcode_to_group[zipcode] = group

#     # 배송 데이터 로드 및 그룹 매핑
#     df_shipping = raw_shipping_items
#     df_shipping["group"] = df_shipping["zipcode"].map(zipcode_to_group)
#     df_shipping = df_shipping[~df_shipping["group"].isna()]

#     return result_gdf, df_shipping

def group_and_map_zipcodes(zipcode_groups, raw_shipping_items):

    # zipcodes 리스트 평탄화
    df = zipcode_groups.explode("zipcodes")
    print(f'group_and_map_zipcodes - explode 후 df: {df.head()}')

    df["zipcodes"] = df["zipcodes"].astype(str).str.zfill(5)
    grouped = (
        df.groupby(["region", "group_name"], dropna=False)["zipcodes"]
          .agg(lambda s: sorted(set(s)))
          .reset_index()
    )
    result_gdf = grouped.copy()

    # A~Z 알파벳 시퀀스 준비
    alphabet = list(string.ascii_uppercase)
    used = set(result_gdf["group_name"].dropna())  # 이미 존재하는 그룹명
    alphabet_iter = iter([c for c in alphabet if c not in used])

    # group_name이 None인 경우 A부터 순서대로 부여
    def fill_group_name(name):
        if pd.isna(name):   # None 또는 NaN
            return next(alphabet_iter, None)  # A-Z 소진되면 None
        return name

    result_gdf["group_name"] = result_gdf["group_name"].apply(fill_group_name)
    
    print(f'group_and_map_zipcodes - grouped 결과: {result_gdf}')
    # -------------------------------
    # 우편번호-그룹 매핑 생성
    # -------------------------------
    zipcode_to_group = {}
    for _, row in result_gdf.iterrows():
        group = row["group_name"]
        zipcodes_group = row["zipcodes"]  # 이미 리스트라고 가정
        zipcodes_group = [str(z).zfill(5) for z in zipcodes_group]
        for zipcode in zipcodes_group:
            zipcode_to_group[zipcode] = group

    # -------------------------------
    # 배송 데이터 로드 및 그룹 매핑
    # -------------------------------
    df_shipping = raw_shipping_items.copy()
    df_shipping["group"] = df_shipping["zipcode"].map(zipcode_to_group)
    df_shipping = df_shipping[~df_shipping["group"].isna()]

    return result_gdf, df_shipping

def process_region(
    region_name,
    norm_region,
    zipcode_groups,
    df_shipping,
    workflow_day_bunny_df,
    leftover_all_fix_drivers,
    max_df
):

    print(f"### {region_name} 처리 시작 ###")

    zipcode_groups = zipcode_groups[zipcode_groups["region"] == region_name]

    # (2) 그룹화 및 데이터 저장
    result_gdf, df_shipping_region = group_and_map_zipcodes(zipcode_groups, df_shipping)
    print(f'group_and_map_zipcodes 결과 {df_shipping_region}')

    # 지역별 bunny 기사 필터링
    if (workflow_day_bunny_df is None or workflow_day_bunny_df.empty or 
        "Area" not in workflow_day_bunny_df.columns):
        print(f"[process_region] 스케줄 데이터가 없거나 비었거나 'Area' 컬럼이 없음. "
              f"지역 {region_name}에 대해 빈 데이터프레임 사용.")
        region_workflow_day_bunny_df = pd.DataFrame(columns=["Area", "Type"])
        
    else:
        try:
            region_workflow_day_bunny_df = workflow_day_bunny_df[
                workflow_day_bunny_df["Area"] == df_shipping_region.iloc[0]["Area"]
            ].copy()
        except Exception as e:
            print(f"[process_region] 데이터 필터링 오류: {e}. 빈 데이터프레임 사용.")
            region_workflow_day_bunny_df = pd.DataFrame(columns=["Area", "Type"])

    # (3) 고정 기사(YELLOW/RAINBOW/ORANGE) & 화이트(WHITE) 기사 분리
    fix_region_workflow_day_bunny_df = region_workflow_day_bunny_df[
        region_workflow_day_bunny_df["Type"].isin(["YELLOW", "RAINBOW", "ORANGE"])
    ].copy()

    print(f"{region_name} 고정기사 수: {len(fix_region_workflow_day_bunny_df)}")
    print(
        f"{region_name} workflow_day_bunny_df Area: {region_workflow_day_bunny_df['Area'].unique().tolist()}"
    )
    print(
        f"{region_name} df_shipping_region Area: {df_shipping_region['Area'].tolist()}"
    )

    # 버니에게 배정 전 그룹별 물량
    df_shipping_region_group_count = (
        df_shipping_region.groupby("group")["shipping_uuid"].agg("count").reset_index()
    )
    print(f"{region_name} 초기 그룹별 물량\n{df_shipping_region_group_count}")

    fix_drivers = len(fix_region_workflow_day_bunny_df)

    # 모델 해당 지역으로 필터링
    if max_df is None or max_df.empty:
        print(f"[process_region] max_df가 없거나 비었음. 지역 {region_name}에 대해 빈 데이터프레임 사용.")
        merged_df_norm = pd.DataFrame()
    else:
        # 'Area' 컬럼 존재/대소문자 변형/공백 표기 방어
        cols_lower = {str(c).strip().lower(): c for c in max_df.columns}
        area_col = cols_lower.get('area')
        if area_col is None:
            print(f"[process_region][WARN] 'Area' 컬럼을 찾지 못함. 현재 컬럼={list(max_df.columns)} → 빈 DF 사용")
            merged_df_norm = pd.DataFrame()
        else:
            merged_df_norm = (
                max_df[max_df[area_col].astype(str).str.strip() == str(norm_region).strip()]
                .reset_index(drop=True)
            )

    print(f'merged_df_norm: {merged_df_norm}')

    if fix_drivers > 0:
        # 고정기사 배정
        df_shipping_region, leftover_driver_df = assign_fixed_drivers(
            df_shipping_region, fix_region_workflow_day_bunny_df, merged_df_norm
        )

        # leftover_all_fix_drivers 누적
        if not leftover_driver_df.empty:
            leftover_driver_df = leftover_driver_df.copy()
            leftover_driver_df["Region"] = region_name
            leftover_all_fix_drivers = pd.concat(
                [leftover_all_fix_drivers, leftover_driver_df], ignore_index=True
            )

    # 미리 driver 컬럼이 없으면 생성
    for col in ["driver_type", "driver_code"]:
        if col not in df_shipping_region.columns:
            df_shipping_region[col] = np.nan

    unassigned_white_groups = (
        df_shipping_region.groupby("group")
        .filter(lambda x: x["driver_type"].isna().all())["group"]
        .unique()
    )

    print("화이트 처리 대상 그룹:", unassigned_white_groups)
    for grp in unassigned_white_groups:
        df_shipping_region = isolate_white_clusters(df_shipping_region, grp, merged_df_norm)
        # 최종 결과 출력: 화이트 처리 후 그룹별 물량
        print(
            "\n[화이트 처리 후 그룹별 물량]\n",
            df_shipping_region.groupby("group")["shipping_uuid"].count(),
        )

    # 5개 이하 클러스터 병합
    df_shipping_region = merge_tiny_clusters(df_shipping_region)  # 기본 min_cluster=5 사용

    print(
            "\n[화이트 최종 병합 후 그룹별 물량]\n",
            df_shipping_region.groupby("group")["shipping_uuid"].count(),
        )

    print(f"{region_name} 처리 완료\n")
    return df_shipping_region, result_gdf, leftover_all_fix_drivers

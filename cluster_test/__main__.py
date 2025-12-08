# ---------------------------------------------------------------------------
# 6) 실제 실행
# ---------------------------------------------------------------------------
if __name__ == "__main__":

    workflow_day_shipping_items_df = workflow_day_shipping_items_df.copy()
    workflow_day_bunny_df = workflow_day_bunny_df.copy()

    workflow_day_shipping_items_df = workflow_day_shipping_items_df.astype(
        {"zipcode": str}
    )
    workflow_day_shipping_items_df["zipcode"] = (
        workflow_day_shipping_items_df["zipcode"].astype(str).str.zfill(5)
    )

    date = workflow_day_bunny_df["Date"].drop_duplicates()
    year, month, day = map(int, date[0].split("-"))

    # BLUE 기사들의 Area 목록 추출
    blue_areas = list(
        workflow_day_bunny_df.loc[workflow_day_bunny_df["Type"] == "BLUE", "Area"]
    )

    if is_weekend(year, month, day):
        df_weekend["region"] = df_weekend["region"].apply(normalize_region)
        chosen_df_weekend = df_weekend[~df_weekend["region"].isin(blue_areas)]

        chosen_zipcode_groups = chosen_df_weekend
        chosen_zipcode_groups.reset_index(drop=True, inplace=True)

    else:
        df_regular["region"] = df_regular["region"].apply(normalize_region)
        chosen_df_regular = df_regular[~df_regular["region"].isin(blue_areas)]

        chosen_zipcode_groups = chosen_df_regular
        chosen_zipcode_groups.reset_index(drop=True, inplace=True)

    all_KMeans_dfs, leftover_drivers = run_clustering(
        zipcode_groups=chosen_zipcode_groups,
        workflow_day_shipping_items_df=workflow_day_shipping_items_df,
        workflow_day_bunny_df=workflow_day_bunny_df,
    )

    # 기사가 부족해 배정되지 않은 지역
    all_KMeans_dfs_left = all_KMeans_dfs[
        (~all_KMeans_dfs["group"].isna()) & (all_KMeans_dfs["driver_type"].isna())
    ].reset_index(drop=True)

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

# ---------------------------------------------------------------------------
# 4) 지역별 처리
# ---------------------------------------------------------------------------
def process_region(
    region_name,
    zipcode_groups,
    df_shipping,
    workflow_day_bunny_df,
    leftover_all_fix_drivers,
):

    print(f"### {region_name} 처리 시작 ###")

    zipcode_groups = zipcode_groups[zipcode_groups['region']==region_name]

    # (2) 그룹화 및 데이터 저장
    result_gdf, df_shipping_region = group_and_map_zipcodes(zipcode_groups, df_shipping)

    # 지역별 bunny 기사 필터링
    region_workflow_day_bunny_df = workflow_day_bunny_df[workflow_day_bunny_df['Area'] == df_shipping_region.iloc[0, 3]].copy()

    # (3) 고정 기사(YELLOW/RAINBOW/ORANGE) & 화이트(WHITE) 기사 분리
    fix_region_workflow_day_bunny_df = region_workflow_day_bunny_df[
        region_workflow_day_bunny_df['Type'].isin(['YELLOW','RAINBOW','ORANGE'])
    ].copy()

    # 버니에게 배정 전 그룹별 물량
    df_shipping_region_group_count=df_shipping_region.groupby('group')['shipping_uuid'].agg('count').reset_index()
    print(f"{region_name} 초기 그룹별 물량\n{df_shipping_region_group_count}")

    fix_drivers = len(fix_region_workflow_day_bunny_df)

    if fix_drivers > 0:
        # 고정기사 배정
        df_shipping_region, leftover_driver_df = assign_fixed_drivers(df_shipping_region, fix_region_workflow_day_bunny_df)

        # leftover_all_fix_drivers 누적
        if not leftover_driver_df.empty:
            leftover_driver_df = leftover_driver_df.copy()
            leftover_driver_df['Region'] = region_name
            leftover_all_fix_drivers = pd.concat([leftover_all_fix_drivers, leftover_driver_df], ignore_index=True)

    # 미리 driver 컬럼이 없으면 생성
    for col in ['driver_type', 'driver_code']:
        if col not in df_shipping_region.columns:
            df_shipping_region[col] = np.nan

    unassigned_white_groups = df_shipping_region.groupby('group') \
        .filter(lambda x: x['driver_type'].isna().all()) \
        ['group'].unique()

    print("화이트 처리 대상 그룹:", unassigned_white_groups)
    for grp in unassigned_white_groups:
        df_shipping_region = isolate_white_clusters(df_shipping_region, grp)
        # 최종 결과 출력: 화이트 처리 후 그룹별 물량
        print("\n[화이트 처리 후 그룹별 물량]\n", df_shipping_region.groupby('group')['shipping_uuid'].count())
        
    print(f"{region_name} 처리 완료\n")
    df_shipping_region_region=df_shipping_region.groupby(['group', 'driver_type'])['shipping_uuid'].agg('count').reset_index()
    print(f"처리 후 최종 물량 및 driver_type:\n {df_shipping_region_region}")
    return df_shipping_region, result_gdf, leftover_all_fix_drivers

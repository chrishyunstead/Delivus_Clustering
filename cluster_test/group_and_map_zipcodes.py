def group_and_map_zipcodes(zipcode_groups, shipping_csv_path):
    
    result_gdf = zipcode_groups

    # 우편번호-그룹 매핑 생성
    zipcode_to_group = {}
    for _, row in result_gdf.iterrows():
        group = row['group_name']
        # 문자열 형태의 zipcodes를 리스트로 변환
        zipcodes_group = ast.literal_eval(row['zipcodes'])
        for zipcode in zipcodes_group:
            zipcode_to_group[zipcode] = group

    # 배송 데이터 로드 및 그룹 매핑
    df_shipping = shipping_csv_path
    df_shipping['group'] = df_shipping['zipcode'].map(zipcode_to_group)
    df_shipping = df_shipping[~df_shipping['group'].isna()]
    
    return result_gdf, df_shipping
# 각 그룹에 물량 집어넣기
# 각 실제 데이터(point)에 대해서 (lat, lng) 거리를 구하고, 가장 가까운 한 개 row의 group을 할당(가장 가까운 데이터의 group에 포함)

def overlap(overlap_df, all_KMeans_dfs_drop):
    
    overlap_df = overlap_df.astype({'zipcode': str})
    overlap_df['zipcode'] = overlap_df['zipcode'].astype(str).str.zfill(5) 

    for col in ['driver_type', 'driver_code', 'cluster_label']:
        if col not in overlap_df.columns:
            overlap_df[col] = np.nan
            
    # 오버랩 데이터를 가장 가까이 있는 데이터의 그룹에 포함시키기
    for i, order_row in overlap_df.iterrows():
        area = order_row["Area"]
        lat_val = order_row["lat"]
        lng_val = order_row["lng"]
        
        
        # 1) Area가 같은 행만 추출
        area_slice = all_KMeans_dfs_drop[all_KMeans_dfs_drop["Area"] == area]
        
        # 2) 해당 지역(Area)에 데이터 자체가 전혀 없는 경우: 미배정 처리
        if area_slice.empty:
            overlap_df.at[i, "driver_type"]  = np.nan
            overlap_df.at[i, "driver_code"]  = np.nan
            overlap_df.at[i, "cluster_label"]  = np.nan
            
            print(f"[INFO] {area} 지역의 주문({order_row['shipping_uuid']})은 같은 지역 데이터가 없어 미배정 처리.")
            continue
        
        # 3) (lat, lng) 거리계산 -> 가장 가까운 group 찾기
        #    여기서는 유클리드로 비교
        area_slice["dist"] = np.sqrt((area_slice["lat"].astype(float) - lat_val)**2 + 
                                     (area_slice["lng"].astype(float) - lng_val)**2)
        
        # 가장 작은 dist를 갖는 row의 인덱스
        min_idx = area_slice["dist"].idxmin()
        nearest_row = area_slice.loc[min_idx]
        
        best_group_driver_type = nearest_row["driver_type"]
        
        # 그룹이 없을 경우 클러스터라벨 및 driver_type 추가하기
        cluster_label = all_KMeans_dfs_drop[all_KMeans_dfs_drop['Area'] == area][['cluster_label']].drop_duplicates()
        cluster_label = cluster_label.iloc[0]

        driver_type = all_KMeans_dfs_drop[all_KMeans_dfs_drop['Area'] == area][['driver_type']].drop_duplicates()
        driver_type = driver_type.iloc[0]
        

        # 혹시 nearest_row 자체에 driver_type이 BLUE로 들어가 있으면 BLUE 처리
        if best_group_driver_type == 'BLUE':
            overlap_df.at[i, "driver_type"]  = driver_type['driver_type']
            overlap_df.at[i, "driver_code"]  = np.nan
            overlap_df.at[i, "cluster_label"]  = cluster_label['cluster_label']
            
            print(f"[INFO] {area} 지역 주문({order_row['shipping_uuid']}) → 가장 가까운 데이터의 driver_type이 BLUE, BLUE 로 편입.")
            continue
        
        # 4) cluster_label 할당
        overlap_df.at[i, "cluster_label"] = cluster_label['cluster_label']
        
        best_group_cluster_label = nearest_row["cluster_label"]

        # 5) 배정된 그룹의 기사 정보 확인
        group_slice = all_KMeans_dfs_drop[
            (all_KMeans_dfs_drop["Area"] == area) & 
            (all_KMeans_dfs_drop["cluster_label"] == best_group_cluster_label)
        ]

        unique_drivers = group_slice[["driver_type", "driver_code", "cluster_label"]].drop_duplicates()
        
        if len(unique_drivers) == 1:
            # 기사정보가 유일하게 한 명이면 그대로 배정
            row_driver = unique_drivers.iloc[0]
            overlap_df.at[i, "driver_type"]  = row_driver["driver_type"]
            overlap_df.at[i, "driver_code"]  = row_driver["driver_code"]
            overlap_df.at[i, "cluster_label"]  = row_driver["cluster_label"]
        else:
            # 기사가 여러 명이거나 아예 없다면 -> 일단 미배정
            overlap_df.at[i, "driver_type"]  = np.nan
            overlap_df.at[i, "driver_code"]  = np.nan
            overlap_df.at[i, "cluster_label"]  = np.nan
        
        print(f"[INFO] {area} 지역 주문({order_row['shipping_uuid']}) → 가장 가까운 데이터의 cluster_label=[{best_group_cluster_label}] 배정 완료")
    
    # 기존 all_KMeans_dfs + overlap_df를 합쳐 최종 반환
    all_KMeans_dfs_plus_overlap = pd.concat([all_KMeans_dfs_drop, overlap_df], ignore_index=True)

    return all_KMeans_dfs_plus_overlap
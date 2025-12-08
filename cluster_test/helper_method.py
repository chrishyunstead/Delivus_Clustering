# 헬퍼 함수


# 1) 그룹별 중심 좌표 재계산
def recalc_group_centroids(df, group_col="group", lat_col="lat", lng_col="lng"):
    """
    DataFrame 내 group별 위경도(lat, lng) 평균을 구하여 centroid(중심좌표) 정보를 dict 형태로 반환
    """
    centroids = (
        df.groupby(group_col)
        .apply(lambda sub_df: (sub_df[lat_col].mean(), sub_df[lng_col].mean()))
        .to_dict()
    )
    return centroids


# 2) 날짜 반환
def is_weekend(year, month, day):
    return calendar.weekday(year, month, day) >= 5


# 3) 버니스케줄과 물품데이터 매핑
def normalize_region(region):
    """
    workflow_day_bunny_df의 Area는 대부분 뒤에 '구'나 '시'가 없는 형식임.
    단, '일산서구', '일산동구'는 예외로 그대로 사용.
    """
    if isinstance(region, list):
        return [normalize_region(r) for r in region]

    if region in [
        "일산서구",
        "일산동구",
        "중구",
        "인천동구",
        "인천서구",
        "인천중구",
        "인천연수구",
        "인천남동구",
        "인천연수구",
    ]:
        return region
    if region.endswith("구") or region.endswith("시"):
        return region[:-1]
    return region


# 4) Kmeans 함수
def split_group_kmeans_2clusters(df, group):
    """
    df에서 특정 group에 속한 주문들을 K-Means(n_clusters=2)로 분할하고,
    클러스터 라벨과 각 클러스터의 주문 건수를 반환합니다.
    반환값: (grp_orders, cluster_counts, label_a, count_a, label_b, count_b)
    """
    grp_orders = df[df["group"] == group].copy()
    grp_orders["lat_rad"] = grp_orders["lat"].apply(radians)
    grp_orders["lng_rad"] = grp_orders["lng"].apply(radians)
    coords = grp_orders[["lat_rad", "lng_rad"]].to_numpy()
    if len(coords) < 2:
        return grp_orders, {}, None, 0, None, 0
    km = KMeans(n_clusters=2, init="k-means++", random_state=42, n_init=10)
    cluster_labels = km.fit_predict(coords)
    grp_orders["cluster"] = cluster_labels
    cluster_counts = grp_orders["cluster"].value_counts()
    if len(cluster_counts) < 2:
        label_a = cluster_counts.index[0]
        return grp_orders, cluster_counts, label_a, cluster_counts.iloc[0], None, 0
    label_a = cluster_counts.index[0]
    count_a = cluster_counts.iloc[0]
    label_b = cluster_counts.index[1]
    count_b = cluster_counts.iloc[1]
    return grp_orders, cluster_counts, label_a, count_a, label_b, count_b


# 5) 주문 건 이동
def move_orders(df, indices, target_group, clear_driver=True):
    if clear_driver:
        df.loc[indices, ["driver_type", "driver_code"]] = np.nan

    df.loc[indices, "group"] = target_group
    print(f"[move_orders] Moved {len(indices)} orders to group [{target_group}].")
    print(df.groupby("group")["shipping_uuid"].count())


# 6) 버니 배정
def assign_driver_to_group(
    df, group_name, driver_df, assigned_idx, leftover_count, label=""
):
    """
    driver_df의 assigned_idx번째 기사를 df에서 group_name에 배정.
    배정 후 assigned_idx / leftover_count 갱신.

    반환: (df, assigned_idx, leftover_count)
    """
    if assigned_idx >= len(driver_df):
        print(f"[assign_driver_to_group] 더 이상 {label} 드라이버가 없습니다.")
        return df, assigned_idx, leftover_count

    driver = driver_df.iloc[assigned_idx]
    df.loc[df["group"] == group_name, "driver_type"] = driver["Type"]

    assigned_idx += 1
    leftover_count -= 1

    return df, assigned_idx, leftover_count


# 7) 범위
def in_range(x, low, high):
    return (x >= low) and (x < high)


def min_dist_to_group(row, group_points):
    try:
        lat = float(row["lat"])
        lng = float(row["lng"])
    except (ValueError, TypeError, KeyError):
        return np.nan

    valid_points = group_points.dropna(subset=["lat", "lng"]).copy()
    if valid_points.empty:
        return np.nan

    try:
        dists = (group_points["lat"].astype(float) - lat) ** 2 + (
            group_points["lng"].astype(float) - lng
        ) ** 2
        return np.sqrt(dists.min())
    except Exception:
        return np.nan


# 화이트 배정
# def iterative_move_cluster_A_to_B(
#     group_orders, group_name, cluster_A, cluster_B, max_moves=None, clear_driver=False
# ):
#     moved_count = 0
#     temp_cluster_added = False

#     while True:
#         # 1) cluster_A에 속한 주문(A) 추출
#         A = group_orders[
#             (group_orders["group"] == group_name)
#             & (group_orders["cluster"] == cluster_A)
#         ]
#         if A.empty:
#             break  # 더 이상 옮길 A 없음

#         if max_moves is not None and moved_count >= max_moves:
#             break  # 이동 한도 도달

#         # 2) cluster_B에 속한 주문들의 좌표
#         B_points = group_orders[
#             (group_orders["group"] == group_name)
#             & (group_orders["cluster"] == cluster_B)
#         ][["lat", "lng"]]

#         # 3) "fallback 좌표" 정의
#         #    만약 cluster_B가 비어 있으면, group 전체의 lat,lng 평균을 fallback으로 사용
#         if B_points.empty:
#             group_points = group_orders[group_orders["group"] == group_name][
#                 ["lat", "lng"]
#             ]
#             if group_points.empty:
#                 # group 내에 주문이 전혀 없는 경우 → 이동 불가
#                 break
#             # group 전체 lat,lng 평균
#             lat_mean = group_points["lat"].mean()
#             lng_mean = group_points["lng"].mean()
#             # cluster_B가 생기기 전까지 임시 점 1개를 "fallback_points"로 사용
#             fallback_points = pd.DataFrame(
#                 [[lat_mean, lng_mean]], columns=["lat", "lng"]
#             )
#             use_points = fallback_points
#         else:
#             use_points = B_points  # 정상 로직: cluster_B가 존재하므로 이걸 기준

#         # 4) A 각각에 대해 use_points와의 거리 계산
#         A = A.copy()
#         A["dist_to_B"] = A.apply(lambda row: min_dist_to_group(row, use_points), axis=1)

#         # dist가 가장 작은 행
#         idx_to_move = A["dist_to_B"].idxmin()
#         min_val = A.loc[idx_to_move, "dist_to_B"]
#         if pd.isna(min_val):
#             # 거리 계산이 NaN → 이동 불가
#             break

#         # 5) 이동 실행
#         if clear_driver:
#             group_orders.loc[idx_to_move, ["driver_type", "driver_code"]] = np.nan
#         group_orders.loc[idx_to_move, "cluster"] = cluster_B

#         moved_count += 1

#     return group_orders, moved_count

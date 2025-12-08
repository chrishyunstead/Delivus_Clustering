def assign_fixed_drivers(df_shipping_region, fix_region_workflow_day_bunny_df):
    for col in ["driver_type", "driver_code"]:
        if col not in df_shipping_region.columns:
            df_shipping_region[col] = np.nan

    group_centroids = recalc_group_centroids(df_shipping_region)
    # 1) 버니 우선순위 매핑 및 정렬
    type_priority = {"YELLOW": 1, "RAINBOW": 2, "ORANGE": 3}
    fix_region_workflow_day_bunny_df["type_prio"] = fix_region_workflow_day_bunny_df[
        "Type"
    ].map(type_priority)
    fix_region_workflow_day_bunny_df.sort_values(["type_prio"], inplace=True)

    # 2) Y/R와 ORANGE 드라이버 분리
    non_orange_drivers = fix_region_workflow_day_bunny_df[
        fix_region_workflow_day_bunny_df["Type"] != "ORANGE"
    ]
    orange_drivers = fix_region_workflow_day_bunny_df[
        fix_region_workflow_day_bunny_df["Type"] == "ORANGE"
    ]
    assigned_non_orange = 0
    assigned_orange = 0
    leftover_non_orange = len(non_orange_drivers) - assigned_non_orange
    leftover_orange = len(orange_drivers) - assigned_orange
    # 1차 배정
    # (A) YELLOW/RAINBOW 배정: 그룹 주문 수 40~50건인 그룹
    group_counts = df_shipping_region.groupby("group")["shipping_uuid"].count()
    yellow_rainbow_groups = group_counts[
        (group_counts >= 40) & (group_counts < 50)
    ].index

    print(f"[1차 배정] Y/R driver count: {len(non_orange_drivers)}")
    print(f"[1차 배정] ORANGE driver count: {len(orange_drivers)}")

    for grp in yellow_rainbow_groups:
        if assigned_non_orange >= len(non_orange_drivers):
            break

        # 새 그룹명 예: 기존 grp + "_Y/R"
        new_grp = f"{grp}_Y/R"

        # 주문들을 새 그룹으로 이동 (여기서는 단순히 group만 바꿈)
        indices = df_shipping_region[df_shipping_region["group"] == grp].index
        df_shipping_region.loc[indices, "group"] = new_grp

        # 드라이버 배정 (driver_type, driver_code 설정)
        df_shipping_region, assigned_non_orange, leftover_non_orange = (
            assign_driver_to_group(
                df_shipping_region,
                new_grp,
                non_orange_drivers,
                assigned_non_orange,
                leftover_non_orange,
                label="Y/R",
            )
        )
        print(f"[1차 배정] Group {grp} reassigned as {new_grp} and driver assigned.")
        # 그룹 중심점 재계산 (필요 시)
        group_centroids = recalc_group_centroids(df_shipping_region)
        if leftover_non_orange <= 0:
            print("[Y/R 1차 배정] 더 이상 Y/R 버니가 없습니다. 배정 중단.")
            break

    # 남은 Y/R 드라이버 수
    print(f"[1차 배정] Leftover Y/R drivers: {leftover_non_orange}")

    # (B) ORANGE 배정: 그룹 주문 수 20~31건인 그룹
    group_counts = df_shipping_region.groupby("group")["shipping_uuid"].count()
    orange_groups = group_counts[(group_counts >= 20) & (group_counts <= 31)].index

    for grp in orange_groups:
        if assigned_orange >= len(orange_drivers):
            break

        new_grp = f"{grp}_O"
        indices = df_shipping_region[df_shipping_region["group"] == grp].index
        df_shipping_region.loc[indices, "group"] = new_grp

        df_shipping_region, assigned_orange, leftover_orange = assign_driver_to_group(
            df_shipping_region,
            new_grp,
            orange_drivers,
            assigned_orange,
            leftover_orange,
            label="ORANGE",
        )
        print(f"[1차 배정] Group {grp} reassigned as {new_grp} and driver assigned.")
        # 그룹 중심점 재계산 (필요 시)
        group_centroids = recalc_group_centroids(df_shipping_region)
        if leftover_orange <= 0:
            print("[ORANGE 1차 배정] 더 이상 오렌지 버니가 없습니다. 재배정 중단.")
            break

    # 남은 ORANGE 드라이버 수
    print(f"[1차 배정] Leftover ORANGE drivers: {leftover_orange}")

    # ---------------------------------------------------------------------------
    # 2차 배정: Y/R 2차 재배정 (주문 수 60건 이상인 그룹 대상)
    yr_group_counter = {}
    stop_all = False
    print("### [Y/R 2차 재배정] ###")

    for _ in range(len(non_orange_drivers)):
        if leftover_non_orange <= 0:
            stop_all = True
            break

        unassigned_df = df_shipping_region[df_shipping_region["driver_type"].isna()]
        group_counts = unassigned_df.groupby("group")["shipping_uuid"].count()

        # 60건 이상인 그룹을 대상으로 처리
        extra_unassigned_max_groups = group_counts[group_counts >= 60].index.tolist()
        print(f"배정되지 않은 그룹 {extra_unassigned_max_groups}")
        print(f"[Y/R 2차 재배정] 남은 Y/R 버니: {leftover_non_orange}명")

        if not extra_unassigned_max_groups:
            break

        for grp in extra_unassigned_max_groups:
            if leftover_non_orange <= 0:
                stop_all = True
                break

            # 스택(LIFO)으로 관리
            group_stack = [grp]

            while group_stack and not stop_all:
                current_group = group_stack.pop()

                # 해당 group의 실제 주문 수 확인
                current_count = df_shipping_region[
                    df_shipping_region["group"] == current_group
                ].shape[0]
                if current_count < 60:
                    # 60건 미만이면 스킵
                    continue

                print(
                    f"[Y/R 2차 재배정] 그룹 [{current_group}] (주문수: {current_count})에서 클러스터 추출 시도"
                )

                grp_orders, cluster_counts_res, label_a, count_a, label_b, count_b = (
                    split_group_kmeans_2clusters(df_shipping_region, current_group)
                )

                # 클러스터가 2개 미만이면 스킵
                if len(cluster_counts_res) < 2 or label_b is None:
                    continue

                # 더 편하게 쓰기 위해 local 변수에 재저장
                cluster_counts = cluster_counts_res
                # 큰/작은 클러스터 식별
                if cluster_counts.iloc[0] <= cluster_counts.iloc[1]:
                    smaller_cluster = cluster_counts.index[0]  # ex) label_a
                    larger_cluster = cluster_counts.index[1]  # ex) label_b
                else:
                    smaller_cluster = cluster_counts.index[1]
                    larger_cluster = cluster_counts.index[0]

                print(
                    f"  → 그룹 [{current_group}] 클러스터 결과: "
                    f"클러스터 {label_a} ({cluster_counts[label_a]}건), "
                    f"클러스터 {label_b} ({cluster_counts[label_b]}건)"
                )

                # 클러스터별 인덱스
                indices_a = grp_orders[grp_orders["cluster"] == label_a].index
                indices_b = grp_orders[grp_orders["cluster"] == label_b].index

                if 55 < count_a < 60 and count_b >= 60:
                    new_group_a = f"{current_group}_R_{label_a}"
                    new_group_b = f"{current_group}_SPLIT_{label_b}"

                    # 그룹 이동 (driver_type은 초기화하지 않고 그대로 유지 → clear_driver=False)
                    move_orders(
                        df_shipping_region, indices_a, new_group_a, clear_driver=False
                    )
                    move_orders(
                        df_shipping_region, indices_b, new_group_b, clear_driver=False
                    )

                    print(
                        f"→ 클러스터{label_a}: remain, 클러스터{label_b}: stack에 재추가 (다시 클러스터링)"
                    )

                    group_stack.append(new_group_b)
                    continue

                if 55 < count_b < 60 and count_a >= 60:
                    new_group_b = f"{current_group}_R_{label_b}"
                    new_group_a = f"{current_group}_SPLIT_{label_a}"

                    move_orders(
                        df_shipping_region, indices_b, new_group_b, clear_driver=False
                    )
                    move_orders(
                        df_shipping_region, indices_a, new_group_a, clear_driver=False
                    )

                    print(
                        f"→ 클러스터{label_b}: remain, 클러스터{label_a}: stack에 재추가 (다시 클러스터링)"
                    )

                    group_stack.append(new_group_a)
                    continue

                if count_a >= 60 and count_b >= 60:
                    new_group_a = f"{current_group}_SPLIT_{label_a}"
                    new_group_b = f"{current_group}_SPLIT_{label_b}"

                    move_orders(
                        df_shipping_region, indices_a, new_group_a, clear_driver=False
                    )
                    move_orders(
                        df_shipping_region, indices_b, new_group_b, clear_driver=False
                    )

                    print(
                        f"→ 두 클러스터가 모두 60건 이상. 새로운 그룹 {new_group_a}, {new_group_b} → stack에 추가"
                    )

                    group_stack.append(new_group_a)
                    group_stack.append(new_group_b)
                    continue

                if 40 <= count_a <= 55 and count_b >= 60:
                    new_YR_group_a = f"{current_group}_Y/R_{label_a}"
                    new_big_grp = f"{current_group}_remain"

                    # 그룹 이동
                    move_orders(
                        df_shipping_region,
                        indices_a,
                        new_YR_group_a,
                        clear_driver=False,
                    )
                    move_orders(
                        df_shipping_region, indices_b, new_big_grp, clear_driver=False
                    )

                    if assigned_non_orange < len(non_orange_drivers):
                        driver_before = non_orange_drivers.iloc[assigned_non_orange]
                        df_shipping_region, assigned_non_orange, leftover_non_orange = (
                            assign_driver_to_group(
                                df_shipping_region,
                                new_YR_group_a,
                                non_orange_drivers,
                                assigned_non_orange,
                                leftover_non_orange,
                                label="Y/R",
                            )
                        )
                        new_count = len(indices_a)  # 대략적인 건수
                        print(
                            f"[Y/R 2차 재배정] 그룹[{new_YR_group_a}] (약 {new_count}건) → [{driver_before['Type']}] 배정"
                        )

                        group_centroids = recalc_group_centroids(df_shipping_region)
                        if leftover_non_orange <= 0:
                            print(
                                "[Y/R 2차 재배정] 더 이상 Y/R 버니가 없습니다. 배정 중단."
                            )
                            break
                    else:
                        print(
                            "[Y/R 2차 재배정] 배정 가능한 Y/R 버니가 더 이상 없습니다."
                        )
                        break

                    print(
                        f"클러스터 {label_a} 그룹 물량 40~55건이므로 [{new_YR_group_a}]에 배정"
                    )
                    group_stack.append(new_big_grp)
                    continue

                if 40 <= count_b <= 55 and count_a >= 60:
                    new_YR_group_b = f"{current_group}_Y/R_{label_b}"
                    new_big_grp = f"{current_group}_remain"

                    move_orders(
                        df_shipping_region,
                        indices_b,
                        new_YR_group_b,
                        clear_driver=False,
                    )
                    move_orders(
                        df_shipping_region, indices_a, new_big_grp, clear_driver=False
                    )

                    if assigned_non_orange < len(non_orange_drivers):
                        driver_before = non_orange_drivers.iloc[assigned_non_orange]
                        df_shipping_region, assigned_non_orange, leftover_non_orange = (
                            assign_driver_to_group(
                                df_shipping_region,
                                new_YR_group_b,
                                non_orange_drivers,
                                assigned_non_orange,
                                leftover_non_orange,
                                label="Y/R",
                            )
                        )
                        new_count = len(indices_b)
                        print(
                            f"[Y/R 2차 재배정] 그룹[{new_YR_group_b}] (약 {new_count}건) → [{driver_before['Type']}] 배정"
                        )

                        group_centroids = recalc_group_centroids(df_shipping_region)
                        if leftover_non_orange <= 0:
                            print(
                                "[Y/R 2차 재배정] 더 이상 Y/R 버니가 없습니다. 배정 중단."
                            )
                            break
                    else:
                        print(
                            "[Y/R 2차 재배정] 배정 가능한 Y/R 버니가 더 이상 없습니다."
                        )
                        break

                    print(
                        f"클러스터 {label_b} 그룹 물량 40~55건이므로 [{new_YR_group_b}]에 배정"
                    )
                    group_stack.append(new_big_grp)
                    continue

                if (40 <= count_a <= 55) and (40 <= count_b <= 55):
                    new_YR_group_a = f"{current_group}_Y/R_{label_a}"
                    new_YR_group_b = f"{current_group}_Y/R_{label_b}"

                    move_orders(
                        df_shipping_region,
                        indices_a,
                        new_YR_group_a,
                        clear_driver=False,
                    )
                    move_orders(
                        df_shipping_region,
                        indices_b,
                        new_YR_group_b,
                        clear_driver=False,
                    )

                    new_count_a = len(indices_a)
                    new_count_b = len(indices_b)

                    if assigned_non_orange < len(non_orange_drivers):
                        driver_before = non_orange_drivers.iloc[assigned_non_orange]
                        df_shipping_region, assigned_non_orange, leftover_non_orange = (
                            assign_driver_to_group(
                                df_shipping_region,
                                new_YR_group_a,
                                non_orange_drivers,
                                assigned_non_orange,
                                leftover_non_orange,
                                label="Y/R",
                            )
                        )
                        print(
                            f"[Y/R 2차 재배정] 그룹[{new_YR_group_a}] (약 {new_count_a}건) {driver_before['Type']} 배정"
                        )

                        group_centroids = recalc_group_centroids(df_shipping_region)
                        if leftover_non_orange <= 0:
                            print(
                                "[Y/R 2차 재배정] 더 이상 Y/R 버니가 없습니다. 배정 중단."
                            )
                            break
                    else:
                        print(
                            "[Y/R 2차 재배정] 배정 가능한 Y/R 버니가 더 이상 없습니다."
                        )
                        break

                    if assigned_non_orange < len(non_orange_drivers):
                        driver_before = non_orange_drivers.iloc[assigned_non_orange]
                        df_shipping_region, assigned_non_orange, leftover_non_orange = (
                            assign_driver_to_group(
                                df_shipping_region,
                                new_YR_group_b,
                                non_orange_drivers,
                                assigned_non_orange,
                                leftover_non_orange,
                                label="Y/R",
                            )
                        )
                        print(
                            f"[Y/R 2차 재배정] 그룹[{new_YR_group_b}] (약 {new_count_b}건) {driver_before['Type']} 배정"
                        )

                        group_centroids = recalc_group_centroids(df_shipping_region)
                        if leftover_non_orange <= 0:
                            print(
                                "[Y/R 2차 재배정] 더 이상 Y/R 버니가 없습니다. 배정 중단."
                            )
                            break
                    else:
                        print(
                            "[Y/R 2차 재배정] 배정 가능한 Y/R 버니가 더 이상 없습니다."
                        )
                        break

                    leftover_non_orange = len(non_orange_drivers) - assigned_non_orange
                    print(f"[Y/R 2차 재배정] 남은 Y/R 버니: {leftover_non_orange}명")
                    continue

                if 40 <= count_a <= 55 and 20 <= count_b < 40:
                    new_YR_group_a = f"{current_group}_Y/R_{label_a}"
                    new_group_b = f"{current_group}_R_{label_b}"

                    move_orders(
                        df_shipping_region,
                        indices_a,
                        new_YR_group_a,
                        clear_driver=False,
                    )
                    move_orders(
                        df_shipping_region, indices_b, new_group_b, clear_driver=False
                    )

                    if assigned_non_orange < len(non_orange_drivers):
                        driver_before = non_orange_drivers.iloc[assigned_non_orange]
                        df_shipping_region, assigned_non_orange, leftover_non_orange = (
                            assign_driver_to_group(
                                df_shipping_region,
                                new_YR_group_a,
                                non_orange_drivers,
                                assigned_non_orange,
                                leftover_non_orange,
                                label="Y/R",
                            )
                        )
                        print(
                            f"[Y/R 2차 재배정] 그룹[{new_YR_group_a}] (약 {len(indices_a)}건) {driver_before['Type']} 배정"
                        )

                        group_centroids = recalc_group_centroids(df_shipping_region)
                        if leftover_non_orange <= 0:
                            print(
                                "[Y/R 2차 재배정] 더 이상 Y/R 버니가 없습니다. 배정 중단."
                            )
                            break
                    else:
                        print(
                            "[Y/R 2차 재배정] 배정 가능한 Y/R 버니가 더 이상 없습니다."
                        )
                        break

                    leftover_non_orange = len(non_orange_drivers) - assigned_non_orange
                    print(f"[Y/R 2차 재배정] 남은 Y/R 버니: {leftover_non_orange}명")
                    continue

                if 40 <= count_b <= 55 and 20 <= count_a < 40:
                    new_YR_group_b = f"{current_group}_Y/R_{label_b}"
                    new_group_a = f"{current_group}_R_{label_a}"

                    move_orders(
                        df_shipping_region,
                        indices_b,
                        new_YR_group_b,
                        clear_driver=False,
                    )
                    move_orders(
                        df_shipping_region, indices_a, new_group_a, clear_driver=False
                    )

                    if assigned_non_orange < len(non_orange_drivers):
                        driver_before = non_orange_drivers.iloc[assigned_non_orange]
                        df_shipping_region, assigned_non_orange, leftover_non_orange = (
                            assign_driver_to_group(
                                df_shipping_region,
                                new_YR_group_b,
                                non_orange_drivers,
                                assigned_non_orange,
                                leftover_non_orange,
                                label="Y/R",
                            )
                        )
                        print(
                            f"[Y/R 2차 재배정] 그룹[{new_YR_group_b}] (약 {len(indices_b)}건) → [{driver_before['Type']}] 배정"
                        )
                        group_centroids = recalc_group_centroids(df_shipping_region)
                        if leftover_non_orange <= 0:
                            print(
                                "[Y/R 2차 재배정] 더 이상 Y/R 버니가 없습니다. 배정 중단."
                            )
                            break
                    else:
                        print(
                            "[Y/R 2차 재배정] 배정 가능한 Y/R 버니가 더 이상 없습니다."
                        )
                        break

                    leftover_non_orange = len(non_orange_drivers) - assigned_non_orange
                    print(f"[Y/R 2차 재배정] 남은 Y/R 버니: {leftover_non_orange}명")
                    continue

                if leftover_non_orange <= 0:
                    print("더 이상 Y/R 버니가 없습니다.")
                    stop_all = True
                    break

                current = cluster_counts[larger_cluster]
                if current < 40:
                    deficit = 40 - current
                    print(f"  → 부족: {deficit}건 필요")

                    # smaller 클러스터 주문들
                    smaller_orders = grp_orders[
                        grp_orders["cluster"] == smaller_cluster
                    ].copy()

                    larger_points = grp_orders[grp_orders["cluster"] == larger_cluster][
                        ["lat", "lng"]
                    ]
                    smaller_orders["dist_to_larger"] = smaller_orders.apply(
                        lambda row: min_dist_to_group(row, larger_points), axis=1
                    )
                    smaller_orders.sort_values("dist_to_larger", inplace=True)
                    indices_to_move = smaller_orders.index[:deficit]

                    print(
                        f"  → {deficit}건을 smaller 클러스터에서 larger 클러스터로 이동"
                    )
                    # driver 컬럼 초기화 후 이동
                    move_orders(
                        df_shipping_region,
                        indices_to_move,
                        current_group,
                        clear_driver=True,
                    )
                    grp_orders.loc[indices_to_move, "cluster"] = larger_cluster

                elif current > 40:
                    surplus = current - 40
                    print(f"  → 초과: {surplus}건 제거 필요")

                    larger_orders = grp_orders[
                        grp_orders["cluster"] == larger_cluster
                    ].copy()
                    smaller_points = grp_orders[
                        grp_orders["cluster"] == smaller_cluster
                    ][["lat", "lng"]]

                    larger_orders["dist_to_small"] = larger_orders.apply(
                        lambda row: min_dist_to_group(row, smaller_points), axis=1
                    )
                    larger_orders.sort_values("dist_to_small", inplace=True)
                    indices_to_move = larger_orders.index[:surplus]

                    print(f"  → {surplus}건을 큰 클러스터에서 작은 클러스터로 이동")
                    move_orders(
                        df_shipping_region,
                        indices_to_move,
                        current_group,
                        clear_driver=True,
                    )
                    grp_orders.loc[indices_to_move, "cluster"] = smaller_cluster

                # 다시 갱신된 클러스터 수 체크(실제로는 df_shipping_region 변경)
                new_counts_ = grp_orders["cluster"].value_counts()
                new_larger_count = new_counts_.get(larger_cluster, 0)
                print(
                    f"  → 조정 후: 큰 클러스터 {larger_cluster} 주문수: {new_larger_count} (목표:40)"
                )

                # 만약 정확히 40이 됐다면 → Y/R 배정
                if new_larger_count == 40:
                    base_name = current_group.split("_cluster")[0]
                    yr_group_counter.setdefault(base_name, 0)
                    yr_group_counter[base_name] += 1

                    new_grp_label_large = (
                        f"{base_name}_cluster_Y/R_{yr_group_counter[base_name]}"
                    )
                    new_grp_label_small = f"{current_group}_remaining"

                    indices_large = grp_orders[
                        grp_orders["cluster"] == larger_cluster
                    ].index
                    indices_small = grp_orders[
                        grp_orders["cluster"] == smaller_cluster
                    ].index

                    # 그룹 이동
                    move_orders(
                        df_shipping_region,
                        indices_large,
                        new_grp_label_large,
                        clear_driver=False,
                    )
                    move_orders(
                        df_shipping_region,
                        indices_small,
                        new_grp_label_small,
                        clear_driver=False,
                    )

                    if assigned_non_orange < len(non_orange_drivers):
                        driver_before = non_orange_drivers.iloc[assigned_non_orange]
                        df_shipping_region, assigned_non_orange, leftover_non_orange = (
                            assign_driver_to_group(
                                df_shipping_region,
                                new_grp_label_large,
                                non_orange_drivers,
                                assigned_non_orange,
                                leftover_non_orange,
                                label="Y/R",
                            )
                        )
                        print(
                            f"[Y/R 2차 재배정] 그룹[{new_grp_label_large}] (약 {new_larger_count}건) → [{driver_before['Type']}] 배정"
                        )

                        group_centroids = recalc_group_centroids(df_shipping_region)
                        if leftover_non_orange <= 0:
                            print(
                                "[Y/R 2차 재배정] 더 이상 Y/R 버니가 없습니다. 배정 중단."
                            )
                            break
                    else:
                        print(
                            "[Y/R 2차 재배정] 배정 가능한 Y/R 버니가 더 이상 없습니다."
                        )
                        break

                print(
                    "[Y/R 2차 재배정] 후 그룹별 물량:\n",
                    df_shipping_region.groupby("group")["shipping_uuid"].count(),
                )

                if leftover_non_orange <= 0:
                    break

            if stop_all:
                break

        leftover_non_orange = len(non_orange_drivers) - assigned_non_orange
        print(f"[Y/R 2차 재배정] 남은 Y/R 버니: {leftover_non_orange}명")

        if stop_all:
            break

    print("[Y/R 2차 재배정] 로직 완료 or 버니 부족")

    # ---------------------------------------------------------------------------
    # 3차 배정: Y/R 3차 재배정 (Assign Y/R drivers to groups with 40~55 orders left unassigned)
    print("### [Y/R 3차 배정] ###")
    for _ in range(len(non_orange_drivers)):
        if leftover_non_orange <= 0:
            print("[3차 배정] No leftover Y/R drivers. Terminating.")
            break
        unassigned_df = df_shipping_region[df_shipping_region["driver_type"].isna()]
        unassigned_group_counts = unassigned_df.groupby("group")[
            "shipping_uuid"
        ].count()
        y_r_groups = unassigned_group_counts[
            (unassigned_group_counts >= 40) & (unassigned_group_counts <= 55)
        ].index.tolist()
        print(f"[3차 배정] Unassigned groups: {y_r_groups}")

        for grp in y_r_groups:
            if leftover_non_orange <= 0:
                print(
                    "[3차 배정] No leftover Y/R drivers in 40~55 groups. Terminating."
                )
                break
            new_grp_label = f"{grp}_Y/R"
            indices = df_shipping_region[df_shipping_region["group"] == grp].index
            df_shipping_region.loc[indices, "group"] = new_grp_label
            driver = non_orange_drivers.iloc[assigned_non_orange]
            df_shipping_region.loc[
                df_shipping_region["group"] == new_grp_label, "driver_type"
            ] = driver["Type"]
            print(
                f"[3차 배정] Group {new_grp_label} (orders: {unassigned_group_counts[grp]}) assigned to Y/R driver {driver['uuid']}."
            )
            assigned_non_orange += 1
            leftover_non_orange = len(non_orange_drivers) - assigned_non_orange
            group_centroids = recalc_group_centroids(df_shipping_region)
            print(
                "[3차 배정] Updated group counts:\n",
                df_shipping_region.groupby("group")["shipping_uuid"].count(),
            )
            if leftover_non_orange <= 0:
                print("[Y/R 3차 재배정] 더 이상 Y/R 버니가 없습니다. 배정 중단.")
                break
        leftover_non_orange = len(non_orange_drivers) - assigned_non_orange
        print(f"[3차 배정] Leftover Y/R drivers: {leftover_non_orange}")

    # ---------------------------------------------------------------------------
    # 4차 배정: Y/R 4차 재배정
    print("### [Y/R 4차 재배정] ###")
    for _ in range(len(non_orange_drivers)):
        if leftover_non_orange <= 0:
            print("남은 버니 부족으로 종료")
            break
        unassigned_groups = df_shipping_region[
            df_shipping_region["driver_type"].isna()
        ]["group"].unique()
        if len(unassigned_groups) == 0:
            print("[Y/R 4차 재배정] 배정되지 않은 그룹이 없습니다.")
            break
        unassigned_group_counts = (
            df_shipping_region[df_shipping_region["group"].isin(unassigned_groups)]
            .groupby("group")["shipping_uuid"]
            .count()
        )

        unassigned_max_group = unassigned_group_counts.idxmax()
        print(
            f"선택된 unassigned_max_group (물량 많은 그룹): {unassigned_max_group} (물량: {unassigned_group_counts[unassigned_max_group]}건)"
        )

        if unassigned_max_group in group_centroids:
            unassigned_max_group_centroid = group_centroids[unassigned_max_group]
        else:
            orders = df_shipping_region[
                df_shipping_region["group"] == unassigned_max_group
            ]
            unassigned_max_group_centroid = (orders["lat"].mean(), orders["lng"].mean())
            group_centroids[unassigned_max_group] = unassigned_max_group_centroid

        unassigned_group_orders = df_shipping_region[
            df_shipping_region["group"] == unassigned_max_group
        ]
        plus_candidate_groups = [
            g for g in group_centroids.keys() if g != unassigned_max_group
        ]

        if plus_candidate_groups:
            distances = {
                g: np.sqrt(
                    (unassigned_max_group_centroid[0] - group_centroids[g][0]) ** 2
                    + (unassigned_max_group_centroid[1] - group_centroids[g][1]) ** 2
                )
                for g in plus_candidate_groups
            }
            nearest_group = min(distances, key=distances.get)
            print(f"unassigned_max_group 과 가장 가까운 그룹: {nearest_group}")

            nearest_orders = df_shipping_region[
                df_shipping_region["group"] == nearest_group
            ]
            nearest_driver_type = (
                nearest_orders["driver_type"].iloc[0]
                if not nearest_orders.empty
                else None
            )
            print(f"근접 그룹 {nearest_group}의 driver_type: {nearest_driver_type}")

            if nearest_group not in group_centroids:
                orders_ng = df_shipping_region[
                    df_shipping_region["group"] == nearest_group
                ]
                group_centroids[nearest_group] = (
                    orders_ng["lat"].mean(),
                    orders_ng["lng"].mean(),
                )

            volume = unassigned_group_counts[unassigned_max_group]
            nearest_volume = nearest_orders["shipping_uuid"].count()

            if pd.isna(nearest_driver_type):
                print(
                    f"근접 그룹 {nearest_group}의 driver_type이 null이므로, {unassigned_max_group}의 물량이 40이 될 때까지 데이터를 이동합니다."
                )
                if volume < 40:
                    temp = nearest_orders.copy()
                    unassigned_points = unassigned_group_orders[["lat", "lng"]]
                    # 여기서는 거리 계산을 위한 새로운 컬럼 "dist"를 생성
                    temp["dist"] = temp.apply(
                        lambda r: min_dist_to_group(r, unassigned_points), axis=1
                    )

                    temp.sort_values("dist", inplace=True)
                    needed = 40 - volume
                    available = nearest_volume - 20  # 이동 가능한 최대 주문 수
                    move_count = min(needed, available)
                    indices_to_move = temp.index[:move_count]  # 직접 인덱스 선택
                    if needed > available:
                        print(
                            "이동할 데이터가 없으므로, [Y/R 4차 재배정]을 종료합니다."
                        )
                        break

                    move_orders(
                        df_shipping_region,
                        indices_to_move,
                        unassigned_max_group,
                        clear_driver=True,
                    )
                    unassigned_max_group_volume = df_shipping_region[
                        df_shipping_region["group"] == unassigned_max_group
                    ]["shipping_uuid"].count()
                    print(
                        f"→ 이동 후 {unassigned_max_group}의 물량: {unassigned_max_group_volume}건"
                    )
                    if unassigned_max_group_volume >= 40:
                        if assigned_non_orange < len(non_orange_drivers):
                            driver = non_orange_drivers.iloc[assigned_non_orange]
                            df_shipping_region.loc[
                                df_shipping_region["group"] == unassigned_max_group,
                                "driver_type",
                            ] = driver["Type"]
                            new_name = f"{unassigned_max_group}_Y/R"
                            df_shipping_region.loc[
                                df_shipping_region["group"] == unassigned_max_group,
                                "group",
                            ] = new_name

                            (
                                df_shipping_region,
                                assigned_non_orange,
                                leftover_non_orange,
                            ) = assign_driver_to_group(
                                df_shipping_region,
                                new_name,
                                non_orange_drivers,
                                assigned_non_orange,
                                leftover_non_orange,
                                label="Y/R",
                            )
                            print(
                                f"[Y/R 4차 재배정] 그룹({new_name})에 {driver['Type']} 배정."
                            )
                            group_centroids = recalc_group_centroids(df_shipping_region)
                            if leftover_non_orange <= 0:
                                print(
                                    "[Y/R 4차 재배정] 더 이상 Y/R 버니가 없습니다. 배정 중단."
                                )
                                break
                        else:
                            print("[Y/R 4차 재배정] 배정 가능한 Y/R 버니 없음.")
                            break
                    else:
                        print(
                            f"이동할 수 있는 주문이 부족 (필요: {needed}, 이동 가능: {move_count}) → 종료"
                        )
                        break

                elif volume >= 50:
                    temp = unassigned_group_orders.copy()
                    nearest_group_points = df_shipping_region[
                        df_shipping_region["group"] == nearest_group
                    ][["lat", "lng"]]
                    temp["dist"] = temp.apply(
                        lambda row: min_dist_to_group(row, nearest_group_points), axis=1
                    )
                    temp.sort_values("dist", inplace=True)
                    needed = volume - 49
                    indices_to_move = temp.index[:needed]
                    print(
                        f"unassigned_max_group 에 이동할 주문 수: {len(indices_to_move)}"
                    )
                    if len(indices_to_move) == 0:
                        print("이동할 데이터가 없으므로 종료")
                        break

                    move_orders(
                        df_shipping_region,
                        indices_to_move,
                        nearest_group,
                        clear_driver=True,
                    )
                    unassigned_max_group_volume = df_shipping_region[
                        df_shipping_region["group"] == unassigned_max_group
                    ]["shipping_uuid"].count()
                    if unassigned_max_group_volume <= 49:
                        if assigned_non_orange < len(non_orange_drivers):
                            driver = non_orange_drivers.iloc[assigned_non_orange]
                            df_shipping_region.loc[
                                df_shipping_region["group"] == unassigned_max_group,
                                "driver_type",
                            ] = driver["Type"]
                            new_name = f"{unassigned_max_group}_Y/R"
                            (
                                df_shipping_region,
                                assigned_non_orange,
                                leftover_non_orange,
                            ) = assign_driver_to_group(
                                df_shipping_region,
                                new_name,
                                non_orange_drivers,
                                assigned_non_orange,
                                leftover_non_orange,
                                label="Y/R",
                            )
                            print(
                                f"[Y/R 4차 재배정] 그룹({new_name})에 {driver['Type']} 배정."
                            )
                            group_centroids = recalc_group_centroids(df_shipping_region)
                            if leftover_non_orange <= 0:
                                print(
                                    "[Y/R 4차 재배정] 더 이상 Y/R 버니가 없습니다. 배정 중단."
                                )
                                break
                        else:
                            print("[Y/R 4차 재배정] 배정 가능한 Y/R 버니 없음.")
                            break
                    else:
                        print("이동할 데이터가 부족 → 종료")
                        break

            elif nearest_driver_type in ["YELLOW", "RAINBOW"]:
                if nearest_volume < 40:
                    print(
                        f"근접 그룹 {nearest_group}의 주문 수가 40건 미만({nearest_volume}건) → 종료"
                    )
                    break
                else:
                    print(
                        f"근접 그룹 {nearest_group}의 driver_type이 Y/R입니다. {unassigned_max_group}의 물량이 40이 될 때까지 이동 시도합니다."
                    )

                    if volume < 40:
                        needed = 40 - volume
                        available = nearest_volume - 40
                        move_count = min(needed, available)
                        print(
                            f"{unassigned_max_group}: 필요 {needed}건; {nearest_group}에서 최대 {move_count}건 이동 가능 (volume {nearest_volume})."
                        )
                        if needed > available:
                            print("이동할 데이터 부족 → 종료")
                            break
                        temp = nearest_orders.copy()
                        unassigned_points = unassigned_group_orders[["lat", "lng"]]
                        temp["dist"] = temp.apply(
                            lambda r: min_dist_to_group(r, unassigned_points), axis=1
                        )

                        temp.sort_values("dist", inplace=True)
                        indices_to_move = temp.index[:move_count]
                        print(
                            f"[Y/R 4차 재배정] 이동할 주문 수: {len(indices_to_move)}"
                        )
                        if needed > available:
                            print("이동할 데이터 부족 → 종료")
                            break

                        move_orders(
                            df_shipping_region,
                            indices_to_move,
                            unassigned_max_group,
                            clear_driver=True,
                        )
                        unassigned_max_group_volume = df_shipping_region[
                            df_shipping_region["group"] == unassigned_max_group
                        ]["shipping_uuid"].count()
                        if unassigned_max_group_volume >= 40:
                            if assigned_non_orange < len(non_orange_drivers):
                                driver = non_orange_drivers.iloc[assigned_non_orange]
                                df_shipping_region.loc[
                                    df_shipping_region["group"] == unassigned_max_group,
                                    "driver_type",
                                ] = driver["Type"]
                                new_name = f"{unassigned_max_group}_Y/R"
                                (
                                    df_shipping_region,
                                    assigned_non_orange,
                                    leftover_non_orange,
                                ) = assign_driver_to_group(
                                    df_shipping_region,
                                    new_name,
                                    non_orange_drivers,
                                    assigned_non_orange,
                                    leftover_non_orange,
                                    label="Y/R",
                                )
                                print(
                                    f"[Y/R 4차 재배정] 그룹({new_name})에 {driver['Type']} 배정."
                                )
                                group_centroids = recalc_group_centroids(
                                    df_shipping_region
                                )
                                if leftover_non_orange <= 0:
                                    print(
                                        "[Y/R 4차 재배정] 더 이상 Y/R 버니가 없습니다. 배정 중단."
                                    )
                                    break
                            else:
                                print("[Y/R 4차 재배정] 배정 가능한 Y/R 버니 없음.")
                                break
                        else:
                            print(
                                f"이동할 데이터 부족 (필요: {needed}, 이동 가능: {move_count}) → 종료"
                            )
                            break
                    # nearest_group에게 넘기기
                    elif volume >= 56:
                        if nearest_group in group_centroids:
                            nearest_group_centroid = group_centroids[nearest_group]
                        else:
                            nearest_group_orders = df_shipping_region[
                                df_shipping_region["group"] == nearest_group
                            ]
                            nearest_group_centroid = (
                                nearest_group_orders["lat"].mean(),
                                nearest_group_orders["lng"].mean(),
                            )
                            group_centroids[nearest_group] = nearest_group_centroid

                        temp = df_shipping_region[
                            df_shipping_region["group"] == unassigned_max_group
                        ].copy()

                        nearest_group_points = df_shipping_region[
                            df_shipping_region["group"] == nearest_group
                        ][["lat", "lng"]]
                        temp["dist_to_A"] = temp.apply(
                            lambda row: min_dist_to_group(row, nearest_group_points),
                            axis=1,
                        )

                        temp.sort_values("dist_to_A", inplace=True)
                        # 60이상은 위에서 이미 클러스터링 돼서 남아있는 그룹은 50~59
                        needed = volume - 55
                        available = (
                            55 - nearest_volume
                        )  # 이동 가능한 최대 주문 수 => 배정이 안 될 수도 있으므로, 여유 둠.(최후)
                        move_count = min(needed, available)
                        orders_to_move = temp.head(move_count)
                        print(
                            f"unassigned_max_group 에 이동할 주문 수: {len(orders_to_move)}"
                        )

                        if needed > available:
                            print(
                                "이동할 데이터가 없으므로, [Y/R 4차 재배정]을 종료합니다."
                            )
                            break

                        move_orders(
                            df_shipping_region,
                            orders_to_move.index,
                            nearest_group,
                            clear_driver=True,
                        )

                        # (3) 만약 nearest_group에 (Y/R 등)가 이미 배정되어 있다면, 그 버니정보를 이동된 주문에도 적용
                        driver_data = df_shipping_region.loc[
                            (df_shipping_region["group"] == nearest_group)
                            & (df_shipping_region["driver_type"].notna())
                        ].head(1)

                        if not driver_data.empty:
                            assigned_type = driver_data["driver_type"].iloc[0]
                            assigned_code = driver_data["driver_code"].iloc[0]

                            df_shipping_region.loc[
                                orders_to_move.index, "driver_type"
                            ] = assigned_type
                            df_shipping_region.loc[
                                orders_to_move.index, "driver_code"
                            ] = assigned_code

                        # 이후 물량 카운트 버니 배정 처리
                        unassigned_max_group_volume = df_shipping_region[
                            df_shipping_region["group"] == unassigned_max_group
                        ]["shipping_uuid"].count()
                        nearest_volume = df_shipping_region[
                            df_shipping_region["group"] == nearest_group
                        ]["shipping_uuid"].count()
                        print(
                            f"이동 후, unassigned_group({unassigned_max_group})={unassigned_max_group_volume}건, nearest_group({nearest_group})={nearest_volume}건"
                        )

                        if unassigned_max_group_volume <= 55:
                            if assigned_non_orange < len(non_orange_drivers):
                                driver = non_orange_drivers.iloc[assigned_non_orange]
                                df_shipping_region.loc[
                                    df_shipping_region["group"] == unassigned_max_group,
                                    "driver_type",
                                ] = driver["Type"]
                                new_name = f"{unassigned_max_group}_Y/R"
                                df_shipping_region.loc[
                                    df_shipping_region["group"] == unassigned_max_group,
                                    "group",
                                ] = new_name

                                (
                                    df_shipping_region,
                                    assigned_non_orange,
                                    leftover_non_orange,
                                ) = assign_driver_to_group(
                                    df_shipping_region,
                                    new_name,
                                    non_orange_drivers,
                                    assigned_non_orange,
                                    leftover_non_orange,
                                    label="Y/R",
                                )
                                print(
                                    f"[4차 Y/R 배정] 그룹({new_name})의 주문 수가 {unassigned_max_group_volume}건이 되어, [{driver['Type']}]에 배정합니다."
                                )
                                group_centroids = recalc_group_centroids(
                                    df_shipping_region
                                )
                                if leftover_non_orange <= 0:
                                    print(
                                        "[Y/R 4차 재배정] 더 이상 Y/R 버니가 없습니다. 배정 중단."
                                    )
                                    break
                        else:
                            print(
                                f"이동할 수 있는 물량이 부족해 종료, 필요물량: {needed}, 가져올 수 있는 물량:{move_count}"
                            )
                            break

            elif nearest_driver_type == "ORANGE":
                if nearest_volume < 20:
                    print(
                        f"근접 그룹 {nearest_group}의 주문 수가 20건 미만({nearest_volume}건) → 종료"
                    )
                    break
                else:
                    print(
                        f"근접 그룹 {nearest_group}의 driver_type이 ORANGE입니다. {unassigned_max_group}의 물량이 20이 될 때까지 이동 시도합니다."
                    )
                    if volume < 40:
                        temp = nearest_orders.copy()

                        unassigned_points = unassigned_group_orders[["lat", "lng"]]
                        temp["dist_to_A"] = temp.apply(
                            lambda r: min_dist_to_group(r, unassigned_points), axis=1
                        )

                        temp.sort_values("dist_to_A", inplace=True)
                        needed = 40 - volume
                        available = nearest_volume - 20  # 이동 가능한 최대 주문 수
                        move_count = min(needed, available)
                        orders_to_move = temp.head(move_count)
                        print(
                            f"unassigned_max_group 에 이동할 주문 수: {len(orders_to_move)}"
                        )

                        if needed > available:
                            print(
                                "이동할 데이터가 없으므로, [Y/R 4차 재배정]을 종료합니다."
                            )
                            break

                        move_orders(
                            df_shipping_region,
                            orders_to_move.index,
                            unassigned_max_group,
                            clear_driver=True,
                        )

                        unassigned_max_group_volume = df_shipping_region[
                            df_shipping_region["group"] == unassigned_max_group
                        ]["shipping_uuid"].count()
                        if unassigned_max_group_volume >= 40:
                            if assigned_non_orange < len(non_orange_drivers):
                                driver = non_orange_drivers.iloc[assigned_non_orange]
                                df_shipping_region.loc[
                                    df_shipping_region["group"] == unassigned_max_group,
                                    "driver_type",
                                ] = driver["Type"]
                                new_name = f"{unassigned_max_group}_Y/R"
                                df_shipping_region.loc[
                                    df_shipping_region["group"] == unassigned_max_group,
                                    "group",
                                ] = new_name
                                (
                                    df_shipping_region,
                                    assigned_non_orange,
                                    leftover_non_orange,
                                ) = assign_driver_to_group(
                                    df_shipping_region,
                                    new_name,
                                    non_orange_drivers,
                                    assigned_non_orange,
                                    leftover_non_orange,
                                    label="Y/R",
                                )
                                print(
                                    f"[4차 Y/R 배정] A 그룹({new_name})의 주문 수가 {unassigned_max_group_volume}건이 되어, [{driver['Type']}]에 배정합니다."
                                )
                                group_centroids = recalc_group_centroids(
                                    df_shipping_region
                                )
                                if leftover_non_orange <= 0:
                                    print(
                                        "[Y/R 4차 재배정] 더 이상 Y/R 버니가 없습니다. 배정 중단."
                                    )
                                    break
                        else:
                            print(
                                f"이동할 수 있는 물량이 부족해 종료, 필요물량: {needed}, 가져올 수 있는 물량:{move_count}"
                            )
                            break

                    elif volume >= 56:
                        if nearest_group in group_centroids:
                            nearest_group_centroid = group_centroids[nearest_group]
                        else:
                            nearest_group_orders = df_shipping_region[
                                df_shipping_region["group"] == nearest_group
                            ]
                            nearest_group_centroid = (
                                nearest_group_orders["lat"].mean(),
                                nearest_group_orders["lng"].mean(),
                            )
                            group_centroids[nearest_group] = nearest_group_centroid

                        temp = df_shipping_region[
                            df_shipping_region["group"] == unassigned_max_group
                        ].copy()

                        nearest_group_points = df_shipping_region[
                            df_shipping_region["group"] == nearest_group
                        ][["lat", "lng"]]
                        temp["dist_to_A"] = temp.apply(
                            lambda row: min_dist_to_group(row, nearest_group_points),
                            axis=1,
                        )

                        temp.sort_values("dist_to_A", inplace=True)
                        # 60이상은 위에서 이미 클러스터링 돼서 남아있는 그룹은 50~59
                        needed = volume - 55
                        available = (
                            29 - nearest_volume
                        )  # 이동 가능한 최대 주문 수 => 배정이 안 될 수도 있으므로, 여유 둠.(최후)
                        move_count = min(needed, available)
                        orders_to_move = temp.head(move_count)
                        print(
                            f"unassigned_max_group 에 이동할 주문 수: {len(orders_to_move)}"
                        )

                        if needed > available:
                            print(
                                "이동할 데이터가 없으므로, [Y/R 4차 재배정]을 종료합니다."
                            )
                            break

                        move_orders(
                            df_shipping_region,
                            orders_to_move.index,
                            nearest_group,
                            clear_driver=True,
                        )

                        # (3) 만약 nearest_group에
                        # 버니(Y/R 등)가 이미 배정되어 있다면, 그 버니정보를 이동된 주문에도 적용
                        driver_data = df_shipping_region.loc[
                            (df_shipping_region["group"] == nearest_group)
                            & (df_shipping_region["driver_type"].notna())
                        ].head(1)

                        if not driver_data.empty:
                            assigned_type = driver_data["driver_type"].iloc[0]
                            assigned_code = driver_data["driver_code"].iloc[0]

                            df_shipping_region.loc[
                                orders_to_move.index, "driver_type"
                            ] = assigned_type
                            df_shipping_region.loc[
                                orders_to_move.index, "driver_code"
                            ] = assigned_code

                        # 이후 물량 카운트, 버니 배정 처리
                        unassigned_max_group_volume = df_shipping_region[
                            df_shipping_region["group"] == unassigned_max_group
                        ]["shipping_uuid"].count()
                        nearest_volume = df_shipping_region[
                            df_shipping_region["group"] == nearest_group
                        ]["shipping_uuid"].count()
                        print(
                            f"이동 후, unassigned_group({unassigned_max_group})={unassigned_max_group_volume}건, nearest_group({nearest_group})={nearest_volume}건"
                        )

                        if unassigned_max_group_volume <= 55:
                            if assigned_non_orange < len(non_orange_drivers):
                                driver = non_orange_drivers.iloc[assigned_non_orange]
                                df_shipping_region.loc[
                                    df_shipping_region["group"] == unassigned_max_group,
                                    "driver_type",
                                ] = driver["Type"]
                                new_name = f"{unassigned_max_group}_Y/R"
                                df_shipping_region.loc[
                                    df_shipping_region["group"] == unassigned_max_group,
                                    "group",
                                ] = new_name

                                (
                                    df_shipping_region,
                                    assigned_non_orange,
                                    leftover_non_orange,
                                ) = assign_driver_to_group(
                                    df_shipping_region,
                                    new_name,
                                    non_orange_drivers,
                                    assigned_non_orange,
                                    leftover_non_orange,
                                    label="Y/R",
                                )
                                print(
                                    f"[4차 Y/R 배정] 그룹({new_name})의 주문 수가 {unassigned_max_group_volume}건이 되어, [{driver['Type']}]에 배정합니다."
                                )
                                group_centroids = recalc_group_centroids(
                                    df_shipping_region
                                )
                                if leftover_non_orange <= 0:
                                    print(
                                        "[Y/R 4차 재배정] 더 이상 Y/R 버니가 없습니다. 배정 중단."
                                    )
                                    break
                        else:
                            print(
                                f"이동할 수 있는 물량이 부족해 종료, 필요물량: {needed}, 가져올 수 있는 물량:{move_count}"
                            )
                            break

            else:
                print(
                    f"근접 그룹 {nearest_group}의 driver_type({nearest_driver_type})에 대해 정의된 로직이 없습니다."
                )
        else:
            print("미배정 그룹 외에 다른 그룹이 없습니다.")

    # ---------------------------------------------------------------------------
    # 2차 배정: ORANGE 2차 재배정
    print("### [O 2차 재배정] ###")
    stop_all = False

    for _ in range(len(orange_drivers)):
        if leftover_orange <= 0:
            stop_all = True
            break

        unassigned_df = df_shipping_region[df_shipping_region["driver_type"].isna()]

        # 현재 group별 주문 수 집계
        group_counts = unassigned_df.groupby("group")["shipping_uuid"].count()
        # 40건 이상인 그룹만 추출
        candidate_groups = group_counts[group_counts >= 40].index.tolist()

        print(
            f"[O 2차 재배정] 남은 오렌지 버니: {leftover_orange}명, 배정되지 않은 40건 이상 그룹: {candidate_groups}"
        )

        # 40건 이상 그룹이 없으면 종료
        if not candidate_groups:
            break

        # 40건 이상 그룹을 순회
        for grp in candidate_groups:
            if leftover_orange <= 0:
                stop_all = True
                break

            # 스택(LIFO)으로 관리
            group_stack = [grp]

            while group_stack and not stop_all:
                current_group = group_stack.pop()
                grp_orders = df_shipping_region[
                    df_shipping_region["group"] == current_group
                ].copy()
                current_count = grp_orders.shape[0]

                # 이미 40건 미만으로 줄었다면 스킵
                if current_count < 40:
                    continue

                print(
                    f"[O 2차 재배정] 그룹[{current_group}] (주문수: {current_count}) → KMeans 2클러스터링 시도"
                )

                grp_orders, cluster_counts, label_a, count_a, label_b, count_b = (
                    split_group_kmeans_2clusters(df_shipping_region, current_group)
                )

                # 만약 제대로 2개 클러스터가 안 나오면(=1개뿐)
                if len(cluster_counts) < 2 or label_b is None:
                    # 클러스터가 하나뿐이면 다음으로 넘어감
                    continue

                print(
                    f"  → 클러스터 A={label_a}({count_a}건), 클러스터 B={label_b}({count_b}건)"
                )

                # idx_a / idx_b 미리 추출
                idx_a = grp_orders[grp_orders["cluster"] == label_a].index
                idx_b = grp_orders[grp_orders["cluster"] == label_b].index

                # --------------------------------------
                # [조건1] 두 클러스터 모두 40건 이상
                # --------------------------------------
                if count_a >= 40 and count_b >= 40:
                    new_group_a = f"{current_group}_SPLIT_{label_a}"
                    new_group_b = f"{current_group}_SPLIT_{label_b}"

                    # move_orders 사용 (clear_driver=False)
                    move_orders(
                        df_shipping_region, idx_a, new_group_a, clear_driver=False
                    )
                    move_orders(
                        df_shipping_region, idx_b, new_group_b, clear_driver=False
                    )

                    print(
                        f"  → 두 클러스터 모두 40건 이상 → [{new_group_a}], [{new_group_b}] 스택에 재추가"
                    )
                    group_stack.append(new_group_a)
                    group_stack.append(new_group_b)
                    continue

                # --------------------------------------
                # [조건2] 한쪽은 20~31, 다른 쪽은 40 이상
                # --------------------------------------
                if 20 <= count_a <= 31 and count_b >= 40:
                    new_orange_group_a = f"{current_group}_O_{label_a}"
                    new_group_b = f"{current_group}_SPLIT_{label_b}"

                    move_orders(
                        df_shipping_region,
                        idx_a,
                        new_orange_group_a,
                        clear_driver=False,
                    )
                    move_orders(
                        df_shipping_region, idx_b, new_group_b, clear_driver=False
                    )

                    # 오렌지 배정
                    if assigned_orange < len(orange_drivers):
                        # 헬퍼 함수로 배정
                        driver_before = orange_drivers.iloc[
                            assigned_orange
                        ]  # 배정 전 기사 정보
                        df_shipping_region, assigned_orange, leftover_orange = (
                            assign_driver_to_group(
                                df_shipping_region,
                                new_orange_group_a,
                                orange_drivers,
                                assigned_orange,
                                leftover_orange,
                                label="ORANGE",
                            )
                        )
                        print(
                            f"  → [조건2] 그룹[{new_orange_group_a}]({count_a}건) → [{driver_before['Type']}] 배정"
                        )
                        if leftover_orange <= 0:
                            print(
                                "[2차 O 재배정] 더 이상 배정할 오렌지 버니가 없습니다."
                            )
                            stop_all = True
                            break
                    else:
                        print("[2차 O 재배정] 더 이상 배정할 오렌지 버니가 없습니다.")
                        stop_all = True
                        break

                    group_stack.append(new_group_b)
                    continue

                if 20 <= count_b <= 31 and count_a >= 40:
                    new_orange_group_b = f"{current_group}_O_{label_b}"
                    new_group_a = f"{current_group}_SPLIT_{label_a}"

                    move_orders(
                        df_shipping_region,
                        idx_b,
                        new_orange_group_b,
                        clear_driver=False,
                    )
                    move_orders(
                        df_shipping_region, idx_a, new_group_a, clear_driver=False
                    )

                    if assigned_orange < len(orange_drivers):
                        driver_before = orange_drivers.iloc[assigned_orange]
                        df_shipping_region, assigned_orange, leftover_orange = (
                            assign_driver_to_group(
                                df_shipping_region,
                                new_orange_group_b,
                                orange_drivers,
                                assigned_orange,
                                leftover_orange,
                                label="ORANGE",
                            )
                        )
                        print(
                            f"  → [조건2] 그룹[{new_orange_group_b}]({count_b}건) → 오렌지 버니[{driver_before['Type']}] 배정"
                        )

                        if leftover_orange <= 0:
                            print(
                                "[2차 O 재배정] 더 이상 배정할 오렌지 버니가 없습니다."
                            )
                            stop_all = True
                            break
                    else:
                        print("[2차 O 재배정] 더 이상 배정할 오렌지 버니가 없습니다.")
                        stop_all = True
                        break

                    group_stack.append(new_group_a)
                    continue

                # --------------------------------------
                # [조건3] 두 클러스터 모두 20~31
                # --------------------------------------
                if (20 <= count_a <= 31) and (20 <= count_b <= 31):
                    new_orange_group_a = f"{current_group}_O_{label_a}"
                    new_orange_group_b = f"{current_group}_O_{label_b}"

                    move_orders(
                        df_shipping_region,
                        idx_a,
                        new_orange_group_a,
                        clear_driver=False,
                    )
                    move_orders(
                        df_shipping_region,
                        idx_b,
                        new_orange_group_b,
                        clear_driver=False,
                    )

                    # A 배정
                    if assigned_orange < len(orange_drivers):
                        driver_a_before = orange_drivers.iloc[assigned_orange]
                        df_shipping_region, assigned_orange, leftover_orange = (
                            assign_driver_to_group(
                                df_shipping_region,
                                new_orange_group_a,
                                orange_drivers,
                                assigned_orange,
                                leftover_orange,
                                label="ORANGE",
                            )
                        )
                        print(
                            f"  → [조건3] 그룹[{new_orange_group_a}]({count_a}건) → 오렌지 버니[{driver_a_before['Type']}] 배정"
                        )
                        if leftover_orange <= 0:
                            print(
                                "[2차 O 재배정] 더 이상 배정할 오렌지 버니가 없습니다."
                            )
                            stop_all = True
                            break
                    else:
                        print("[2차 O 재배정] 더 이상 오렌지 버니가 없습니다.")
                        stop_all = True
                        break

                    # B 배정
                    if assigned_orange < len(orange_drivers):
                        driver_b_before = orange_drivers.iloc[assigned_orange]
                        df_shipping_region, assigned_orange, leftover_orange = (
                            assign_driver_to_group(
                                df_shipping_region,
                                new_orange_group_b,
                                orange_drivers,
                                assigned_orange,
                                leftover_orange,
                                label="ORANGE",
                            )
                        )
                        print(
                            f"  → [조건3] 그룹[{new_orange_group_b}]({count_b}건) → 오렌지 버니[{driver_b_before['Type']}] 배정"
                        )
                        if leftover_orange <= 0:
                            print(
                                "[2차 O 재배정] 더 이상 배정할 오렌지 버니가 없습니다."
                            )
                            stop_all = True
                            break
                    else:
                        print("[2차 O 재배정] 더 이상 오렌지 버니가 없습니다.")
                        stop_all = True
                        break

                    continue

                # --------------------------------------
                # [조건4] 한 클러스터가 20~31, 다른 클러스터가 30~39
                # --------------------------------------
                # 기존 in_range() 함수를 재사용
                if in_range(count_a, 20, 32) and in_range(count_b, 30, 40):
                    new_orange_group_a = f"{current_group}_O_{label_a}"
                    remain_group_b = f"{current_group}_remain_{label_b}"

                    move_orders(
                        df_shipping_region,
                        idx_a,
                        new_orange_group_a,
                        clear_driver=False,
                    )
                    move_orders(
                        df_shipping_region, idx_b, remain_group_b, clear_driver=False
                    )

                    if assigned_orange < len(orange_drivers):
                        driver_before = orange_drivers.iloc[assigned_orange]
                        df_shipping_region, assigned_orange, leftover_orange = (
                            assign_driver_to_group(
                                df_shipping_region,
                                new_orange_group_a,
                                orange_drivers,
                                assigned_orange,
                                leftover_orange,
                                label="ORANGE",
                            )
                        )
                        print(
                            f"  → [조건4] 그룹[{new_orange_group_a}]({count_a}건) → [{driver_before['Type']}] 배정, 나머지[{remain_group_b}]는 유지({count_b}건)"
                        )

                        if leftover_orange <= 0:
                            print(
                                "[2차 O 재배정] 더 이상 배정할 오렌지 버니가 없습니다."
                            )
                            stop_all = True
                            break
                    else:
                        print("[2차 O 재배정] 더 이상 오렌지 버니가 없습니다.")
                        stop_all = True
                        break

                    continue

                if in_range(count_b, 20, 32) and in_range(count_a, 30, 40):
                    new_orange_group_b = f"{current_group}_O_{label_b}"
                    remain_group_a = f"{current_group}_remain_{label_a}"

                    move_orders(
                        df_shipping_region,
                        idx_b,
                        new_orange_group_b,
                        clear_driver=False,
                    )
                    move_orders(
                        df_shipping_region, idx_a, remain_group_a, clear_driver=False
                    )

                    if assigned_orange < len(orange_drivers):
                        driver_before = orange_drivers.iloc[assigned_orange]
                        df_shipping_region, assigned_orange, leftover_orange = (
                            assign_driver_to_group(
                                df_shipping_region,
                                new_orange_group_b,
                                orange_drivers,
                                assigned_orange,
                                leftover_orange,
                                label="ORANGE",
                            )
                        )
                        print(
                            f"  → [조건4] 그룹[{new_orange_group_b}]({count_b}건) → [{driver_before['Type']}] 배정, 나머지[{remain_group_a}]는 유지({count_a}건)"
                        )
                        if leftover_orange <= 0:
                            print(
                                "[2차 O 재배정] 더 이상 배정할 오렌지 버니가 없습니다."
                            )
                            stop_all = True
                            break
                    else:
                        print("[2차 O 재배정] 더 이상 오렌지 버니가 없습니다.")
                        stop_all = True
                        break

                    continue

                # --------------------------------------
                # [조건5] 그 외 - 부족 / 초과 로직으로 20건 맞추기
                # --------------------------------------
                # 작은/큰 클러스터 식별
                if cluster_counts[label_a] <= cluster_counts[label_b]:
                    small_label, large_label = label_a, label_b
                else:
                    small_label, large_label = label_b, label_a

                small_count = cluster_counts[small_label]
                large_count = cluster_counts[large_label]

                print(
                    f"  → [조건5] 작은 클러스터={small_label}({small_count}건), 큰 클러스터={large_label}({large_count}건)"
                )

                # A) 작은 클러스터 < 20 → 큰 쪽에서 가져와 20 맞추기
                if small_count < 20:
                    deficit = 20 - small_count
                    print(
                        f"    → 작은 클러스터 부족 {deficit}건. 큰 클러스터 -> 작은 클러스터 이동"
                    )

                    small_cluster_points = grp_orders[
                        grp_orders["cluster"] == small_label
                    ][["lat", "lng"]]
                    large_orders = grp_orders[
                        grp_orders["cluster"] == large_label
                    ].copy()
                    large_orders["dist_to_small"] = large_orders.apply(
                        lambda row: min_dist_to_group(row, small_cluster_points), axis=1
                    )
                    large_orders.sort_values("dist_to_small", inplace=True)
                    indices_to_move = large_orders.index[:deficit]

                    # 실제 데이터프레임에 반영
                    df_shipping_region.loc[
                        indices_to_move, ["driver_type", "driver_code"]
                    ] = np.nan
                    grp_orders.loc[indices_to_move, "cluster"] = small_label
                    print(
                        f"  → {deficit}건을 대형 클러스터에서 작은 클러스터로 이동 (가장 가까운 순)"
                    )

                # B) 작은 클러스터 >= 32 → 일부를 큰 쪽으로 이동
                elif small_count >= 32:
                    surplus = small_count - 20
                    print(
                        f"    → 작은 클러스터 초과 {surplus}건. 작은 클러스터 -> 큰 클러스터 이동"
                    )

                    large_cluster_points = grp_orders[
                        grp_orders["cluster"] == large_label
                    ][["lat", "lng"]]
                    small_orders = grp_orders[
                        grp_orders["cluster"] == small_label
                    ].copy()
                    small_orders["dist_to_large"] = small_orders.apply(
                        lambda row: min_dist_to_group(row, large_cluster_points), axis=1
                    )
                    small_orders.sort_values("dist_to_large", inplace=True)
                    indices_to_move = small_orders.index[:surplus]

                    df_shipping_region.loc[
                        indices_to_move, ["driver_type", "driver_code"]
                    ] = np.nan
                    grp_orders.loc[indices_to_move, "cluster"] = large_label
                    print(f"  → {surplus}건을 작은 클러스터에서 대형 클러스터로 이동")

                new_counts = grp_orders["cluster"].value_counts()
                new_small_count = new_counts.get(small_label, 0)
                print(
                    f"  → 조정 후 작은 클러스터 {small_label} 주문 수: {new_small_count} (목표:20)"
                )

                if new_small_count == 20:
                    base_name = current_group.split("_cluster")[0]
                    yr_group_counter.setdefault(base_name, 0)
                    yr_group_counter[base_name] += 1

                    new_grp_label_target = (
                        f"{base_name}_cluster_O_{yr_group_counter[base_name]}"
                    )
                    new_grp_label_remaining = f"{current_group}_remaining"

                    indices_target = grp_orders[
                        grp_orders["cluster"] == small_label
                    ].index
                    indices_remaining = grp_orders[
                        grp_orders["cluster"] == large_label
                    ].index

                    # 그룹 이동
                    move_orders(
                        df_shipping_region,
                        indices_target,
                        new_grp_label_target,
                        clear_driver=False,
                    )
                    move_orders(
                        df_shipping_region,
                        indices_remaining,
                        new_grp_label_remaining,
                        clear_driver=False,
                    )

                    if assigned_orange < len(orange_drivers):
                        driver_before = orange_drivers.iloc[assigned_orange]
                        df_shipping_region, assigned_orange, leftover_orange = (
                            assign_driver_to_group(
                                df_shipping_region,
                                new_grp_label_target,
                                orange_drivers,
                                assigned_orange,
                                leftover_orange,
                                label="ORANGE",
                            )
                        )
                        print(
                            f"[2차 O 재배정] 그룹[{new_grp_label_target}] (주문수: {new_small_count}) → [{driver_before['Type']}] 배정"
                        )
                        group_centroids = recalc_group_centroids(df_shipping_region)
                        print(
                            "[2차 O 재배정] 후 그룹별 물량:\n",
                            df_shipping_region.groupby("group")[
                                "shipping_uuid"
                            ].count(),
                        )

                        if leftover_orange <= 0:
                            print(
                                "[2차 O 재배정] 더 이상 배정할 오렌지 버니가 없습니다."
                            )
                            stop_all = True
                            break
                    else:
                        print(
                            "[2차 O 재배정] 배정 가능한 오렌지 버니가 더 이상 없습니다."
                        )
                        break

                if leftover_orange <= 0:
                    print("[2차 O 재배정] 더 이상 오렌지 버니가 없습니다.")
                    stop_all = True
                    break

        leftover_orange = len(orange_drivers) - assigned_orange
        print(f"[O 2차 재배정] 루프 종료, 남은 오렌지 버니: {leftover_orange}")

        if stop_all:
            break

    print("[O 2차 재배정] 로직 종료 또는 버니 부족")

    # [3차 O 재배정]
    while leftover_orange > 0:
        # 남은 20-31 지역 남은 오렌지 버니에게 배정
        plus_unassigned_groups = df_shipping_region[
            df_shipping_region["driver_type"].isna()
        ]["group"].unique()
        plus_candidate_groups = []
        for grp in plus_unassigned_groups:
            cnt = df_shipping_region[df_shipping_region["group"] == grp][
                "shipping_uuid"
            ].count()
            if 20 <= cnt <= 31:
                plus_candidate_groups.append(grp)

        if not plus_candidate_groups:
            print(
                "[3차 O 재배정] 더 이상 주문 수 20이상 31 이하의 미배정 그룹이 없습니다."
            )
            break

        print(f"[3차 O 재배정]대상 그룹: {plus_candidate_groups}")

        for grp in plus_candidate_groups:
            if leftover_orange <= 0:
                break

            grp_orders = df_shipping_region[df_shipping_region["group"] == grp]
            print("[3차 O 재배정] 20~31 그룹 Orange 에게 배정")

            # (1) 그룹 이름 변경
            new_grp_label = f"{grp}_O"
            selected_idx = grp_orders.index

            move_orders(
                df_shipping_region, selected_idx, new_grp_label, clear_driver=False
            )

            # (2) 오렌지 기사 배정
            if assigned_orange < len(orange_drivers):
                # 배정 전 기사 정보를 따로 보관
                driver_before = orange_drivers.iloc[assigned_orange]

                df_shipping_region, assigned_orange, leftover_orange = (
                    assign_driver_to_group(
                        df_shipping_region,
                        new_grp_label,
                        orange_drivers,
                        assigned_orange,
                        leftover_orange,
                        label="ORANGE",
                    )
                )
                # 기존 출력 메시지
                print(
                    f"[3차 O 재배정] 그룹[{new_grp_label}] (물량={len(grp_orders)}) → [{driver_before['Type']}] 배정"
                )

                group_centroids = recalc_group_centroids(df_shipping_region)

                # 기존 로직: 필요시 group_centroids에서 기존 grp 키를 삭제
                if grp in group_centroids:
                    del group_centroids[grp]

                if leftover_orange <= 0:
                    print("[2차 O 재배정] 더 이상 배정할 오렌지 버니가 없습니다.")
                    break
            else:
                print("[3차 O 재배정] 더 이상 배정할 오렌지 버니가 없습니다.")
                break
    # [4차 O 재배정]
    print("[ORANGE 4차 재배정]")
    while leftover_orange > 0:
        unassigned_groups = df_shipping_region[
            df_shipping_region["driver_type"].isna()
        ]["group"].unique()
        if len(unassigned_groups) == 0:
            print("[ORANGE 4차 재배정] 배정되지 않은 그룹이 없습니다.")
            break

        unassigned_group_counts = (
            df_shipping_region[df_shipping_region["group"].isin(unassigned_groups)]
            .groupby("group")["shipping_uuid"]
            .count()
        )
        group_centroids = recalc_group_centroids(df_shipping_region)

        # 물량이 가장 많은 그룹
        unassigned_max_group = unassigned_group_counts.idxmax()
        max_cnt = unassigned_group_counts[unassigned_max_group]
        print(
            f"선택된 unassigned_max_group (물량 많은 그룹): {unassigned_max_group} (물량: {max_cnt}건)"
        )

        unassigned_group_orders = df_shipping_region[
            df_shipping_region["group"] == unassigned_max_group
        ]
        unassigned_points = unassigned_group_orders[["lat", "lng"]]

        plus_candidate_groups = [
            g for g in group_centroids.keys() if g != unassigned_max_group
        ]
        if plus_candidate_groups:
            # 1) unassigned_max_group에서 각 candidate 그룹까지의 거리를 계산
            distances = {}
            for g in plus_candidate_groups:
                centroid = group_centroids[g]
                # 중심점 끼리의 거리 (혹은 unassigned_points의 평균 vs centroid)
                dist = np.sqrt(
                    (unassigned_points["lat"].mean() - centroid[0]) ** 2
                    + (unassigned_points["lng"].mean() - centroid[1]) ** 2
                )
                distances[g] = dist

            nearest_group = min(distances, key=distances.get)
            print(f"unassigned_max_group 과 가장 가까운 그룹: {nearest_group}")

            nearest_orders = df_shipping_region[
                df_shipping_region["group"] == nearest_group
            ]
            nearest_points = nearest_orders[["lat", "lng"]]

            # 근접 그룹의 driver_type
            if not nearest_orders.empty:
                nearest_driver_type = nearest_orders["driver_type"].iloc[0]
            else:
                nearest_driver_type = None

            print(f"근접 그룹 {nearest_group}의 driver_type: {nearest_driver_type}")

            # 근접 그룹 centroid 갱신 (혹시 없으면)
            if nearest_group in group_centroids:
                nearest_group_centroid = group_centroids[nearest_group]
            else:
                nearest_group_centroid = (
                    nearest_orders["lat"].mean(),
                    nearest_orders["lng"].mean(),
                )
                group_centroids[nearest_group] = nearest_group_centroid

            volume = max_cnt  # unassigned_max_group 물량
            nearest_volume = len(nearest_orders)  # 근접 그룹 물량

            # -------------------------------------------------
            # 근접 그룹의 드라이버 타입이 NULL (pd.isna) 일 때
            # -------------------------------------------------
            if pd.isna(nearest_driver_type):
                print(
                    f"근접 그룹 {nearest_group}의 driver_type이 null이므로, unassigned_max_group 의 물량이 20이 될 때까지 데이터를 이동합니다."
                )

                # A) 배정되지 않은 그룹의 수량이 20 미만
                if volume < 20:
                    needed = 20 - volume
                    available = nearest_volume - 20  # 이동 가능한 최대 주문 수
                    move_count = min(needed, available)
                    print(
                        f"unassigned_max_group={unassigned_max_group} 부족분={needed}, 근접그룹={nearest_group} (volume={nearest_volume})에서 가져올 수={move_count}"
                    )

                    if needed > available:
                        print(
                            "이동할 데이터가 없으므로, [ORANGE 4차 재배정]을 종료합니다."
                        )
                        break

                    temp = nearest_orders.copy()
                    temp["dist_to_A"] = temp.apply(
                        lambda r: min_dist_to_group(r, unassigned_points), axis=1
                    )
                    temp.sort_values("dist_to_A", inplace=True)

                    orders_to_move = temp.head(move_count)

                    move_orders(
                        df_shipping_region,
                        orders_to_move.index,
                        unassigned_max_group,
                        clear_driver=True,
                    )

                    # 이동 후 unassigned_max_group 물량 재확인
                    unassigned_max_group_volume = df_shipping_region[
                        df_shipping_region["group"] == unassigned_max_group
                    ]["shipping_uuid"].count()
                    print(
                        f"→ 이동 후 unassigned_max_group={unassigned_max_group}의 물량={unassigned_max_group_volume}건"
                    )

                    # 물량 20 이상 → Orange 배정
                    if unassigned_max_group_volume >= 20:
                        if assigned_orange < len(orange_drivers):
                            # 그룹명 변경
                            driver_before = orange_drivers.iloc[assigned_orange]
                            new_name = f"{unassigned_max_group}_O"

                            # 그룹명 교체
                            df_shipping_region.loc[
                                df_shipping_region["group"] == unassigned_max_group,
                                "group",
                            ] = new_name

                            # 드라이버 배정
                            df_shipping_region, assigned_orange, leftover_orange = (
                                assign_driver_to_group(
                                    df_shipping_region,
                                    new_name,
                                    orange_drivers,
                                    assigned_orange,
                                    leftover_orange,
                                    label="ORANGE",
                                )
                            )
                            print(
                                f"[ORANGE 4차 재배정] 그룹({new_name})의 주문 수가 {unassigned_max_group_volume}건이 되어, 남은 O 버니[{driver_before['uuid']}]에 배정합니다."
                            )

                            group_centroids = recalc_group_centroids(df_shipping_region)
                            if leftover_orange <= 0:
                                print(
                                    "[ORANGE 4차 재배정] 더 이상 오렌지 버니가 없습니다. 재배정 중단."
                                )
                                break
                    else:
                        print(
                            f"이동할 수 있는 물량이 부족해 종료, 필요물량: {needed}, 가져올 수 있는 물량:{move_count}"
                        )
                        break

                # B) 배정되지 않은 그룹의 물량이 32 이상
                elif volume >= 32:
                    needed = volume - 31

                    # 거리 계산
                    temp = unassigned_group_orders.copy()
                    temp["dist_to_A"] = temp.apply(
                        lambda r: min_dist_to_group(r, nearest_points), axis=1
                    )
                    temp.sort_values("dist_to_A", inplace=True)

                    orders_to_move = temp.head(needed)
                    print(f"nearest_group 에 이동할 주문 수: {len(orders_to_move)}")

                    if len(orders_to_move) == 0:
                        print("이동할 데이터가 없으므로 종료")
                        break

                    move_orders(
                        df_shipping_region,
                        orders_to_move.index,
                        nearest_group,
                        clear_driver=True,
                    )
                    unassigned_max_group_volume = df_shipping_region[
                        df_shipping_region["group"] == unassigned_max_group
                    ]["shipping_uuid"].count()
                    nearest_group_volume = df_shipping_region[
                        df_shipping_region["group"] == nearest_group
                    ].shape[0]
                    print(
                        f"→ 이동 후 unassigned_max_group={unassigned_max_group}={unassigned_max_group_volume}건, nearest_group={nearest_group}={nearest_group_volume}건"
                    )

                    # 31 이하로 줄었다면 → Orange 배정
                    if unassigned_max_group_volume <= 31:
                        if assigned_orange < len(orange_drivers):
                            driver_before = orange_drivers.iloc[assigned_orange]
                            new_name = f"{unassigned_max_group}_O"

                            # 그룹명 교체
                            df_shipping_region.loc[
                                df_shipping_region["group"] == unassigned_max_group,
                                "group",
                            ] = new_name

                            # 드라이버 배정
                            df_shipping_region, assigned_orange, leftover_orange = (
                                assign_driver_to_group(
                                    df_shipping_region,
                                    new_name,
                                    orange_drivers,
                                    assigned_orange,
                                    leftover_orange,
                                    label="ORANGE",
                                )
                            )
                            print(
                                f"[ORANGE 4차 재배정] 그룹({new_name})의 주문 수가 {unassigned_max_group_volume}건이 되어, [{driver_before['Type']}]에 배정합니다."
                            )

                            group_centroids = recalc_group_centroids(df_shipping_region)
                            if leftover_orange <= 0:
                                print(
                                    "[ORANGE 4차 재배정] 더 이상 오렌지 버니가 없습니다. 재배정 중단."
                                )
                                break
                        else:
                            print("[ORANGE 4차 재배정] 더 이상 오렌지 버니가 없습니다.")
                            break

            # -------------------------------------------------
            # 근접 그룹 드라이버 타입이 YELLOW / RAINBOW 일 때
            # -------------------------------------------------
            elif nearest_driver_type in ["YELLOW", "RAINBOW"]:
                if nearest_volume < 40:
                    print(
                        f"근접 그룹 {nearest_group}의 물량이 40 미만({nearest_volume}건)이라 unassigned_max_group 에 데이터를 가져올 수 없습니다. 종료합니다."
                    )
                    break
                else:
                    print(
                        f"근접 그룹 {nearest_group}의 driver_type이 Y/R입니다. unassigned_max_group 목표 물량: 20~29, 데이터 이동 시도합니다."
                    )

                    # A) unassigned_max_group 물량 < 20
                    if volume < 20:
                        needed = 20 - volume
                        available = nearest_volume - 40
                        move_count = min(needed, available)
                        print(
                            f"unassigned_max_group={unassigned_max_group} 부족분={needed}, 근접그룹={nearest_group} (volume={nearest_volume})에서 가져올 수={move_count}"
                        )

                        if needed > available:
                            print(
                                "이동할 데이터가 없으므로, [ORANGE 4차 재배정]을 종료합니다."
                            )
                            break

                        temp = nearest_orders.copy()
                        temp["dist_to_A"] = temp.apply(
                            lambda r: min_dist_to_group(r, unassigned_points), axis=1
                        )
                        temp.sort_values("dist_to_A", inplace=True)

                        orders_to_move = temp.head(move_count)
                        print(
                            f"unassigned_max_group 에 이동할 주문 수: {len(orders_to_move)}"
                        )

                        if needed > available:
                            print(
                                "이동할 데이터가 없으므로, [ORANGE 4차 재배정]을 종료합니다."
                            )
                            break

                        move_orders(
                            df_shipping_region,
                            orders_to_move.index,
                            unassigned_max_group,
                            clear_driver=True,
                        )
                        unassigned_max_group_volume = df_shipping_region[
                            df_shipping_region["group"] == unassigned_max_group
                        ]["shipping_uuid"].count()
                        if unassigned_max_group_volume >= 20:
                            if assigned_orange < len(orange_drivers):
                                driver_before = orange_drivers.iloc[assigned_orange]
                                new_name = f"{unassigned_max_group}_O"

                                # 그룹명 교체
                                df_shipping_region.loc[
                                    df_shipping_region["group"] == unassigned_max_group,
                                    "group",
                                ] = new_name

                                # 드라이버 배정
                                df_shipping_region, assigned_orange, leftover_orange = (
                                    assign_driver_to_group(
                                        df_shipping_region,
                                        new_name,
                                        orange_drivers,
                                        assigned_orange,
                                        leftover_orange,
                                        label="ORANGE",
                                    )
                                )
                                print(
                                    f"[ORANGE 4차 배정] 그룹({new_name})의 주문 수가 {unassigned_max_group_volume}건이 되어, [{driver_before['Type']}]에 배정합니다."
                                )

                                group_centroids = recalc_group_centroids(
                                    df_shipping_region
                                )
                                if leftover_orange <= 0:
                                    print(
                                        "[ORANGE 4차 재배정] 더 이상 오렌지 버니가 없습니다. 재배정 중단."
                                    )
                                    break
                        else:
                            print(
                                f"이동할 수 있는 물량이 부족해 종료, 필요물량: {needed}, 가져올 수 있는 물량:{move_count}"
                            )
                            break

                    # B) unassigned_max_group 물량 >= 30
                    elif volume >= 32:
                        needed = volume - 31
                        available = 55 - nearest_volume
                        move_count = min(needed, available)

                        if needed > available:
                            print(
                                "이동할 데이터가 없으므로, [O 4차 재배정]을 종료합니다."
                            )
                            break

                        temp = df_shipping_region[
                            df_shipping_region["group"] == unassigned_max_group
                        ].copy()
                        temp["dist_to_A"] = temp.apply(
                            lambda r: min_dist_to_group(r, nearest_points), axis=1
                        )
                        temp.sort_values("dist_to_A", inplace=True)

                        orders_to_move = temp.head(move_count)
                        print(f"nearest_group 에 이동할 주문 수: {len(orders_to_move)}")

                        move_orders(
                            df_shipping_region,
                            orders_to_move.index,
                            nearest_group,
                            clear_driver=True,
                        )
                        # 만약 nearest_group에 이미 배정된 드라이버가 있다면 적용
                        driver_data = df_shipping_region.loc[
                            (df_shipping_region["group"] == nearest_group)
                            & (df_shipping_region["driver_type"].notna())
                        ].head(1)
                        if not driver_data.empty:
                            assigned_type = driver_data["driver_type"].iloc[0]
                            assigned_code = driver_data["driver_code"].iloc[0]
                            df_shipping_region.loc[
                                orders_to_move.index, "driver_type"
                            ] = assigned_type
                            df_shipping_region.loc[
                                orders_to_move.index, "driver_code"
                            ] = assigned_code

                        unassigned_max_group_volume = df_shipping_region[
                            df_shipping_region["group"] == unassigned_max_group
                        ]["shipping_uuid"].count()
                        nearest_volume = df_shipping_region[
                            df_shipping_region["group"] == nearest_group
                        ]["shipping_uuid"].count()
                        print(
                            f"이동 후, unassigned_group({unassigned_max_group})={unassigned_max_group_volume}건, nearest_group({nearest_group})={nearest_volume}건"
                        )

                        if unassigned_max_group_volume <= 31:
                            if assigned_orange < len(orange_drivers):
                                driver_before = orange_drivers.iloc[assigned_orange]
                                new_name = f"{unassigned_max_group}_O"

                                # 그룹명 교체
                                df_shipping_region.loc[
                                    df_shipping_region["group"] == unassigned_max_group,
                                    "group",
                                ] = new_name

                                # 드라이버 배정
                                df_shipping_region, assigned_orange, leftover_orange = (
                                    assign_driver_to_group(
                                        df_shipping_region,
                                        new_name,
                                        orange_drivers,
                                        assigned_orange,
                                        leftover_orange,
                                        label="ORANGE",
                                    )
                                )
                                print(
                                    f"[4차 ORANGE 배정] 그룹({new_name})의 주문 수가 {unassigned_max_group_volume}건이 되어, [{driver_before['Type']}]에 배정합니다."
                                )

                                group_centroids = recalc_group_centroids(
                                    df_shipping_region
                                )
                                if leftover_orange <= 0:
                                    print(
                                        "[ORANGE 4차 재배정] 더 이상 오렌지 버니가 없습니다. 재배정 중단."
                                    )
                                    break
                        else:
                            print(
                                f"이동할 수 있는 물량이 부족해 종료, 필요물량: {needed}, 가져올 수 있는 물량:{move_count}"
                            )

            # -------------------------------------------------
            # 근접 그룹 드라이버 타입이 ORANGE 일 때
            # -------------------------------------------------
            elif nearest_driver_type == "ORANGE":
                if nearest_volume < 20:
                    print(
                        f"근접 그룹 {nearest_group}의 물량이 20 미만({nearest_volume}건)이라 unassigned_max_group 에 데이터를 가져올 수 없습니다. 종료합니다."
                    )
                    break
                else:
                    print(
                        f"근접 그룹 {nearest_group}의 driver_type이 Orange입니다. unassigned_max_group 의 물량이 20~30이 될 때까지 데이터 이동 시도합니다."
                    )

                    # A) unassigned_max_group < 20
                    if volume < 20:
                        needed = 20 - volume
                        available = nearest_volume - 20
                        move_count = min(needed, available)

                        if needed > available:
                            print("이동할 데이터가 없으므로, [O 4차 재배정] 종료.")
                            break

                        temp = nearest_orders.copy()
                        unassigned_points = df_shipping_region[
                            df_shipping_region["group"] == unassigned_max_group
                        ][["lat", "lng"]]
                        temp["dist_to_A"] = temp.apply(
                            lambda row: min_dist_to_group(row, unassigned_points),
                            axis=1,
                        )
                        temp.sort_values("dist_to_A", inplace=True)
                        orders_to_move = temp.head(move_count)
                        print(
                            f"unassigned_max_group 에 이동할 주문 수: {len(orders_to_move)}"
                        )

                        move_orders(
                            df_shipping_region,
                            orders_to_move.index,
                            unassigned_max_group,
                            clear_driver=True,
                        )
                        unassigned_max_group_volume = df_shipping_region[
                            df_shipping_region["group"] == unassigned_max_group
                        ]["shipping_uuid"].count()
                        nearest_volume = df_shipping_region[
                            df_shipping_region["group"] == nearest_group
                        ]["shipping_uuid"].count()
                        print(
                            f"이동 후, unassigned_group({unassigned_max_group})={unassigned_max_group_volume}건, nearest_group({nearest_group})={nearest_volume}건"
                        )

                        if unassigned_max_group_volume >= 20:
                            if assigned_orange < len(orange_drivers):
                                driver_before = orange_drivers.iloc[assigned_orange]
                                new_name = f"{unassigned_max_group}_O"

                                # 그룹명 교체
                                df_shipping_region.loc[
                                    df_shipping_region["group"] == unassigned_max_group,
                                    "group",
                                ] = new_name

                                # 드라이버 배정
                                df_shipping_region, assigned_orange, leftover_orange = (
                                    assign_driver_to_group(
                                        df_shipping_region,
                                        new_name,
                                        orange_drivers,
                                        assigned_orange,
                                        leftover_orange,
                                        label="ORANGE",
                                    )
                                )
                                print(
                                    f"[4차 ORANGE 배정] A 그룹({new_name})의 주문 수가 {unassigned_max_group_volume}건이 되어, [{driver_before['Type']}]에 배정합니다."
                                )

                                group_centroids = recalc_group_centroids(
                                    df_shipping_region
                                )
                                if leftover_orange <= 0:
                                    print(
                                        "[ORANGE 4차 재배정] 더 이상 오렌지 버니가 없습니다. 재배정 중단."
                                    )
                                    break
                        else:
                            print(
                                f"이동할 수 있는 물량이 부족해 종료, 필요물량: {needed}, 가져올 수 있는 물량:{move_count}"
                            )

                    # B) unassigned_max_group >= 30
                    elif volume >= 32:
                        needed = volume - 31
                        available = 31 - nearest_volume
                        move_count = min(needed, available)

                        if needed > available:
                            print(
                                "이동할 데이터가 없으므로, [O 4차 재배정]을 종료합니다."
                            )
                            break

                        temp = df_shipping_region[
                            df_shipping_region["group"] == unassigned_max_group
                        ].copy()
                        nearest_points = df_shipping_region[
                            df_shipping_region["group"] == nearest_group
                        ][["lat", "lng"]]
                        temp["dist_to_A"] = temp.apply(
                            lambda r: min_dist_to_group(r, nearest_points), axis=1
                        )
                        temp.sort_values("dist_to_A", inplace=True)

                        orders_to_move = temp.head(move_count)
                        print(f"nearest_group 에 이동할 주문 수: {len(orders_to_move)}")

                        move_orders(
                            df_shipping_region,
                            orders_to_move.index,
                            nearest_group,
                            clear_driver=True,
                        )
                        driver_data = df_shipping_region.loc[
                            (df_shipping_region["group"] == nearest_group)
                            & (df_shipping_region["driver_type"].notna())
                        ].head(1)
                        if not driver_data.empty:
                            assigned_type = driver_data["driver_type"].iloc[0]
                            assigned_code = driver_data["driver_code"].iloc[0]

                            df_shipping_region.loc[
                                orders_to_move.index, "driver_type"
                            ] = assigned_type
                            df_shipping_region.loc[
                                orders_to_move.index, "driver_code"
                            ] = assigned_code

                        unassigned_max_group_volume = df_shipping_region[
                            df_shipping_region["group"] == unassigned_max_group
                        ]["shipping_uuid"].count()
                        nearest_volume = df_shipping_region[
                            df_shipping_region["group"] == nearest_group
                        ]["shipping_uuid"].count()
                        print(
                            f"이동 후, unassigned_group({unassigned_max_group})={unassigned_max_group_volume}건, nearest_group({nearest_group})={nearest_volume}건"
                        )

                        if unassigned_max_group_volume <= 31:
                            if assigned_orange < len(orange_drivers):
                                driver_before = orange_drivers.iloc[assigned_orange]
                                new_name = f"{unassigned_max_group}_O"

                                # 그룹명 교체
                                df_shipping_region.loc[
                                    df_shipping_region["group"] == unassigned_max_group,
                                    "group",
                                ] = new_name

                                # 드라이버 배정
                                df_shipping_region, assigned_orange, leftover_orange = (
                                    assign_driver_to_group(
                                        df_shipping_region,
                                        new_name,
                                        orange_drivers,
                                        assigned_orange,
                                        leftover_orange,
                                        label="ORANGE",
                                    )
                                )
                                print(
                                    f"[4차 ORANGE 배정] 그룹({new_name})의 주문 수가 {unassigned_max_group_volume}건이 되어, [{driver_before['Type']}]에 배정합니다."
                                )

                                group_centroids = recalc_group_centroids(
                                    df_shipping_region
                                )
                                if leftover_orange <= 0:
                                    print(
                                        "[ORANGE 4차 재배정] 더 이상 오렌지 버니가 없습니다. 재배정 중단."
                                    )
                                    break
                        else:
                            print(
                                f"이동할 수 있는 물량이 부족해 종료, 필요물량: {needed}, 가져올 수 있는 물량:{move_count}"
                            )

            else:
                print(
                    f"근접 그룹 {nearest_group}의 driver_type({nearest_driver_type})에 대해 정의된 로직이 없습니다."
                )
        else:
            print("미배정 그룹 외에 다른 그룹이 없습니다.")

    used_drivers_idx = list(non_orange_drivers.index[:assigned_non_orange]) + list(
        orange_drivers.index[:assigned_orange]
    )
    leftover_driver_df = fix_region_workflow_day_bunny_df.drop(used_drivers_idx)

    return df_shipping_region, leftover_driver_df

import numpy as np
import pandas as pd

from ..common import (
    assign_driver_to_group,
    in_range,
    min_dist_to_group,
    move_orders,
    recalc_group_centroids,
    split_group_kmeans_2clusters,
)

# Y/R 은 merged_df_norm에서 나온 결과값그대로
# O는 31건

class AssignDriversHandler:
    def __init__(self):
        self.init = None

    # 신규
    def assign_fixed_drivers(
        self, df_shipping_region, fix_region_workflow_day_bunny_df, merged_df_norm
    ):
        def pick_target_by_distance(cnt_a, cnt_b, la, lb, target):
            """white에서 쓰던 로직과 동일: target에 더 가까운 클러스터를 타깃으로."""
            da = abs(cnt_a - target)
            db = abs(cnt_b - target)
            if da < db:
                return la, lb
            elif db < da:
                return lb, la
            else:
                # 거리 동률이면, (1) target 이하인 쪽 우선, (2) 둘 다 같은쪽이면 크기로 결정(덜 움직이는 쪽)
                if cnt_a <= target < cnt_b:
                    return la, lb
                if cnt_b <= target < cnt_a:
                    return lb, la
                # 안전 fallback
                return (min(la, lb), max(la, lb))
            
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

        # Y/R count 계산 + 방어 로직
        
        # 디폴트
        yr_count = 35
        if merged_df_norm is not None and not merged_df_norm.empty:
            try:
                # 컬럼 안전 접근
                cols_lower = {c.lower(): c for c in merged_df_norm.columns}
                col_max   = cols_lower.get('max_shipping_update', 'max_shipping_update')
                col_deliv = cols_lower.get('deliveries', 'deliveries')

                # 숫자 변환
                max_ship_s = pd.to_numeric(merged_df_norm[col_max], errors='coerce')
                deliv_s    = pd.to_numeric(merged_df_norm[col_deliv], errors='coerce')

                # 대표값(전체 최댓값) 선택
                max_ship_raw = max_ship_s.max(skipna=True)
                deliv_raw    = deliv_s.max(skipna=True)

                # deliveries 값 검증
                if pd.isna(deliv_raw):
                    print("deliveries 값이 유효하지 않음 → yr_count=35(디폴트)")
                else:
                    deliveries_val = int(deliv_raw)

                    # (A) 배송량 자체가 35 미만이면: 한 배치로 처리 → 35 유지
                    if deliveries_val < 35:
                        yr_count = 35
                        print(f"deliveries={deliveries_val} < 35 → yr_count=35(디폴트)")

                    else:
                        # max_shipping_update 검증
                        if pd.isna(max_ship_raw):
                            max_ship_raw = None
                        else:
                            max_ship_raw = int(max_ship_raw)

                        # (B) max_shipping_update 유효성/하한 적용
                        if (max_ship_raw is None) or (max_ship_raw <= 0):
                            yr_count = 35
                            print(f"max_shipping_update 값이 유효하지 않음({max_ship_raw}) → yr_count=35(디폴트)")
                        elif max_ship_raw < 35:
                            yr_count = 35
                            print(f"max_shipping_update={max_ship_raw} < 35 → yr_count=35(디폴트)")
                        else:
                            # ✅ 분할 목적: deliveries와 비교하지 않고 max_shipping_update 그대로 사용
                            yr_count = max_ship_raw
                            print(f"분할기준 max_shipping_update={max_ship_raw} 적용 → yr_count={yr_count}")

            except KeyError:
                print("컬럼 'max_shipping_update' 또는 'deliveries' 없음 → yr_count=35(디폴트)")
                yr_count = 35
            except (IndexError, ValueError, TypeError):
                print("값 추출/변환 중 예외 → yr_count=35(디폴트)")
                yr_count = 35
        else:
            print('해당 지역 데이터 없음 → yr_count=35(디폴트)')

        print(f'해당 지역 yr_count {yr_count}로 배정')
        # 1차 배정
        # (A) YELLOW/RAINBOW 배정: 그룹 주문 수 yr_count 건인 그룹
        group_counts = df_shipping_region.groupby("group")["shipping_uuid"].count()
        yellow_rainbow_groups = group_counts[(group_counts == yr_count)].index

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

        # (B) ORANGE 배정: 그룹 주문 수 31건인 그룹
        group_counts = df_shipping_region.groupby("group")["shipping_uuid"].count()
        orange_groups = group_counts[(group_counts == 31)].index

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
            
            group_counts = unassigned_df.groupby("group")["shipping_uuid"].count().sort_values(ascending=False)
            
            extra_unassigned_max_groups = group_counts.index.tolist()

            print(f"배정되지 않은 그룹 {extra_unassigned_max_groups}")
            print(f"[Y/R 2차 재배정] 남은 Y/R 버니: {leftover_non_orange}명")

            if not extra_unassigned_max_groups:
                break

            for grp in extra_unassigned_max_groups:
                if leftover_non_orange <= 0:
                    stop_all = True
                    break
                current_group = grp
                current_count = df_shipping_region[df_shipping_region["group"] == current_group].shape[0]

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

                print(
                    f"  → 그룹 [{current_group}] 클러스터 결과: "
                    f"{label_a}({cluster_counts[label_a]}건), {label_b}({cluster_counts[label_b]}건)"
                )

                 # ✅ 앵커 선택: yr_count에 더 가까운 클러스터를 타깃으로
                target_label, other_label = pick_target_by_distance(
                    cluster_counts[label_a], cluster_counts[label_b], label_a, label_b, yr_count
                )
                print(f"  → 타깃(앵커): {target_label}, 기타: {other_label} (목표={yr_count})")
                
                # 타깃을 yr_count로 맞추는 최소 이동 루프
                while True:
                    vc = grp_orders["cluster"].value_counts()
                    # 소멸 가드
                    if (target_label not in vc.index) or (other_label not in vc.index):
                        print("  → 타깃/기타 중 한 클러스터가 사라져서 종료")
                        break

                    cnt_target = int(vc.get(target_label, 0))
                    cnt_other  = int(vc.get(other_label, 0))

                    if cnt_target == yr_count:
                        print(f"  → 타깃 {target_label}이 목표 {yr_count}건에 도달")
                        break

                    # 타깃 부족: other → target 이동
                    if cnt_target < yr_count:
                        deficit = yr_count - cnt_target
                        if cnt_other == 0:
                            print("  → 기타 클러스터에 주문이 없어 타깃 보충 불가 → 종료")
                            break

                        donor_orders = grp_orders[grp_orders["cluster"] == other_label].copy()
                        target_points = grp_orders[grp_orders["cluster"] == target_label][["lat", "lng"]]
                        donor_orders["dist_to_target"] = donor_orders.apply(
                            lambda row: min_dist_to_group(row, target_points), axis=1
                        )
                        donor_orders.sort_values("dist_to_target", inplace=True)
                        move_n = min(deficit, len(donor_orders))
                        indices_to_move = donor_orders.index[:move_n]

                        print(f"  → 타깃 부족 {deficit}건: 기타→타깃 {move_n}건 이동")
                        move_orders(
                            df_shipping_region,
                            indices_to_move,
                            current_group,
                            clear_driver=True,
                        )
                        grp_orders.loc[indices_to_move, "cluster"] = target_label

                    # 타깃 초과: target → other 이동
                    else:
                        surplus = cnt_target - yr_count
                        donor_orders = grp_orders[grp_orders["cluster"] == target_label].copy()
                        other_points = grp_orders[grp_orders["cluster"] == other_label][["lat", "lng"]]
                        donor_orders["dist_to_other"] = donor_orders.apply(
                            lambda row: min_dist_to_group(row, other_points), axis=1
                        )
                        donor_orders.sort_values("dist_to_other", inplace=True)
                        indices_to_move = donor_orders.index[:surplus]

                        print(f"  → 타깃 초과 {surplus}건: 타깃→기타 {len(indices_to_move)}건 이동")
                        move_orders(
                            df_shipping_region,
                            indices_to_move,
                            current_group,
                            clear_driver=True,
                        )
                        grp_orders.loc[indices_to_move, "cluster"] = other_label

                    vc2 = grp_orders["cluster"].value_counts()
                    print(f"  → 이동 후 분포: {vc2.to_dict()}")

                # 최종 확인: 타깃이 정확히 yr_count면 Y/R 그룹 확정
                final_counts = grp_orders["cluster"].value_counts()
                final_cnt_target = int(final_counts.get(target_label, 0))
                if final_cnt_target == yr_count:
                    base_name = current_group.split("_cluster")[0]
                    yr_group_counter.setdefault(base_name, 0)
                    yr_group_counter[base_name] += 1

                    new_grp_label_target = f"{base_name}_cluster_Y/R_{yr_group_counter[base_name]}"
                    new_grp_label_other  = f"{current_group}_remaining"

                    indices_target = grp_orders[grp_orders["cluster"] == target_label].index
                    indices_other  = grp_orders[grp_orders["cluster"] == other_label].index

                    # 그룹 이동
                    move_orders(
                        df_shipping_region,
                        indices_target,
                        new_grp_label_target,
                        clear_driver=False,
                    )
                    move_orders(
                        df_shipping_region,
                        indices_other,
                        new_grp_label_other,
                        clear_driver=False,
                    )

                    if assigned_non_orange < len(non_orange_drivers):
                        driver_before = non_orange_drivers.iloc[assigned_non_orange]
                        df_shipping_region, assigned_non_orange, leftover_non_orange = (
                            assign_driver_to_group(
                                df_shipping_region,
                                new_grp_label_target,
                                non_orange_drivers,
                                assigned_non_orange,
                                leftover_non_orange,
                                label="Y/R",
                            )
                        )
                        print(
                            f"[Y/R 2차 재배정] 그룹[{new_grp_label_target}] (약 {final_cnt_target}건) → [{driver_before['Type']}] 배정"
                        )

                        group_centroids = recalc_group_centroids(df_shipping_region)
                        if leftover_non_orange <= 0:
                            print("[Y/R 2차 재배정] 더 이상 Y/R 버니가 없습니다. 배정 중단.")
                            break
                    else:
                        print("[Y/R 2차 재배정] 배정 가능한 Y/R 버니가 더 이상 없습니다.")
                        break

                print(
                    "[Y/R 2차 재배정] 후 그룹별 물량:\n",
                    df_shipping_region.groupby("group")["shipping_uuid"].count(),
                )

                if leftover_non_orange <= 0:
                    stop_all = True
                    break

            if stop_all:
                break

            leftover_non_orange = len(non_orange_drivers) - assigned_non_orange
            print(f"[Y/R 2차 재배정] 남은 Y/R 버니: {leftover_non_orange}명")

            if stop_all:
                break

        print("[Y/R 2차 재배정] 로직 완료 or 버니 부족")

        # 2차 배정: ORANGE 2차 재배정 (목표 31건)
        print("### [O 2차 재배정] ###")
        stop_all = False
        o_group_counter = {}
        ORANGE_TARGET = 31  # ✅ 오렌지 목표 건수

        for _ in range(len(orange_drivers)):
            if leftover_orange <= 0:
                stop_all = True
                break

            unassigned_df = df_shipping_region[df_shipping_region["driver_type"].isna()]
            group_counts = unassigned_df.groupby("group")["shipping_uuid"].count().sort_values(ascending=False)
            candidate_groups = group_counts.index.tolist()

            for grp in candidate_groups:
                if leftover_orange <= 0:
                    stop_all = True
                    break

                current_group = grp
                grp_orders = df_shipping_region[df_shipping_region["group"] == current_group].copy()
                current_count = grp_orders.shape[0]
                print(f"[O 2차 재배정] 그룹 [{current_group}] (주문수: {current_count})에서 클러스터 추출 시도")

                # 총량이 목표보다 작으면 분리 불가
                if current_count < ORANGE_TARGET:
                    print(f"  → 총 {current_count}건 < 목표 {ORANGE_TARGET}건 → 분리 불가, 스킵")
                    continue

                # 2-클러스터 분할
                grp_orders, cluster_counts_res, label_a, count_a, label_b, count_b = (
                    split_group_kmeans_2clusters(df_shipping_region, current_group)
                )
                if len(cluster_counts_res) < 2 or label_b is None:
                    continue

                cluster_counts = cluster_counts_res
                print(
                    f"  → 그룹 [{current_group}] 클러스터 결과: "
                    f"{label_a}({cluster_counts[label_a]}건), {label_b}({cluster_counts[label_b]}건)"
                )

                # ✅ 앵커 선택: 31에 더 가까운 클러스터를 타깃으로
                target_label, other_label = pick_target_by_distance(
                    cluster_counts[label_a], cluster_counts[label_b], label_a, label_b, ORANGE_TARGET
                )
                print(f"  → 타깃(앵커): {target_label}, 기타: {other_label} (목표={ORANGE_TARGET})")

                # 타깃을 31로 맞추는 최소 이동 루프
                while True:
                    vc = grp_orders["cluster"].value_counts()
                    if (target_label not in vc.index) or (other_label not in vc.index):
                        print("  → 타깃/기타 중 한 클러스터가 사라져서 종료")
                        break

                    cnt_target = int(vc.get(target_label, 0))
                    cnt_other  = int(vc.get(other_label, 0))

                    if cnt_target == ORANGE_TARGET:
                        print(f"  → 타깃 {target_label}이 목표 {ORANGE_TARGET}건에 도달")
                        break

                    if cnt_target < ORANGE_TARGET:
                        deficit = ORANGE_TARGET - cnt_target
                        if cnt_other == 0:
                            print("  → 기타 클러스터에 주문이 없어 타깃 보충 불가 → 종료")
                            break

                        donor_orders = grp_orders[grp_orders["cluster"] == other_label].copy()
                        target_points = grp_orders[grp_orders["cluster"] == target_label][["lat", "lng"]]
                        donor_orders["dist_to_target"] = donor_orders.apply(
                            lambda row: min_dist_to_group(row, target_points), axis=1
                        )
                        donor_orders.sort_values("dist_to_target", inplace=True)
                        move_n = min(deficit, len(donor_orders))
                        indices_to_move = donor_orders.index[:move_n]

                        print(f"  → 타깃 부족 {deficit}건: 기타→타깃 {move_n}건 이동")
                        # 드라이버 초기화만 수행(그룹명 유지) — Y/R과 동일 패턴
                        move_orders(
                            df_shipping_region,
                            indices_to_move,
                            current_group,
                            clear_driver=True,
                        )
                        grp_orders.loc[indices_to_move, "cluster"] = target_label

                    else:
                        surplus = cnt_target - ORANGE_TARGET

                        donor_orders = grp_orders[grp_orders["cluster"] == target_label].copy()
                        other_points = grp_orders[grp_orders["cluster"] == other_label][["lat", "lng"]]
                        donor_orders["dist_to_other"] = donor_orders.apply(
                            lambda row: min_dist_to_group(row, other_points), axis=1
                        )
                        donor_orders.sort_values("dist_to_other", inplace=True)
                        indices_to_move = donor_orders.index[:surplus]

                        print(f"  → 타깃 초과 {surplus}건: 타깃→기타 {len(indices_to_move)}건 이동")
                        move_orders(
                            df_shipping_region,
                            indices_to_move,
                            current_group,
                            clear_driver=True,
                        )
                        grp_orders.loc[indices_to_move, "cluster"] = other_label

                    vc2 = grp_orders["cluster"].value_counts()
                    print(f"  → 이동 후 분포: {vc2.to_dict()}")

                # 최종 확인: 타깃이 정확히 31건이면 ORANGE 그룹 확정
                final_counts = grp_orders["cluster"].value_counts()
                final_cnt_target = int(final_counts.get(target_label, 0))
                if final_cnt_target == ORANGE_TARGET:
                    base_name = current_group.split("_cluster")[0]
                    o_group_counter.setdefault(base_name, 0)
                    o_group_counter[base_name] += 1

                    new_grp_label_target    = f"{base_name}_cluster_O_{o_group_counter[base_name]}"
                    new_grp_label_remaining = f"{current_group}_remaining"

                    indices_target    = grp_orders[grp_orders["cluster"] == target_label].index
                    indices_remaining = grp_orders[grp_orders["cluster"] == other_label].index

                    # 그룹 이동(최종 라벨링)
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
                            f"[2차 O 재배정] 그룹[{new_grp_label_target}] (주문수: {final_cnt_target}) → [{driver_before['Type']}] 배정"
                        )
                        group_centroids = recalc_group_centroids(df_shipping_region)
                        print(
                            "[2차 O 재배정] 후 그룹별 물량:\n",
                            df_shipping_region.groupby("group")["shipping_uuid"].count(),
                        )

                        if leftover_orange <= 0:
                            print("[2차 O 재배정] 더 이상 배정할 오렌지 버니가 없습니다.")
                            stop_all = True
                            break
                    else:
                        print("[2차 O 재배정] 배정 가능한 오렌지 버니가 더 이상 없습니다.")
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

        used_drivers_idx = list(non_orange_drivers.index[:assigned_non_orange]) + list(orange_drivers.index[:assigned_orange])
        leftover_driver_df = fix_region_workflow_day_bunny_df.drop(used_drivers_idx)

        return df_shipping_region, leftover_driver_df
    
    
                # 큰/작은 클러스터 식별
        #         if cluster_counts.iloc[0] <= cluster_counts.iloc[1]:
        #             smaller_cluster = cluster_counts.index[0]  # ex) label_a
        #             larger_cluster = cluster_counts.index[1]  # ex) label_b
        #         else:
        #             smaller_cluster = cluster_counts.index[1]
        #             larger_cluster = cluster_counts.index[0]

        #             print(
        #                 f"  → 그룹 [{current_group}] 클러스터 결과: "
        #                 f"클러스터 {label_a} ({cluster_counts[label_a]}건), "
        #                 f"클러스터 {label_b} ({cluster_counts[label_b]}건)"
        #             )

        #         current = cluster_counts[larger_cluster]
        #         # 큰 클러스터 y/r_count 미만일때 작은 클러스터에서 주문 건들 이동
        #         if current < yr_count:
        #             deficit = yr_count - current
        #             print(f"  → 부족: {deficit}건 필요")

        #             # smaller 클러스터 주문들
        #             smaller_orders = grp_orders[
        #                 grp_orders["cluster"] == smaller_cluster
        #             ].copy()

        #             larger_points = grp_orders[grp_orders["cluster"] == larger_cluster][
        #                 ["lat", "lng"]
        #             ]
        #             smaller_orders["dist_to_larger"] = smaller_orders.apply(
        #                 lambda row: min_dist_to_group(row, larger_points), axis=1
        #             )
        #             smaller_orders.sort_values("dist_to_larger", inplace=True)
        #             indices_to_move = smaller_orders.index[:deficit]

        #             print(
        #                 f"  → {deficit}건을 smaller 클러스터에서 larger 클러스터로 이동"
        #             )
        #             # driver 컬럼 초기화 후 이동
        #             move_orders(
        #                 df_shipping_region,
        #                 indices_to_move,
        #                 current_group,
        #                 clear_driver=True,
        #             )
        #             grp_orders.loc[indices_to_move, "cluster"] = larger_cluster

        #         elif current > yr_count:
        #             surplus = current - yr_count
        #             print(f"  → 초과: {surplus}건 제거 필요")

        #             larger_orders = grp_orders[
        #                 grp_orders["cluster"] == larger_cluster
        #             ].copy()
        #             smaller_points = grp_orders[
        #                 grp_orders["cluster"] == smaller_cluster
        #             ][["lat", "lng"]]

        #             larger_orders["dist_to_small"] = larger_orders.apply(
        #                 lambda row: min_dist_to_group(row, smaller_points), axis=1
        #             )
        #             larger_orders.sort_values("dist_to_small", inplace=True)
        #             indices_to_move = larger_orders.index[:surplus]

        #             print(f"  → {surplus}건을 큰 클러스터에서 작은 클러스터로 이동")
        #             move_orders(
        #                 df_shipping_region,
        #                 indices_to_move,
        #                 current_group,
        #                 clear_driver=True,
        #             )

        #             grp_orders.loc[indices_to_move, "cluster"] = smaller_cluster

        #         # 다시 갱신된 클러스터 수 체크(실제로는 df_shipping_region 변경)
        #         new_counts_ = grp_orders["cluster"].value_counts()
        #         new_larger_count = new_counts_.get(larger_cluster, 0)
        #         print(
        #             f"  → 조정 후: 큰 클러스터 {larger_cluster} 주문수: {new_larger_count} (목표:{yr_count})"
        #         )

        #         # 만약 정확히 yr_count 이 됐다면 → Y/R 배정
        #         if new_larger_count == yr_count:
        #             base_name = current_group.split("_cluster")[0]
        #             yr_group_counter.setdefault(base_name, 0)
        #             yr_group_counter[base_name] += 1

        #             new_grp_label_large = (
        #                 f"{base_name}_cluster_Y/R_{yr_group_counter[base_name]}"
        #             )
        #             new_grp_label_small = f"{current_group}_remaining"

        #             indices_large = grp_orders[
        #                 grp_orders["cluster"] == larger_cluster
        #             ].index
        #             indices_small = grp_orders[
        #                 grp_orders["cluster"] == smaller_cluster
        #             ].index

        #             # 그룹 이동
        #             move_orders(
        #                 df_shipping_region,
        #                 indices_large,
        #                 new_grp_label_large,
        #                 clear_driver=False,
        #             )
        #             move_orders(
        #                 df_shipping_region,
        #                 indices_small,
        #                 new_grp_label_small,
        #                 clear_driver=False,
        #             )

        #             if assigned_non_orange < len(non_orange_drivers):
        #                 driver_before = non_orange_drivers.iloc[assigned_non_orange]
        #                 df_shipping_region, assigned_non_orange, leftover_non_orange = (
        #                     assign_driver_to_group(
        #                         df_shipping_region,
        #                         new_grp_label_large,
        #                         non_orange_drivers,
        #                         assigned_non_orange,
        #                         leftover_non_orange,
        #                         label="Y/R",
        #                     )
        #                 )
        #                 print(
        #                     f"[Y/R 2차 재배정] 그룹[{new_grp_label_large}] (약 {new_larger_count}건) → [{driver_before['Type']}] 배정"
        #                 )

        #                 group_centroids = recalc_group_centroids(df_shipping_region)
        #                 if leftover_non_orange <= 0:
        #                     print(
        #                         "[Y/R 2차 재배정] 더 이상 Y/R 버니가 없습니다. 배정 중단."
        #                     )
        #                     break
        #             else:
        #                 print(
        #                     "[Y/R 2차 재배정] 배정 가능한 Y/R 버니가 더 이상 없습니다."
        #                 )
        #                 break

        #         print(
        #             "[Y/R 2차 재배정] 후 그룹별 물량:\n",
        #             df_shipping_region.groupby("group")["shipping_uuid"].count(),
        #         )

        #         if leftover_non_orange <= 0:
        #             stop_all = True
        #             break

        #     if stop_all:
        #         break

        #     leftover_non_orange = len(non_orange_drivers) - assigned_non_orange
        #     print(f"[Y/R 2차 재배정] 남은 Y/R 버니: {leftover_non_orange}명")

        #     if stop_all:
        #         break

        # print("[Y/R 2차 재배정] 로직 완료 or 버니 부족")

        # # ---------------------------------------------------------------------------
        # # 2차 배정: ORANGE 2차 재배정
        # print("### [O 2차 재배정] ###")
        # stop_all = False
        # o_group_counter = {}

        # for _ in range(len(orange_drivers)):
        #     if leftover_orange <= 0:
        #         stop_all = True
        #         break

        #     unassigned_df = df_shipping_region[df_shipping_region["driver_type"].isna()]

        #     # 현재 group별 주문 수 집계
        #     group_counts = unassigned_df.groupby("group")["shipping_uuid"].count().sort_values(ascending=False)
            
        #     candidate_groups = group_counts.index.tolist()
        #     for grp in candidate_groups:
        #         if leftover_orange <= 0:
        #             stop_all = True
        #             break
        #         current_group = grp
        #         grp_orders = df_shipping_region[df_shipping_region["group"] == current_group].copy()
        #         current_count = grp_orders.shape[0]
        #         print(
        #             f"[O 2차 재배정] 그룹 [{current_group}] (주문수: {current_count})에서 클러스터 추출 시도"
        #         )

        #         grp_orders, cluster_counts_res, label_a, count_a, label_b, count_b = (
        #             split_group_kmeans_2clusters(df_shipping_region, current_group)
        #         )

        #         # 클러스터가 2개 미만이면 스킵
        #         if len(cluster_counts_res) < 2 or label_b is None:
        #             continue

        #         # 더 편하게 쓰기 위해 local 변수에 재저장
        #         cluster_counts = cluster_counts_res

        #         # --------------------------------------
        #         # [조건5] 그 외 - 부족 / 초과 로직으로 31 맞추기
        #         # --------------------------------------
        #         # 작은/큰 클러스터 식별
        #         if cluster_counts[label_a] <= cluster_counts[label_b]:
        #             small_label, large_label = label_a, label_b
        #         else:
        #             small_label, large_label = label_b, label_a

        #         small_count = cluster_counts[small_label]
        #         large_count = cluster_counts[large_label]

        #         print(
        #             f"  → [조건5] 작은 클러스터={small_label}({small_count}건), 큰 클러스터={large_label}({large_count}건)"
        #         )

        #         # A) 작은 클러스터 < 31 → 큰 쪽에서 가져와 31 맞추기
        #         if small_count < 31:
        #             deficit = 31 - small_count
        #             print(
        #                 f"    → 작은 클러스터 부족 {deficit}건. 큰 클러스터 -> 작은 클러스터 이동"
        #             )

        #             small_cluster_points = grp_orders[
        #                 grp_orders["cluster"] == small_label
        #             ][["lat", "lng"]]
        #             large_orders = grp_orders[
        #                 grp_orders["cluster"] == large_label
        #             ].copy()
        #             large_orders["dist_to_small"] = large_orders.apply(
        #                 lambda row: min_dist_to_group(row, small_cluster_points), axis=1
        #             )
        #             large_orders.sort_values("dist_to_small", inplace=True)
        #             indices_to_move = large_orders.index[:deficit]

        #             # 실제 데이터프레임에 반영
        #             df_shipping_region.loc[
        #                 indices_to_move, ["driver_type", "driver_code"]
        #             ] = np.nan
        #             grp_orders.loc[indices_to_move, "cluster"] = small_label
        #             print(
        #                 f"  → {deficit}건을 대형 클러스터에서 작은 클러스터로 이동 (가장 가까운 순)"
        #             )

        #         # B) 작은 클러스터 >= 32 → 일부를 큰 쪽으로 이동
        #         elif small_count > 31:
        #             surplus = small_count - 31
        #             print(
        #                 f"    → 작은 클러스터 초과 {surplus}건. 작은 클러스터 -> 큰 클러스터 이동"
        #             )

        #             large_cluster_points = grp_orders[
        #                 grp_orders["cluster"] == large_label
        #             ][["lat", "lng"]]
        #             small_orders = grp_orders[
        #                 grp_orders["cluster"] == small_label
        #             ].copy()
        #             small_orders["dist_to_large"] = small_orders.apply(
        #                 lambda row: min_dist_to_group(row, large_cluster_points), axis=1
        #             )
        #             small_orders.sort_values("dist_to_large", inplace=True)
        #             indices_to_move = small_orders.index[:surplus]

        #             df_shipping_region.loc[
        #                 indices_to_move, ["driver_type", "driver_code"]
        #             ] = np.nan
        #             grp_orders.loc[indices_to_move, "cluster"] = large_label
        #             print(f"  → {surplus}건을 작은 클러스터에서 대형 클러스터로 이동")

        #         new_counts = grp_orders["cluster"].value_counts()
        #         new_small_count = new_counts.get(small_label, 0)
        #         print(
        #             f"  → 조정 후 작은 클러스터 {small_label} 주문 수: {new_small_count} (목표:31)"
        #         )

        #         if new_small_count == 31:
        #             base_name = current_group.split("_cluster")[0]
        #             o_group_counter.setdefault(base_name, 0)
        #             o_group_counter[base_name] += 1

        #             new_grp_label_target = (
        #                 f"{base_name}_cluster_O_{o_group_counter[base_name]}"
        #             )
        #             new_grp_label_remaining = f"{current_group}_remaining"

        #             indices_target = grp_orders[
        #                 grp_orders["cluster"] == small_label
        #             ].index
        #             indices_remaining = grp_orders[
        #                 grp_orders["cluster"] == large_label
        #             ].index

        #             # 그룹 이동
        #             move_orders(
        #                 df_shipping_region,
        #                 indices_target,
        #                 new_grp_label_target,
        #                 clear_driver=False,
        #             )
        #             move_orders(
        #                 df_shipping_region,
        #                 indices_remaining,
        #                 new_grp_label_remaining,
        #                 clear_driver=False,
        #             )

        #             if assigned_orange < len(orange_drivers):
        #                 driver_before = orange_drivers.iloc[assigned_orange]
        #                 df_shipping_region, assigned_orange, leftover_orange = (
        #                     assign_driver_to_group(
        #                         df_shipping_region,
        #                         new_grp_label_target,
        #                         orange_drivers,
        #                         assigned_orange,
        #                         leftover_orange,
        #                         label="ORANGE",
        #                     )
        #                 )
        #                 print(
        #                     f"[2차 O 재배정] 그룹[{new_grp_label_target}] (주문수: {new_small_count}) → [{driver_before['Type']}] 배정"
        #                 )
        #                 group_centroids = recalc_group_centroids(df_shipping_region)
        #                 print(
        #                     "[2차 O 재배정] 후 그룹별 물량:\n",
        #                     df_shipping_region.groupby("group")[
        #                         "shipping_uuid"
        #                     ].count(),
        #                 )

        #                 if leftover_orange <= 0:
        #                     print(
        #                         "[2차 O 재배정] 더 이상 배정할 오렌지 버니가 없습니다."
        #                     )
        #                     stop_all = True
        #                     break
        #             else:
        #                 print(
        #                     "[2차 O 재배정] 배정 가능한 오렌지 버니가 더 이상 없습니다."
        #                 )
        #                 break

        #         if leftover_orange <= 0:
        #             print("[2차 O 재배정] 더 이상 오렌지 버니가 없습니다.")
        #             stop_all = True
        #             break

        #     leftover_orange = len(orange_drivers) - assigned_orange
        #     print(f"[O 2차 재배정] 루프 종료, 남은 오렌지 버니: {leftover_orange}")

        #     if stop_all:
        #         break

        # print("[O 2차 재배정] 로직 종료 또는 버니 부족")

        # used_drivers_idx = list(non_orange_drivers.index[:assigned_non_orange]) + list(
        #     orange_drivers.index[:assigned_orange]
        # )
        # leftover_driver_df = fix_region_workflow_day_bunny_df.drop(used_drivers_idx)

        # return df_shipping_region, leftover_driver_df
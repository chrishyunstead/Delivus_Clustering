import numpy as np
import pandas as pd
from ..common import min_dist_to_group, move_orders, split_group_kmeans_2clusters


class WhiteDriversHandler:
    def __init__(self):
        self.init = None

    # ===== [NEW] 모든 그룹 분리 작업이 끝난 뒤, 한 번만 호출하는 후처리 =====
    def merge_tiny_clusters(self, df, min_cluster=5, max_merge_km=4):
        """
        min_cluster 이하의 작은 그룹을, 각 포인트 기준으로
        유클리드 거리(위/경도) 가장 가까운 다른 그룹에 흡수시킨다.
        모든 분리 작업 완료 후 마지막에 한 번만 호출.
        
        max_merge_km: float | None
            병합 허용 반경(km). 최단 후보가 이 거리보다 멀면 해당 포인트는 이동하지 않음.
            None이면 거리 제한 없이 기존 로직대로 병합.
        """
        # --- km -> degree 임계값 계산(간단 근사: 1 deg ≈ 111 km)
        deg_threshold = None
        if max_merge_km is not None:
            try:
                deg_threshold = float(max_merge_km) / 111.0
            except (TypeError, ValueError):
                deg_threshold = None
                print(f"[후처리] max_merge_km={max_merge_km} 해석 실패 → 거리 제한 해제")

        # 현재 그룹별 사이즈
        sizes = df.groupby("group")["shipping_uuid"].count().sort_values()
        tiny_groups = [g for g, sz in sizes.items() if sz <= min_cluster]

        if not tiny_groups:
            print(f"[후처리] 소형({min_cluster} 이하) 클러스터 없음 → 종료")
            return df

        print(f"[후처리] 소형 클러스터: {[(g, int(sizes[g])) for g in tiny_groups]}")

        # ✅ tiny 처리 시작 전에 '초기 멤버' 스냅샷 고정
        members_by_group = {g: df.index[df["group"] == g].tolist() for g in tiny_groups}

        # 그룹별 좌표 뷰
        def group_points(gname):
            return df.loc[df["group"] == gname, ["lat", "lng"]]

        for g in tiny_groups:
            # ✅ 현재 멤버가 아니라 '초기 멤버'만 이동 대상으로 사용
            member_idx = members_by_group.get(g, [])
            if not member_idx:
                continue

            # 병합 후보(자기 자신 제외). 후보가 없으면 스킵
            candidates = [cg for cg in df["group"].unique() if cg != g]
            if not candidates:
                print(f"[후처리] 그룹 {g}: 후보 그룹 없음 → 스킵")
                continue

            assign_map = {}  # tgt_group -> [row_idx,...]
            skipped_far = 0  # 거리 제한 넘겨서 스킵된 포인트 수

            for idx in member_idx:
                row = df.loc[idx, ["lat", "lng"]]
                best_g, best_d = None, np.inf

                for cg in candidates:
                    pts = group_points(cg)
                    d = min_dist_to_group(row, pts)  # (deg 단위) 유클리드 최소거리
                    if pd.notna(d) and d < best_d:
                        best_d, best_g = d, cg

                # --- 경계 제한: 최단 후보가 너무 멀면 이동 스킵
                if best_g is not None:
                    if (deg_threshold is not None) and (best_d > deg_threshold):
                        skipped_far += 1
                        print(f"[후처리] 그룹 {g} 주문 {idx}: {max_merge_km}km 초과, 거리({best_d*111:.2f}km) → 스킵")
                        continue
                    assign_map.setdefault(best_g, []).append(idx)

            moved_total = 0
            for tgt, idxs in assign_map.items():
                # (1) 그룹만 이동
                move_orders(df, idxs, tgt, clear_driver=False)

                # (2) 타깃 그룹에 드라이버가 이미 있으면, 방금 이동한 로우도 그 드라이버로 통일
                tgt_dt = df.loc[df["group"] == tgt, "driver_type"]
                tgt_dc = df.loc[df["group"] == tgt, "driver_code"]

                if tgt_dt.notna().any():
                    majority_type = tgt_dt.dropna().mode().iloc[0]
                    df.loc[idxs, "driver_type"] = majority_type

                    if tgt_dc.notna().any():
                        majority_code = tgt_dc.dropna().mode().iloc[0]
                        df.loc[idxs, "driver_code"] = majority_code

                moved_total += len(idxs)
                print(f"[후처리] {g} → {tgt} : {len(idxs)}건 이동")

            if skipped_far > 0:
                print(f"[후처리] 그룹 {g}: 거리 제한으로 이동 스킵 {skipped_far}건"
                    + (f" (max_merge_km={max_merge_km})" if max_merge_km is not None else ""))

            print(f"[후처리] 그룹 {g} 병합 완료 (총 {moved_total}건 이동)")

        final_sizes = df.groupby("group")["shipping_uuid"].count().sort_values()
        print(f"[후처리] 최종 그룹 사이즈: {final_sizes.to_dict()}")

        return df

    def isolate_white_clusters(self, df, group_name, merged_df_norm):
        iteration = 1
        group_stack = [group_name]  # 처리할 그룹을 스택에 저장
        
        # white_count 계산 + 방어 로직
        
        # 디폴트
        white_count = 35
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
                    print("deliveries 값이 유효하지 않음 → white_count=35(디폴트)")
                else:
                    deliveries_val = int(deliv_raw)

                    # (A) 배송량 자체가 35 미만이면: 한 배치로 처리 → 35 유지
                    if deliveries_val < 35:
                        white_count = 35
                        print(f"deliveries={deliveries_val} < 35 → white_count=35(디폴트)")

                    else:
                        # max_shipping_update 검증
                        if pd.isna(max_ship_raw):
                            max_ship_raw = None
                        else:
                            max_ship_raw = int(max_ship_raw)

                        # (B) max_shipping_update 유효성/하한 적용
                        if (max_ship_raw is None) or (max_ship_raw <= 0):
                            white_count = 35
                            print(f"max_shipping_update 값이 유효하지 않음({max_ship_raw}) → white_count=35(디폴트)")
                        elif max_ship_raw < 35:
                            white_count = 35
                            print(f"max_shipping_update={max_ship_raw} < 35 → white_count=35(디폴트)")
                        else:
                            # ✅ 분할 목적: del. iveries와 비교하지 않고 max_shipping_update 그대로 사용
                            white_count = max_ship_raw
                            print(f"분할기준 max_shipping_update={max_ship_raw} 적용 → white_count={white_count}")

            except KeyError:
                print("컬럼 'max_shipping_update' 또는 'deliveries' 없음 → white_count=35(디폴트)")
                white_count = 35
            except (IndexError, ValueError, TypeError):
                print("값 추출/변환 중 예외 → white_count=35(디폴트)")
                white_count = 35
        else:
            print('해당 지역 데이터 없음 → white_count=35(디폴트)')

        print(f'해당 지역 WHITE {white_count}로 배정')

        while group_stack:
            current_group = group_stack.pop()
            group_orders = df[df["group"] == current_group].copy()
            total_count = group_orders["shipping_uuid"].count()

            # (1) white_count건 미만이면 화이트 처리 중단
            if total_count < white_count:
                print(
                    f"그룹 {current_group}의 주문 수가 {total_count}건으로 {white_count}미만이어서 추가 분리 종료"
                )
                continue

            grp_orders, cluster_counts, label_a, count_a, label_b, count_b = (
                split_group_kmeans_2clusters(df, current_group)
            )
            if len(cluster_counts) < 2 or label_b is None:
                print("클러스터가 2개 미만이라 스킵")
                continue

            print(f"클러스터링 결과: {cluster_counts.to_dict()}")
            group_orders["cluster"] = grp_orders["cluster"]

            # ------------------------------------------------------------
            # ✅ 변경 핵심: white_count에 '더 가까운' 클러스터를 앵커(타깃)로 선정
            # ------------------------------------------------------------
            def pick_target_by_distance(cnt_a, cnt_b, la, lb, target):
                da = abs(cnt_a - target)
                db = abs(cnt_b - target)
                if da < db:
                    return la, lb  # target, other
                elif db < da:
                    return lb, la
                else:
                    # 거리 동률이면, (1) target 이하인 쪽 우선, (2) 최종적으로 라벨 정렬 안정화
                    if cnt_a <= target < cnt_b:
                        return la, lb
                    if cnt_b <= target < cnt_a:
                        return lb, la
                    # 둘 다 같은 쪽(둘 다 <= 또는 둘 다 >)이면 라벨 정렬로 결정
                    return (min(la, lb), max(la, lb))

            target_label, other_label = pick_target_by_distance(
                count_a, count_b, label_a, label_b, white_count
            )
            print(f"타깃(앵커) 클러스터: {target_label}, 기타 클러스터: {other_label} (white_count={white_count})")

            # ------------------------------------------------------------

            while True:
                # 현재 분포 파악
                vc = group_orders["cluster"].value_counts()

                if len(vc) < 2:
                    print("클러스터 수가 1개로 붕괴 -> 조정 중단")
                    break

                # 타깃/기타 라벨이 바뀌었거나 사라졌을 수 있으니 보정
                labels_now = list(vc.index)
                if target_label not in labels_now or other_label not in labels_now:
                    print("타깃/기타 중 한 클러스터가 사라져서 종료")
                    break

                cnt_target = int(vc.get(target_label, 0))
                cnt_other  = int(vc.get(other_label, 0))
                print(f"타깃 클러스터 건수: {cnt_target}, 기타 클러스터 건수: {cnt_other}")
                
                if cnt_target == white_count:
                    print(f"타깃 클러스터가 white_count={white_count}에 도달")
                    break

                # 타깃이 부족하면(other -> target), 넘치면(target -> other)
                if cnt_target < white_count:
                    deficit = white_count - cnt_target
                    # other에서 target으로 '가까운' 데이터 이동
                    donor_orders = group_orders[group_orders['cluster'] == other_label].copy()
                    if donor_orders.empty:
                        print("기타 클러스터에 이동 가능한 주문이 없어 종료")
                        break

                    target_df = group_orders[group_orders['cluster'] == target_label][["lat","lng"]]
                    donor_orders['dist_to_target'] = donor_orders.apply(
                        lambda row: min_dist_to_group(row, target_df),
                        axis=1
                    )
                    donor_orders.sort_values('dist_to_target', ascending=True, inplace=True)
                    move_count = min(deficit, len(donor_orders))
                    orders_to_move = donor_orders.head(move_count)

                    if len(orders_to_move) == 0:
                        print("이동할 주문이 없어 추가 조정 불가능")
                        break

                    group_orders.loc[orders_to_move.index, 'cluster'] = target_label
                    print(f"타깃 부족 {deficit}건 → 기타→타깃 {move_count}건 이동")

                else:
                    surplus = cnt_target - white_count
                    # target에서 other로 'other에 가까운' 데이터 이동
                    donor_orders = group_orders[group_orders['cluster'] == target_label].copy()
                    if donor_orders.empty:
                        print("타깃 클러스터에 이동 가능한 주문이 없어 종료")
                        break

                    other_df = group_orders[group_orders['cluster'] == other_label][["lat","lng"]]
                    donor_orders['dist_to_other'] = donor_orders.apply(
                        lambda row: min_dist_to_group(row, other_df),
                        axis=1
                    )
                    donor_orders.sort_values('dist_to_other', ascending=True, inplace=True)
                    orders_to_move = donor_orders.head(surplus)

                    if len(orders_to_move) == 0:
                        print("이동할 주문이 없어 추가 조정 불가능")
                        break

                    group_orders.loc[orders_to_move.index, 'cluster'] = other_label
                    print(f"타깃 초과 {surplus}건 → 타깃→기타 {len(orders_to_move)}건 이동")


                # 이동 후 분포 출력
                vc2 = group_orders["cluster"].value_counts()
                print(f"이동 후 클러스터 분포: {vc2.to_dict()}")


                # 라벨 소멸 시 종료
                if (target_label not in vc2.index) or (other_label not in vc2.index):
                    vanished = "target_label" if (target_label not in vc2.index) else "other_label"
                    print(f"{vanished} 클러스터가 사라져서 종료")
                    break


            # ------------------------------------------------------------
            # 타깃이 정확히 white_count면 화이트 그룹 확정
            # ------------------------------------------------------------
            final_counts = group_orders["cluster"].value_counts()
            final_cnt_target = int(final_counts.get(target_label, 0))
            if final_cnt_target == white_count:
                new_white_group = f"{current_group}_WHITE_{iteration}"
                idx_white = group_orders[group_orders["cluster"] == target_label].index

                move_orders(df, idx_white, new_white_group, clear_driver=False)
                print(
                    f"[화이트 분리 완료] 그룹 {new_white_group} {white_count}건 생성, driver_type='WHITE'로 업데이트"
                )

                iteration += 1

                # 나머지(기타 클러스터) 처리
                if other_label in group_orders["cluster"].unique():
                    idx_remaining = group_orders[group_orders["cluster"] == other_label].index
                    remaining_count = df.loc[idx_remaining, "shipping_uuid"].count()
                    if remaining_count < white_count:
                        print(
                            f"남은 그룹의 주문 수가 {remaining_count}건으로 {white_count}미만이어서 추가 분리 종료"
                        )
                        continue

                    new_remaining_group = f"{current_group}_R"
                    move_orders(df, idx_remaining, new_remaining_group, clear_driver=False)
                    print(
                        f"남은 주문 {remaining_count}건은 그룹 {new_remaining_group}로 업데이트"
                    )

                    # 스택에 새 그룹 push → 다음 while loop에서 처리
                    group_stack.append(new_remaining_group)
                else:
                    print("남은(other) 클러스터가 없어 추가 처리 스킵")

            else:
                print(
                    f"화이트 분리 불가: 타깃 클러스터가 {white_count}건이 아닙니다. (현재 {final_cnt_target}건)"
                )
                continue

        return df
        
        # while group_stack:
        #     current_group = group_stack.pop()
        #     group_orders = df[df["group"] == current_group].copy()
        #     total_count = group_orders["shipping_uuid"].count()

        #     # (1) white_count건 미만이면 화이트 처리 중단
        #     if total_count < white_count:
        #         print(
        #             f"그룹 {current_group}의 주문 수가 {total_count}건으로 {white_count}미만이어서 추가 분리 종료"
        #         )
        #         continue

        #     grp_orders, cluster_counts, label_a, count_a, label_b, count_b = (
        #         split_group_kmeans_2clusters(df, current_group)
        #     )
        #     if len(cluster_counts) < 2 or label_b is None:
        #         print("클러스터가 2개 미만이라 스킵")
        #         continue

        #     print(f"클러스터링 결과: {cluster_counts.to_dict()}")
        #     group_orders["cluster"] = grp_orders["cluster"]

        #     if count_a < count_b:
        #         label_small, label_large = label_a, label_b
        #     elif count_a > count_b:
        #         label_small, label_large = label_b, label_a
        #     else:
        #         print("두 클러스터 사이즈 동일 -> 강제로 label_small=0, label_large=1")
        #         sorted_idx = sorted(cluster_counts.index)
        #         label_small, label_large = sorted_idx[0], sorted_idx[1]

        #     while True:
        #         cluster_counts2 = group_orders["cluster"].value_counts()
        #         if len(cluster_counts2) < 2:
        #             print("클러스터 수가 1개로 붕괴 -> 조정 중단")
        #             break

        #         la = cluster_counts2.index[0]
        #         ca = cluster_counts2.iloc[0]
        #         lb = cluster_counts2.index[1]
        #         cb = cluster_counts2.iloc[1]

        #         if ca < cb:
        #             label_small, label_large = la, lb
        #         elif ca > cb:
        #             label_small, label_large = lb, la
        #         else:
        #             print("작은/큰 클러스터 사이즈 동일 -> tie-break")
        #             sorted_idx = sorted(cluster_counts2.index)
        #             label_small, label_large = sorted_idx[0], sorted_idx[1]

        #         count_small = cluster_counts2[label_small]
        #         count_large = cluster_counts2[label_large]

        #         if count_large == white_count:
        #             break
        #         # 작은 클러스터의 중심점에서 가까운 데이터들 옮기기
        #         elif count_large < white_count:
        #             deficit = white_count - count_large
        #             available = count_small - deficit
        #             if available <= 0:
        #                 print(
        #                     f"조정 불가: 작은 클러스터({label_large})에 여분 주문이 없어 이동 불가"
        #                 )
        #                 break
        #             # move_count=deficit
        #             move_count = min(deficit, available)
        #             print(
        #                 f"큰 클러스터 부족: {deficit}건, 작은 클러스터에서 {move_count}건 이동 시도"
        #             )
        #             donor_orders = group_orders[group_orders['cluster'] == label_small].copy()
        #             large_cluster_df = group_orders[group_orders['cluster'] == label_large][["lat","lng"]]

        #             donor_orders['dist_to_large'] = donor_orders.apply(
        #                 lambda row: min_dist_to_group(row, large_cluster_df),
        #                 axis=1
        #             )
        #             donor_orders.sort_values('dist_to_large', ascending=True, inplace=True)
        #             orders_to_move = donor_orders.head(move_count)

        #             if len(orders_to_move) == 0:
        #                 print("이동할 주문이 없어 추가 조정 불가능")
        #                 break

        #             group_orders.loc[orders_to_move.index, 'cluster'] = label_large

        #         else:
        #             surplus = count_large - white_count
        #             print(f"큰 클러스터 초과: {surplus}건, 작은 클러스터로 이동 시도")

        #             donor_orders = group_orders[group_orders['cluster'] == label_large].copy()
        #             small_cluster_df = group_orders[group_orders['cluster'] == label_small][["lat","lng"]]

        #             donor_orders['dist_to_small'] = donor_orders.apply(
        #                 lambda row: min_dist_to_group(row, small_cluster_df),
        #                 axis=1
        #             )
        #             donor_orders.sort_values('dist_to_small', ascending=True, inplace=True)
        #             orders_to_move = donor_orders.head(surplus)

        #             if len(orders_to_move) == 0:
        #                 print("이동할 주문이 없어 추가 조정 불가능")
        #                 break

        #             group_orders.loc[orders_to_move.index, 'cluster'] = label_small


        #         cluster_counts2 = group_orders["cluster"].value_counts()
        #         print(f"이동 후 클러스터 분포: {cluster_counts2.to_dict()}")

        #         # 존재 여부는 index로 확인, 어느 쪽이든 사라지면 중단
        #         if (label_large not in cluster_counts2.index) or (label_small not in cluster_counts2.index):
        #             vanished = "label_large" if (label_large not in cluster_counts2.index) else "label_small"
        #             print(f"{vanished} 클러스터가 사라져서 종료")
        #             break

        #         count_large = cluster_counts2.get(label_large, 0)
        #         if count_large == white_count:
        #             break

        #     # 큰 클러스터가 white_count건이면 화이트로 확정
        #     final_count_large = group_orders["cluster"].value_counts().get(label_large, 0)
        #     if final_count_large == white_count:
        #         new_white_group = f"{current_group}_WHITE_{iteration}"
        #         idx_white = group_orders[group_orders["cluster"] == label_large].index

        #         move_orders(df, idx_white, new_white_group, clear_driver=False)
        #         print(
        #             f"[화이트 분리 완료] 그룹 {new_white_group} {white_count}건 생성, driver_type='WHITE'로 업데이트"
        #         )

        #         iteration += 1

        #         # 나머지(큰 클러스터) 처리
        #         idx_remaining = group_orders[group_orders["cluster"] == label_small].index
        #         remaining_count = df.loc[idx_remaining, "shipping_uuid"].count()
        #         if remaining_count < white_count:
        #             print(
        #                 f"남은 그룹의 주문 수가 {remaining_count}건으로 {white_count}미만이어서 추가 분리 종료"
        #             )
        #             continue

        #         new_remaining_group = f"{current_group}_R"
        #         move_orders(df, idx_remaining, new_remaining_group, clear_driver=False)
        #         print(
        #             f"남은 주문 {remaining_count}건은 그룹 {new_remaining_group}로 업데이트"
        #         )

        #         # 스택에 새 그룹 push → 다음 while loop에서 처리
        #         group_stack.append(new_remaining_group)

        #     else:
        #         print(
        #             f"화이트 분리 불가: 큰 클러스터가 {white_count}건이 아닙니다. (현재 {final_count_large}건)"
        #         )
        #         continue
        # return df
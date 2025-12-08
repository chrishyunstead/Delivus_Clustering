import numpy as np

from ..common import min_dist_to_group, move_orders, split_group_kmeans_2clusters


class WhiteDriversHandler:
    def __init__(self):
        self.init = None

    def isolate_white_clusters(self, df, group_name):
        iteration = 1
        group_stack = [group_name]  # 처리할 그룹을 스택에 저장

        while group_stack:
            current_group = group_stack.pop()
            group_orders = df[df["group"] == current_group].copy()
            total_count = group_orders["shipping_uuid"].count()

            if total_count >= 60:
                print(f"{current_group}의 주문 수가 {total_count}건")
                
            # (1) 40건 미만이면 화이트 처리 중단
            if total_count < 40:
                print(
                    f"그룹 {current_group}의 주문 수가 {total_count}건으로 40 미만이어서 추가 분리 종료"
                )
                continue

            if 40 <= total_count < 45:
                print(f"{total_count}건 이므로 한 클러스터 20으로 조정")

                grp_orders, cluster_counts, label_a, count_a, label_b, count_b = (
                    split_group_kmeans_2clusters(df, current_group)
                )

                if len(cluster_counts) < 2 or label_b is None:
                    print("클러스터가 2개 미만이거나 하나뿐이어서 처리 불가, 계속 진행")
                    continue

                print(f"클러스터링 결과: {cluster_counts.to_dict()}")
                group_orders["cluster"] = grp_orders["cluster"]

                # 작은/큰 클러스터 식별
                if count_a < count_b:
                    label_small, label_large = label_a, label_b
                elif count_a > count_b:
                    label_small, label_large = label_b, label_a
                else:
                    print("두 클러스터 사이즈 동일 -> 강제로 label_small=0, label_large=1")
                    sorted_idx = sorted(cluster_counts.index)
                    label_small, label_large = sorted_idx[0], sorted_idx[1]

                # 반복적으로 작은 클러스터를 20건으로 맞추기
                while True:
                    cluster_counts = group_orders["cluster"].value_counts()
                    if len(cluster_counts) < 2:
                        break

                    label_a2 = cluster_counts.index[0]
                    count_a2 = cluster_counts.iloc[0]
                    label_b2 = cluster_counts.index[1]
                    count_b2 = cluster_counts.iloc[1]

                    # 다시 작은/큰 라벨 식별
                    if count_a2 < count_b2:
                        label_small, label_large = label_a2, label_b2
                    elif count_a2 > count_b2:
                        label_small, label_large = label_b2, label_a2
                    else:
                        print("작은/큰 클러스터 사이즈 동일 -> tie-break")
                        sorted_idx = sorted(cluster_counts.index)
                        label_small, label_large = sorted_idx[0], sorted_idx[1]

                    count_small = cluster_counts[label_small]
                    count_large = cluster_counts[label_large]

                    # 정확히 30이면 루프 종료
                    if count_small == 20:
                        break

                    elif count_small < 20:
                        # 작은 클러스터 부족 -> 큰 클러스터에서 가져오기
                        deficit = 20 - count_small
                        available = count_large - 20
                        if available <= 0:
                            print(
                                f"조정 불가: 큰 클러스터({label_large})에 여분 주문이 없어 이동 불가"
                            )
                            break
                        move_count = min(deficit, available)

                        donor_orders = group_orders[group_orders['cluster'] == label_large].copy()

                        # 작은 클러스터에 속한 좌표들
                        small_cluster_df = group_orders[group_orders['cluster'] == label_small][["lat","lng"]]

                        # min_dist_to_group 사용
                        donor_orders['dist_to_small'] = donor_orders.apply(
                            lambda row: min_dist_to_group(row, small_cluster_df),
                            axis=1
                        )
                        donor_orders.sort_values('dist_to_small', ascending=True, inplace=True)
                        orders_to_move = donor_orders.head(move_count)

                        if len(orders_to_move) == 0:
                            print("이동할 주문이 없어 추가 조정 불가능")
                            break

                        group_orders.loc[orders_to_move.index, 'cluster'] = label_small

                    else:
                        # 작은 클러스터 초과 -> 큰 클러스터로 이동
                        surplus = count_small - 20
                        print(f"작은 클러스터 초과: {surplus}건, 큰 클러스터로 이동 시도")

                        donor_orders = group_orders[group_orders['cluster'] == label_small].copy()
                        large_cluster_df = group_orders[group_orders['cluster'] == label_large][["lat","lng"]]

                        donor_orders['dist_to_large'] = donor_orders.apply(
                            lambda row: min_dist_to_group(row, large_cluster_df),
                            axis=1
                        )
                        donor_orders.sort_values('dist_to_large', ascending=True, inplace=True)
                        orders_to_move = donor_orders.head(surplus)

                        if len(orders_to_move) == 0:
                            print("이동할 주문이 없어 추가 조정 불가능")
                            break

                        group_orders.loc[orders_to_move.index, 'cluster'] = label_large

                    # 이동 후 상황 확인
                    cluster_counts = group_orders["cluster"].value_counts()
                    print(f"이동 후 클러스터 분포: {cluster_counts.to_dict()}")

                    if label_small not in cluster_counts:
                        print("label_small 클러스터가 사라져서 종료")
                        break

                    count_small = cluster_counts.get(label_small, 0)
                    if count_small == 20:
                        break

                # 작은 클러스터가 20건이면 화이트 확정
                count_small = group_orders["cluster"].value_counts().get(label_small, 0)
                if count_small == 20:
                    new_white_group = f"{current_group}_WHITE"
                    idx_white = group_orders[group_orders["cluster"] == label_small].index

                    # 그룹 이동
                    move_orders(df, idx_white, new_white_group, clear_driver=False)

                    print(
                        f"[화이트 분리 완료] 그룹 {new_white_group} (20건) 생성, driver_type='WHITE'로 업데이트"
                    )
                    iteration += 1

                    # 남은(큰) 클러스터 처리
                    idx_remaining = group_orders[
                        group_orders["cluster"] == label_large
                    ].index
                    remaining_count = df.loc[idx_remaining, "shipping_uuid"].count()
                    if remaining_count < 40:
                        print(
                            f"남은 그룹의 주문 수가 {remaining_count}건으로 40 미만이어서 추가 분리 종료"
                        )
                        new_remaining_group = f"{current_group}_R"
                        move_orders(
                            df, idx_remaining, new_remaining_group, clear_driver=False
                        )
                        print(
                            f"남은 주문 {remaining_count}건은 그룹 {new_remaining_group}로 업데이트"
                        )
                        continue

            if 45 <= total_count < 50:
                print(f"{total_count}건 이므로 한 클러스터 23으로 조정")

                grp_orders, cluster_counts, label_a, count_a, label_b, count_b = (
                    split_group_kmeans_2clusters(df, current_group)
                )

                if len(cluster_counts) < 2 or label_b is None:
                    print("클러스터가 2개 미만이거나 하나뿐이어서 처리 불가, 계속 진행")
                    continue

                print(f"클러스터링 결과: {cluster_counts.to_dict()}")
                group_orders["cluster"] = grp_orders["cluster"]

                # 작은/큰 클러스터 식별
                if count_a < count_b:
                    label_small, label_large = label_a, label_b
                elif count_a > count_b:
                    label_small, label_large = label_b, label_a
                else:
                    print("두 클러스터 사이즈 동일 -> 강제로 label_small=0, label_large=1")
                    sorted_idx = sorted(cluster_counts.index)
                    label_small, label_large = sorted_idx[0], sorted_idx[1]

                # 반복적으로 작은 클러스터를 23건으로 맞추기
                while True:
                    cluster_counts = group_orders["cluster"].value_counts()
                    if len(cluster_counts) < 2:
                        break

                    label_a2 = cluster_counts.index[0]
                    count_a2 = cluster_counts.iloc[0]
                    label_b2 = cluster_counts.index[1]
                    count_b2 = cluster_counts.iloc[1]

                    # 다시 작은/큰 라벨 식별
                    if count_a2 < count_b2:
                        label_small, label_large = label_a2, label_b2
                    elif count_a2 > count_b2:
                        label_small, label_large = label_b2, label_a2
                    else:
                        print("작은/큰 클러스터 사이즈 동일 -> tie-break")
                        sorted_idx = sorted(cluster_counts.index)
                        label_small, label_large = sorted_idx[0], sorted_idx[1]

                    count_small = cluster_counts[label_small]
                    count_large = cluster_counts[label_large]

                    # 정확히 30이면 루프 종료
                    if count_small == 23:
                        break
                    
                    # 이 부분 조심
                    elif count_small < 23:
                        # 작은 클러스터 부족 -> 큰 클러스터에서 가져오기
                        deficit = 23 - count_small
                        # available = count_large - 23
                        # if available <= 0:
                        #     print(
                        #         f"조정 불가: 큰 클러스터({label_large})에 여분 주문이 없어 이동 불가"
                        #     )
                        #     break
                        # move_count = min(deficit, available)
                        move_count = deficit

                        donor_orders = group_orders[group_orders['cluster'] == label_large].copy()

                        # 작은 클러스터에 속한 좌표들
                        small_cluster_df = group_orders[group_orders['cluster'] == label_small][["lat","lng"]]

                        # min_dist_to_group 사용
                        donor_orders['dist_to_small'] = donor_orders.apply(
                            lambda row: min_dist_to_group(row, small_cluster_df),
                            axis=1
                        )
                        donor_orders.sort_values('dist_to_small', ascending=True, inplace=True)
                        orders_to_move = donor_orders.head(move_count)

                        if len(orders_to_move) == 0:
                            print("이동할 주문이 없어 추가 조정 불가능")
                            break

                        group_orders.loc[orders_to_move.index, 'cluster'] = label_small

                    else:
                        # 작은 클러스터 초과 -> 큰 클러스터로 이동
                        surplus = count_small - 23
                        print(f"작은 클러스터 초과: {surplus}건, 큰 클러스터로 이동 시도")

                        donor_orders = group_orders[group_orders['cluster'] == label_small].copy()
                        large_cluster_df = group_orders[group_orders['cluster'] == label_large][["lat","lng"]]

                        donor_orders['dist_to_large'] = donor_orders.apply(
                            lambda row: min_dist_to_group(row, large_cluster_df),
                            axis=1
                        )
                        donor_orders.sort_values('dist_to_large', ascending=True, inplace=True)
                        orders_to_move = donor_orders.head(surplus)

                        if len(orders_to_move) == 0:
                            print("이동할 주문이 없어 추가 조정 불가능")
                            break

                        group_orders.loc[orders_to_move.index, 'cluster'] = label_large

                    # 이동 후 상황 확인
                    cluster_counts = group_orders["cluster"].value_counts()
                    print(f"이동 후 클러스터 분포: {cluster_counts.to_dict()}")

                    if label_small not in cluster_counts:
                        print("label_small 클러스터가 사라져서 종료")
                        break

                    count_small = cluster_counts.get(label_small, 0)
                    if count_small == 23:
                        break

                # 작은 클러스터가 23건이면 화이트 확정
                count_small = group_orders["cluster"].value_counts().get(label_small, 0)
                if count_small == 23:
                    new_white_group = f"{current_group}_WHITE"
                    idx_white = group_orders[group_orders["cluster"] == label_small].index

                    # 그룹 이동
                    move_orders(df, idx_white, new_white_group, clear_driver=False)

                    print(
                        f"[화이트 분리 완료] 그룹 {new_white_group} (23건) 생성, driver_type='WHITE'로 업데이트"
                    )
                    iteration += 1

                    # 남은(큰) 클러스터 처리
                    idx_remaining = group_orders[
                        group_orders["cluster"] == label_large
                    ].index
                    remaining_count = df.loc[idx_remaining, "shipping_uuid"].count()
                    if remaining_count < 40:
                        print(
                            f"남은 그룹의 주문 수가 {remaining_count}건으로 40 미만이어서 추가 분리 종료"
                        )
                        new_remaining_group = f"{current_group}_R"
                        move_orders(
                            df, idx_remaining, new_remaining_group, clear_driver=False
                        )
                        print(
                            f"남은 주문 {remaining_count}건은 그룹 {new_remaining_group}로 업데이트"
                        )
                        continue

            if 50 <= total_count < 60:
                print(f"{total_count}건 이므로 큰 클러스터 30으로 조정")
                grp_orders, cluster_counts, label_a, count_a, label_b, count_b = (
                    split_group_kmeans_2clusters(df, current_group)
                )

                if len(cluster_counts) < 2 or label_b is None:
                    print("클러스터가 2개 미만이거나 하나뿐이어서 처리 불가, 계속 진행")
                    continue

                print(f"클러스터링 결과: {cluster_counts.to_dict()}")
                group_orders["cluster"] = grp_orders["cluster"]

                # 작은/큰 클러스터 식별
                if count_a < count_b:
                    label_small, label_large = label_a, label_b
                elif count_a > count_b:
                    label_small, label_large = label_b, label_a
                else:
                    print("두 클러스터 사이즈 동일 -> 강제로 label_small=0, label_large=1")
                    sorted_idx = sorted(cluster_counts.index)
                    label_small, label_large = sorted_idx[0], sorted_idx[1]

                # 반복적으로 큰 클러스터를 30건으로 맞추기
                while True:
                    cluster_counts = group_orders["cluster"].value_counts()
                    if len(cluster_counts) < 2:
                        break

                    label_a2 = cluster_counts.index[0]
                    count_a2 = cluster_counts.iloc[0]
                    label_b2 = cluster_counts.index[1]
                    count_b2 = cluster_counts.iloc[1]

                    # 다시 작은/큰 라벨 식별
                    if count_a2 < count_b2:
                        label_small, label_large = label_a2, label_b2
                    elif count_a2 > count_b2:
                        label_small, label_large = label_b2, label_a2
                    else:
                        print("작은/큰 클러스터 사이즈 동일 -> tie-break")
                        sorted_idx = sorted(cluster_counts.index)
                        label_small, label_large = sorted_idx[0], sorted_idx[1]

                    count_small = cluster_counts[label_small]
                    count_large = cluster_counts[label_large]

                    # 정확히 30이면 루프 종료
                    if count_large == 30:
                        break

                    elif count_large < 30:
                        # 큰 클러스터 부족 -> 작은 클러스터에서 가져오기
                        deficit = 30 - count_large
                        # available = count_large - 30
                        # if available <= 0:
                        #     print(
                        #         f"조정 불가: 큰 클러스터({label_large})에 여분 주문이 없어 이동 불가"
                        #     )
                        #     break
                        # move_count = min(deficit, available)
                        move_count = deficit

                        donor_orders = group_orders[group_orders['cluster'] == label_small].copy()

                        # 작은 클러스터에 속한 좌표들
                        large_cluster_df = group_orders[group_orders['cluster'] == label_large][["lat","lng"]]

                        # min_dist_to_group 사용
                        donor_orders['dist_to_large'] = donor_orders.apply(
                            lambda row: min_dist_to_group(row, large_cluster_df),
                            axis=1
                        )
                        donor_orders.sort_values('dist_to_large', ascending=True, inplace=True)
                        orders_to_move = donor_orders.head(move_count)

                        if len(orders_to_move) == 0:
                            print("이동할 주문이 없어 추가 조정 불가능")
                            break

                        group_orders.loc[orders_to_move.index, 'cluster'] = label_large

                    else:
                        # 큰 클러스터 초과 -> 작은 클러스터로 이동
                        surplus = count_large - 30
                        print(f"큰 클러스터 초과: {surplus}건, 작은 클러스터로 이동 시도")

                        donor_orders = group_orders[group_orders['cluster'] == label_large].copy()
                        small_cluster_df = group_orders[group_orders['cluster'] == label_small][["lat","lng"]]

                        donor_orders['dist_to_small'] = donor_orders.apply(
                            lambda row: min_dist_to_group(row, small_cluster_df),
                            axis=1
                        )
                        donor_orders.sort_values('dist_to_small', ascending=True, inplace=True)
                        orders_to_move = donor_orders.head(surplus)

                        if len(orders_to_move) == 0:
                            print("이동할 주문이 없어 추가 조정 불가능")
                            break

                        group_orders.loc[orders_to_move.index, 'cluster'] = label_small

                    # 이동 후 상황 확인
                    cluster_counts = group_orders["cluster"].value_counts()
                    print(f"이동 후 클러스터 분포: {cluster_counts.to_dict()}")

                    if label_large not in cluster_counts:
                        print("label_large 클러스터가 사라져서 종료")
                        break

                    count_large = cluster_counts.get(label_large, 0)
                    if count_large == 30:
                        break

                # 작은 클러스터가 30건이면 화이트 확정
                count_large = group_orders["cluster"].value_counts().get(label_large, 0)
                if count_large == 30:
                    new_white_group = f"{current_group}_WHITE"
                    idx_white = group_orders[group_orders["cluster"] == label_large].index

                    # 그룹 이동
                    move_orders(df, idx_white, new_white_group, clear_driver=False)

                    print(
                        f"[화이트 분리 완료] 그룹 {new_white_group} (30건) 생성, driver_type='WHITE'로 업데이트"
                    )
                    iteration += 1

                    # 남은(큰) 클러스터 처리
                    idx_remaining = group_orders[
                        group_orders["cluster"] == label_small
                    ].index
                    remaining_count = df.loc[idx_remaining, "shipping_uuid"].count()
                    if remaining_count < 40:
                        print(
                            f"남은 그룹의 주문 수가 {remaining_count}건으로 40 미만이어서 추가 분리 종료"
                        )
                        new_remaining_group = f"{current_group}_R"
                        move_orders(
                            df, idx_remaining, new_remaining_group, clear_driver=False
                        )
                        print(
                            f"남은 주문 {remaining_count}건은 그룹 {new_remaining_group}로 업데이트"
                        )
                        continue


            if 60 <= total_count <= 69:
                print(f"{total_count}건 이므로 한 클러스터 30으로 조정")

                grp_orders, cluster_counts, label_a, count_a, label_b, count_b = (
                    split_group_kmeans_2clusters(df, current_group)
                )

                if len(cluster_counts) < 2 or label_b is None:
                    print("클러스터가 2개 미만이거나 하나뿐이어서 처리 불가, 계속 진행")
                    continue

                print(f"클러스터링 결과: {cluster_counts.to_dict()}")
                group_orders["cluster"] = grp_orders["cluster"]

                # 작은/큰 클러스터 식별
                if count_a < count_b:
                    label_small, label_large = label_a, label_b
                elif count_a > count_b:
                    label_small, label_large = label_b, label_a
                else:
                    print("두 클러스터 사이즈 동일 -> 강제로 label_small=0, label_large=1")
                    sorted_idx = sorted(cluster_counts.index)
                    label_small, label_large = sorted_idx[0], sorted_idx[1]

                # 반복적으로 작은 클러스터를 30건으로 맞추기
                while True:
                    cluster_counts = group_orders["cluster"].value_counts()
                    if len(cluster_counts) < 2:
                        break

                    label_a2 = cluster_counts.index[0]
                    count_a2 = cluster_counts.iloc[0]
                    label_b2 = cluster_counts.index[1]
                    count_b2 = cluster_counts.iloc[1]

                    # 다시 작은/큰 라벨 식별
                    if count_a2 < count_b2:
                        label_small, label_large = label_a2, label_b2
                    elif count_a2 > count_b2:
                        label_small, label_large = label_b2, label_a2
                    else:
                        print("작은/큰 클러스터 사이즈 동일 -> tie-break")
                        sorted_idx = sorted(cluster_counts.index)
                        label_small, label_large = sorted_idx[0], sorted_idx[1]

                    count_small = cluster_counts[label_small]
                    count_large = cluster_counts[label_large]

                    # 두 클러스터가 모두 30~39면 각각 WHITE 그룹으로 마무리
                    if (30 <= count_a2 < 40) and (30 <= count_b2 < 40):
                        new_white_group_a = f"{current_group}_{label_a2}_WHITE"
                        new_white_group_b = f"{current_group}_{label_b2}_WHITE"

                        idx_a = group_orders[group_orders["cluster"] == label_a2].index
                        idx_b = group_orders[group_orders["cluster"] == label_b2].index

                        move_orders(df, idx_a, new_white_group_a, clear_driver=False)
                        move_orders(df, idx_b, new_white_group_b, clear_driver=False)

                        print(
                            f"[화이트 분리 완료] 그룹 {new_white_group_a} {len(idx_a)}건, {new_white_group_b} {len(idx_b)}건 생성, driver_type='WHITE'로 업데이트"
                        )
                        break

                    # 정확히 30이면 루프 종료
                    if count_small == 30:
                        break

                    elif count_small < 30:
                        # 작은 클러스터 부족 -> 큰 클러스터에서 가져오기
                        deficit = 30 - count_small
                        available = count_large - 30
                        if available <= 0:
                            print(
                                f"조정 불가: 큰 클러스터({label_large})에 여분 주문이 없어 이동 불가"
                            )
                            break
                        move_count = min(deficit, available)

                        donor_orders = group_orders[group_orders['cluster'] == label_large].copy()

                        # 작은 클러스터에 속한 좌표들
                        small_cluster_df = group_orders[group_orders['cluster'] == label_small][["lat","lng"]]

                        # min_dist_to_group 사용
                        donor_orders['dist_to_small'] = donor_orders.apply(
                            lambda row: min_dist_to_group(row, small_cluster_df),
                            axis=1
                        )
                        donor_orders.sort_values('dist_to_small', ascending=True, inplace=True)
                        orders_to_move = donor_orders.head(move_count)

                        if len(orders_to_move) == 0:
                            print("이동할 주문이 없어 추가 조정 불가능")
                            break

                        group_orders.loc[orders_to_move.index, 'cluster'] = label_small

                    else:
                        # 작은 클러스터 초과 -> 큰 클러스터로 이동
                        surplus = count_small - 30
                        print(f"작은 클러스터 초과: {surplus}건, 큰 클러스터로 이동 시도")

                        donor_orders = group_orders[group_orders['cluster'] == label_small].copy()
                        large_cluster_df = group_orders[group_orders['cluster'] == label_large][["lat","lng"]]

                        donor_orders['dist_to_large'] = donor_orders.apply(
                            lambda row: min_dist_to_group(row, large_cluster_df),
                            axis=1
                        )
                        donor_orders.sort_values('dist_to_large', ascending=True, inplace=True)
                        orders_to_move = donor_orders.head(surplus)

                        if len(orders_to_move) == 0:
                            print("이동할 주문이 없어 추가 조정 불가능")
                            break

                        group_orders.loc[orders_to_move.index, 'cluster'] = label_large

                    # 이동 후 상황 확인
                    cluster_counts = group_orders["cluster"].value_counts()
                    print(f"이동 후 클러스터 분포: {cluster_counts.to_dict()}")

                    if label_small not in cluster_counts:
                        print("label_small 클러스터가 사라져서 종료")
                        break

                    count_small = cluster_counts.get(label_small, 0)
                    if count_small == 30:
                        break

                # 작은 클러스터가 30건이면 화이트 확정
                count_small = group_orders["cluster"].value_counts().get(label_small, 0)
                if count_small == 30:
                    new_white_group = f"{current_group}_WHITE"
                    idx_white = group_orders[group_orders["cluster"] == label_small].index

                    # 그룹 이동
                    move_orders(df, idx_white, new_white_group, clear_driver=False)

                    print(
                        f"[화이트 분리 완료] 그룹 {new_white_group} (30건) 생성, driver_type='WHITE'로 업데이트"
                    )
                    iteration += 1

                    # 남은(큰) 클러스터 처리
                    idx_remaining = group_orders[
                        group_orders["cluster"] == label_large
                    ].index
                    remaining_count = df.loc[idx_remaining, "shipping_uuid"].count()
                    if remaining_count < 40:
                        print(
                            f"남은 그룹의 주문 수가 {remaining_count}건으로 40 미만이어서 추가 분리 종료"
                        )
                        new_remaining_group = f"{current_group}_R"
                        move_orders(
                            df, idx_remaining, new_remaining_group, clear_driver=False
                        )
                        print(
                            f"남은 주문 {remaining_count}건은 그룹 {new_remaining_group}로 업데이트"
                        )
                        continue

            if 70 <= total_count <= 78:
                print(f"{total_count}건 이므로 큰 클러스터 39로 조정")

                grp_orders, cluster_counts, label_a, count_a, label_b, count_b = (
                    split_group_kmeans_2clusters(df, current_group)
                )
                if len(cluster_counts) < 2 or label_b is None:
                    print("클러스터가 2개 미만이라 처리 불가")
                    continue

                print(f"클러스터링 결과: {cluster_counts.to_dict()}")
                group_orders["cluster"] = grp_orders["cluster"]

                # 작은/큰 클러스터 구분
                if count_a < count_b:
                    label_small, label_large = label_a, label_b
                elif count_a > count_b:
                    label_small, label_large = label_b, label_a
                else:
                    print("두 클러스터 사이즈 동일 -> 강제로 label_small=0, label_large=1")
                    sorted_idx = sorted(cluster_counts.index)
                    label_small, label_large = sorted_idx[0], sorted_idx[1]

                # 큰 클러스터를 39건으로 조정
                while True:
                    cluster_counts2 = group_orders["cluster"].value_counts()
                    if len(cluster_counts2) < 2:
                        break

                    la = cluster_counts2.index[0]
                    ca = cluster_counts2.iloc[0]
                    lb = cluster_counts2.index[1]
                    cb = cluster_counts2.iloc[1]

                    if ca < cb:
                        label_small, label_large = la, lb
                    elif ca > cb:
                        label_small, label_large = lb, la
                    else:
                        print("작은/큰 클러스터 사이즈 동일 -> tie-break")
                        sorted_idx = sorted(cluster_counts2.index)
                        label_small, label_large = sorted_idx[0], sorted_idx[1]

                    count_small = cluster_counts2[label_small]
                    count_large = cluster_counts2[label_large]

                    if (30 <= ca < 40) and (30 <= cb < 40):
                        new_white_group_a = f"{current_group}_{la}_WHITE"
                        new_white_group_b = f"{current_group}_{lb}_WHITE"

                        idx_a = group_orders[group_orders["cluster"] == la].index
                        idx_b = group_orders[group_orders["cluster"] == lb].index

                        move_orders(df, idx_a, new_white_group_a, clear_driver=False)
                        move_orders(df, idx_b, new_white_group_b, clear_driver=False)

                        print(
                            f"[화이트 분리 완료] 그룹 {new_white_group_a} {len(idx_a)}건, {new_white_group_b} {len(idx_b)}건 생성, driver_type='WHITE'로 업데이트"
                        )
                        break

                    if count_large == 39:
                        break

                    # 큰 클러스터 39로 맞추기
                    # 작은 클러스터에서 큰 클러스터 중심점에서 가까운 주문 선택
                    elif count_large < 39:
                        deficit = 39 - count_large
                        available = count_small - 30
                        if available <= 0:
                            print(
                                f"조정 불가: 작은 클러스터({label_small})에 여분 주문이 없어 이동 불가"
                            )
                            break
                        move_count = min(deficit, available)
                        print(f"작은 클러스터 부족: {deficit}건 -> {move_count}건 이동")

                        donor_orders = group_orders[group_orders['cluster'] == label_small].copy()
                        large_cluster_df = group_orders[group_orders['cluster'] == label_large][["lat","lng"]]

                        donor_orders['dist_to_large'] = donor_orders.apply(
                            lambda row: min_dist_to_group(row, large_cluster_df),
                            axis=1
                        )
                        donor_orders.sort_values('dist_to_large', ascending=True, inplace=True)
                        orders_to_move = donor_orders.head(move_count)

                        if len(orders_to_move) == 0:
                            print("이동할 주문이 없어 추가 조정 불가능")
                            break

                        group_orders.loc[orders_to_move.index, 'cluster'] = label_large


                    else:  # count_large > 39
                        surplus = count_large - 39
                        print(f"큰 클러스터 초과: {surplus}건 -> 작은 클러스터 이동")

                        donor_orders = group_orders[group_orders['cluster'] == label_large].copy()
                        small_cluster_df = group_orders[group_orders['cluster'] == label_small][["lat","lng"]]

                        donor_orders['dist_to_small'] = donor_orders.apply(
                            lambda row: min_dist_to_group(row, small_cluster_df),
                            axis=1
                        )
                        donor_orders.sort_values('dist_to_small', ascending=True, inplace=True)
                        orders_to_move = donor_orders.head(surplus)

                        if len(orders_to_move) == 0:
                            print("이동할 주문이 없어 추가 조정 불가능")
                            break

                        group_orders.loc[orders_to_move.index, 'cluster'] = label_small

                    print(
                        f"이동 후 클러스터 분포: {group_orders['cluster'].value_counts().to_dict()}"
                    )

                    if label_small not in group_orders["cluster"].value_counts():
                        print("label_small 클러스터가 사라져서 종료")
                        break

                    if group_orders["cluster"].value_counts().get(label_large, 0) == 39:
                        break

                # 큰 클러스터가 39건이면 화이트 확정
                count_large = group_orders["cluster"].value_counts().get(label_large, 0)
                if count_large == 39:
                    new_white_group = f"{current_group}_WHITE_{iteration}"
                    idx_white = group_orders[group_orders["cluster"] == label_large].index

                    move_orders(df, idx_white, new_white_group, clear_driver=False)
                    print(
                        f"[화이트 분리 완료] 그룹 {new_white_group} (39건) 생성, driver_type='WHITE'로 업데이트"
                    )

                    iteration += 1

                    # 작은 클러스터 처리
                    idx_small = group_orders[group_orders["cluster"] == label_small].index
                    remaining_count = df.loc[idx_small, "shipping_uuid"].count()
                    if remaining_count < 40:
                        print(
                            f"남은 그룹의 주문 수가 {remaining_count}건으로 40 미만이어서 추가 분리 종료"
                        )
                        new_remaining_group = f"{current_group}_R_WHITE"
                        move_orders(df, idx_small, new_remaining_group, clear_driver=False)
                        print(
                            f"남은 주문 {remaining_count}건은 그룹 {new_remaining_group}로 업데이트"
                        )
                        continue

            print(
                f"\n[화이트 처리] 그룹 {current_group} 총 주문 수: {total_count}건. 클러스터링 시도..."
            )

            grp_orders, cluster_counts, label_a, count_a, label_b, count_b = (
                split_group_kmeans_2clusters(df, current_group)
            )
            if len(cluster_counts) < 2 or label_b is None:
                print("클러스터가 2개 미만이라 스킵")
                continue

            print(f"클러스터링 결과: {cluster_counts.to_dict()}")
            group_orders["cluster"] = grp_orders["cluster"]

            # 둘 다 30~39면 둘 다 WHITE 배정
            if 30 <= count_a < 40 and 30 <= count_b < 40:
                new_white_group_a = f"{current_group}_WHITE_{label_a}"
                new_white_group_b = f"{current_group}_WHITE_{label_b}"

                idx_a = group_orders[group_orders["cluster"] == label_a].index
                idx_b = group_orders[group_orders["cluster"] == label_b].index

                move_orders(df, idx_a, new_white_group_a, clear_driver=False)
                move_orders(df, idx_b, new_white_group_b, clear_driver=False)

                print(
                    f"클러스터 초기 그룹 물량 30건이상 40건 미만이므로 그룹 {new_white_group_a}, {new_white_group_b} driver_type='WHITE'로 업데이트"
                )
                continue

            # 한쪽이 30~39, 다른 쪽이 60 이상
            if 30 <= count_a < 40 and count_b >= 60:
                new_white_group_a = f"{current_group}_WHITE_{label_a}"

                idx_a = group_orders[group_orders["cluster"] == label_a].index
                idx_b = group_orders[group_orders["cluster"] == label_b].index

                move_orders(df, idx_a, new_white_group_a, clear_driver=False)
                move_orders(df, idx_b, f"{current_group}_R", clear_driver=False)

                print("A 화이트 배정")
                print(
                    f"클러스터 초기 그룹 물량 30건이상 40건 미만이므로 그룹 {new_white_group_a} driver_type='WHITE'로 업데이트"
                )

                current_group = f"{current_group}_R"
                group_stack.append(current_group)
                continue

            if 30 <= count_b < 40 and count_a >= 60:
                new_white_group_b = f"{current_group}_WHITE_{label_b}"

                idx_a = group_orders[group_orders["cluster"] == label_a].index
                idx_b = group_orders[group_orders["cluster"] == label_b].index

                move_orders(df, idx_b, new_white_group_b, clear_driver=False)
                move_orders(df, idx_a, f"{current_group}_R", clear_driver=False)

                print("B 화이트 배정")
                print(
                    f"클러스터 초기 그룹 물량 30건이상 40건 미만이므로 그룹 {new_white_group_b} driver_type='WHITE'로 업데이트"
                )

                current_group = f"{current_group}_R"
                group_stack.append(current_group)
                continue

            if count_a < count_b:
                label_small, label_large = label_a, label_b
            elif count_a > count_b:
                label_small, label_large = label_b, label_a
            else:
                print("두 클러스터 사이즈 동일 -> 강제로 label_small=0, label_large=1")
                sorted_idx = sorted(cluster_counts.index)
                label_small, label_large = sorted_idx[0], sorted_idx[1]

            while True:
                cluster_counts2 = group_orders["cluster"].value_counts()
                if len(cluster_counts2) < 2:
                    break

                la = cluster_counts2.index[0]
                ca = cluster_counts2.iloc[0]
                lb = cluster_counts2.index[1]
                cb = cluster_counts2.iloc[1]

                if ca < cb:
                    label_small, label_large = la, lb
                elif ca > cb:
                    label_small, label_large = lb, la
                else:
                    print("작은/큰 클러스터 사이즈 동일 -> tie-break")
                    sorted_idx = sorted(cluster_counts2.index)
                    label_small, label_large = sorted_idx[0], sorted_idx[1]

                count_small = cluster_counts2[label_small]
                count_large = cluster_counts2[label_large]

                if count_small == 35:
                    break
                # 작은 클러스터의 중심점에서 가까운 데이터들 옮기기
                elif count_small < 35:
                    deficit = 35 - count_small
                    available = count_large - 35
                    if available <= 0:
                        print(
                            f"조정 불가: 큰 클러스터({label_large})에 여분 주문이 없어 이동 불가"
                        )
                        break
                    # move_count=deficit
                    move_count = min(deficit, available)
                    print(
                        f"작은 클러스터 부족: {deficit}건, donor 클러스터에서 {move_count}건 이동 시도"
                    )
                    donor_orders = group_orders[group_orders['cluster'] == label_large].copy()
                    small_cluster_df = group_orders[group_orders['cluster'] == label_small][["lat","lng"]]

                    donor_orders['dist_to_small'] = donor_orders.apply(
                        lambda row: min_dist_to_group(row, small_cluster_df),
                        axis=1
                    )
                    donor_orders.sort_values('dist_to_small', ascending=True, inplace=True)
                    orders_to_move = donor_orders.head(move_count)

                    if len(orders_to_move) == 0:
                        print("이동할 주문이 없어 추가 조정 불가능")
                        break

                    group_orders.loc[orders_to_move.index, 'cluster'] = label_small

                else:
                    surplus = count_small - 35
                    print(f"작은 클러스터 초과: {surplus}건, 큰 클러스터로 이동 시도")

                    donor_orders = group_orders[group_orders['cluster'] == label_small].copy()
                    large_cluster_df = group_orders[group_orders['cluster'] == label_large][["lat","lng"]]

                    donor_orders['dist_to_large'] = donor_orders.apply(
                        lambda row: min_dist_to_group(row, large_cluster_df),
                        axis=1
                    )
                    donor_orders.sort_values('dist_to_large', ascending=True, inplace=True)
                    orders_to_move = donor_orders.head(surplus)

                    if len(orders_to_move) == 0:
                        print("이동할 주문이 없어 추가 조정 불가능")
                        break

                    group_orders.loc[orders_to_move.index, 'cluster'] = label_large


                cluster_counts2 = group_orders["cluster"].value_counts()
                print(f"이동 후 클러스터 분포: {cluster_counts2.to_dict()}")

                if label_small not in cluster_counts2:
                    print("label_small 클러스터가 사라져서 종료")
                    break

                if cluster_counts2.get(label_small, 0) == 35:
                    break

            # 작은 클러스터가 35건이면 화이트로 확정
            final_count_small = group_orders["cluster"].value_counts().get(label_small, 0)
            if final_count_small == 35:
                new_white_group = f"{current_group}_WHITE_{iteration}"
                idx_white = group_orders[group_orders["cluster"] == label_small].index

                move_orders(df, idx_white, new_white_group, clear_driver=False)
                print(
                    f"[화이트 분리 완료] 그룹 {new_white_group} (35건) 생성, driver_type='WHITE'로 업데이트"
                )

                iteration += 1

                # 나머지(큰 클러스터) 처리
                idx_remaining = group_orders[group_orders["cluster"] == label_large].index
                remaining_count = df.loc[idx_remaining, "shipping_uuid"].count()
                if remaining_count < 40:
                    print(
                        f"남은 그룹의 주문 수가 {remaining_count}건으로 40 미만이어서 추가 분리 종료"
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
                print(
                    f"화이트 분리 불가: 작은 클러스터가 20건이 아닙니다. (현재 {final_count_small}건)"
                )
                continue

        return df
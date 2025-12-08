Postalcode Clustering Lambda

이 프로젝트는 우편번호 기반 배송 작업을 공간적·운영적 제약을 반영하여 자동 클러스터링하는 엔진입니다.
배송 아이템, 기사 스케줄, 우편번호 그룹 정보를 통합하여 운영 가능한 단위의 클러스터 생성 및 기사 배정을 수행하며, 결과는 S3와 내부 시스템으로 전달됩니다.

전체 워크플로는 AWS Lambda와 EventBridge 기반의 서버리스 배치 파이프라인으로 구성됩니다.

아키텍처 개요
EventBridge → Lambda(app.py)
      ↓
데이터 적재
  - 배송 아이템 (MySQL/Postgres)
  - 기사 스케줄
  - 우편번호 그룹 정의
      ↓
지역 단위 클러스터링
  - 우편번호 폴리곤 기반 공간 매칭
  - K-means++ + 운영 제약 반영
      ↓
기사 배정
  - Y/R/O/WHITE/BLUE 타입
  - MAX 용량 기반 제약 처리
  - 소형 그룹 병합 / 대형 그룹 분할
      ↓
오버랩(늦게 유입된 주문) 자동 매핑
      ↓
S3 업로드 및 Slack 모니터링

디렉터리 구조
lambda/
└─ postalcode-clustering/
   ├─ app.py                      # Lambda 엔트리포인트 및 워크플로 오케스트레이션
   ├─ utils/
   │  ├─ run_clustering.py        # 지역 단위 클러스터링 실행 로직
   │  ├─ process_region.py        # 공간 매칭 + K-means 조정 + 기사 배정
   │  ├─ drivers/                 # 기사 배정(Y/R/O/WHITE/BLUE) 및 후처리 로직
   │  ├─ zipcode/                 # 우편번호 그룹(MySQL/PG) 로딩
   │  ├─ data/                    # 배송/스케줄/모델 제약 데이터 로더
   │  ├─ overlap/                 # 오버랩 주문 처리 모듈
   │  ├─ upload_cluster_data.py   # 결과 S3 업로드
   │  └─ slack/                   # Slack 알림 템플릿 및 Webhook 처리

핵심 로직
1. 지역 단위 공간 클러스터링
- 우편번호 폴리곤과 배송 좌표 간 공간 매칭
- 기사 스케줄 및 MAX 제약을 반영한 K-means++ 기반 분할·병합
- group_name, cluster_label, driver_type, driver_code 자동 생성


단순 거리 기반 K-means가 아닌, 운영 제약(기사 용량·근무 지역·우편번호 그룹) 을 포함한 하이브리드 방식으로 클러스터를 생성합니다.

2. 기사 배정 로직
- 기사 색상(Y/R/O/WHITE/BLUE)별 작업 가능 범위 분리
- 기사별 최대 작업량(MAX)을 기반으로 한 배정 제약 처리
- 그룹 중심점 기준 최소 이동 거리 기반 기사-그룹 매칭
- WHITE 기사 대상:
    • 소형 그룹 병합
    • 대형 그룹 재분할(K-means 활용)


실제 운영에 필요한 업무량 균형화 및 공간적 배정 효율성을 확보하기 위한 설계입니다.

3. 오버랩 주문 처리
- 배치 실행 이후 유입된 주문을 최근 생성된 클러스터에 자동 할당
- 기존 cluster_label, driver_type 일관성 유지
- 연속적 주문 흐름을 고려한 운영 친화 구조

4. 결과 저장 및 모니터링
- 배송 아이템 단위 · 기사 단위 · 클러스터 단위 JSON 생성 후 S3 저장
- Slack Webhook을 통한 실행 상태, 요약 통계, 오류 보고 자동화

출력 예시
zipcode     group    driver_type    cluster_label
01786       A        WHITE          1
01812       B        YELLOW         2
01811       C        BLUE           1

기술 스택
AWS     : Lambda, EventBridge, S3, CloudWatch
Python  : Pandas, GeoPandas, Shapely, scikit-learn(K-means++)
DB      : MySQL, PostgreSQL
Ops     : Slack Webhook 기반 모니터링

프로젝트의 주요 특성
• 운영 제약 기반 클러스터링
    - 기사 스케줄, MAX 용량, 지역 정책 등을 모두 반영한 실제 운영 가능 모델

• 공간 정보 활용
    - 우편번호 폴리곤과 좌표를 결합한 하이브리드 클러스터링 방식

• 안정적인 운영 자동화
    - 오버랩 주문 처리
    - Slack 기반 실행 로그 및 오류 모니터링

• 확장성과 유지보수성
    - 지역·우편번호 그룹 정책 변화에 대응 용이
    - 기사 정책 변경 시 논리 분리로 인한 모듈 교체 가능
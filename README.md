📦 Postalcode Clustering Lambda

본 프로젝트는 우편번호 그룹 기반 배송 클러스터링 엔진으로,
하루 배송 물량을 지역·기사 스케줄·최대 물량 제약(MAX) 에 따라 자동으로 클러스터링하고
결과를 S3 및 내부 시스템으로 전달하는 Serverless 배치 파이프라인입니다.

전체 아키텍처

EventBridge → Lambda(app.py) 실행

DB(MySQL/Postgres) → 배송 아이템 / 기사 스케줄 / 우편번호 그룹 로딩

지역 단위 클러스터링 (K-means++ + 제약 조건 반영)

기사 배정(YELLOW/RAINBOW/ORANGE/WHITE/BLUE) + WHITE/소형 그룹 후처리

오버랩 주문 처리

S3 업로드 + Slack 알림

📁 주요 디렉터리
lambda/
├─ postalcode-clustering/
├─ app.py                 # Lambda 엔트리, 전체 파이프라인 오케스트레이션
├─ utils/
│  ├─ run_clustering.py   # 지역별 클러스터링 실행 (메인 엔진)
│  ├─ process_region.py   # 우편번호 그룹 매핑 + K-means 분할/병합 + 기사 배정
│  ├─ drivers/            # 기사 배정(Y/R/O/WHITE), 병합/분할 로직
│  ├─ zipcode/            # 우편번호 그룹 로딩(MySQL/PG)
│  ├─ data/               # 배송/스케줄/모델 설정 DB 조회 및 전처리
│  ├─ overlap/            # 배치 이후 들어오는 주문 오버랩 처리
│  ├─ upload_cluster_data.py  # S3 업로드
│  └─ slack/              # Slack 알림 템플릿 + 발송

핵심 로직 요약
1) 지역 단위 클러스터링

우편번호 그룹(폴리곤/zipcodes)과 배송 좌표를 공간 매칭

기사 스케줄 + MAX 제약을 반영해
K-means 기반 그룹 분할/병합

그룹마다 driver_type, driver_code, cluster_label 부여

2) 기사 배정 알고리즘

기사 색상(Y/R/O/WHITE/BLUE) 분리

기사별 최대 가능 물량(MAX) 체크

그룹 중심점과 기사 위치 기반 최소 거리 배정

화이트 기사 대상 소형 그룹 병합, 대형 그룹 재분할

3) 오버랩 주문 처리

배치 실행 이후 들어온 주문을
최근 생성된 그룹 중 가장 가까운 group으로 자동 할당

4) 결과 저장 및 모니터링

그룹·기사·배송 아이템 단위 JSON을 S3에 저장

Slack으로 성공/에러/통계 메시지 발송

결과 예시 (요약)
zipcode	group	driver_type	cluster_label
01786	A	        WHITE	    1
01812	B	        YELLOW	    2
01811	C	        BLUE	    1

기술 스택
AWS: Lambda, EventBridge, S3, CloudWatch

Python: Pandas, GeoPandas, Shapely, Scikit-learn(K-means++)

DB: MySQL, PostgreSQL

Monitoring: Slack Webhook Integration

🔍 이 프로젝트의 핵심 가치

실서비스 물량 확보: 실제 배송 환경(기사 스케줄·MAX·zipgroup)을 반영한 실시간 배치 가능

공간 기반 클러스터링: 우편번호 그룹 + 좌표 기반 K-means 하이브리드 모델

운영 친화성: 오버랩 주문 자동 흡수, Slack 통합 알림

확장성: 지역 추가, 그룹 스키마 변경, 기사 정책 변경에 유연 대응
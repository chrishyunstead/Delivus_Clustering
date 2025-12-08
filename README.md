📦 Postalcode Clustering Lambda

본 프로젝트는 우편번호 그룹 기반 배송 클러스터링 엔진으로,
하루 배송 물량을 지역 · 기사 스케줄 · 최대 물량 제약(MAX) 에 따라 자동으로 클러스터링하고
결과를 S3 및 내부 시스템으로 전달하는 Serverless 배치 파이프라인입니다.

🏗️ 전체 아키텍처
EventBridge → Lambda(app.py) 실행
      ↓
DB(MySQL/Postgres)에서 배송 아이템 · 기사 스케줄 · 우편번호 그룹 로딩
      ↓
지역 단위 클러스터링 (K-means++ + 제약 조건 반영)
      ↓
기사 배정 (YELLOW / RAINBOW / ORANGE / WHITE / BLUE)
      ↓
WHITE 및 소형 그룹 후처리 (병합/분할)
      ↓
오버랩 주문 처리
      ↓
S3 업로드 + Slack 모니터링 알림

📁 주요 디렉터리 구조
lambda/
└─ postalcode-clustering/
   ├─ app.py                     # Lambda 엔트리, 전체 파이프라인 오케스트레이션
   ├─ utils/
   │  ├─ run_clustering.py       # 지역별 클러스터링 실행 (Main Engine)
   │  ├─ process_region.py       # 우편번호 그룹 매핑 + K-means 분할/병합 + 기사 배정
   │  ├─ drivers/                # 기사 배정(Y/R/O/WHITE) + 그룹 후처리 로직
   │  ├─ zipcode/                # 우편번호 그룹 로딩 (MySQL/PG)
   │  ├─ data/                   # 배송/스케줄/모델 설정 DB 조회 및 전처리
   │  ├─ overlap/                # 배치 이후 들어오는 주문 오버랩 처리
   │  ├─ upload_cluster_data.py  # S3 업로드 모듈
   │  └─ slack/                  # Slack 알림 템플릿 + 발송 모듈

🧠 핵심 로직 요약
① 지역 단위 클러스터링

우편번호 그룹(폴리곤/zipcodes)과 배송 좌표 공간 매칭

기사 스케줄 + 지역별 MAX 제약 기반 K-means 그룹 분할/병합

각 그룹에

driver_type

driver_code

cluster_label
자동 부여

② 기사 배정 알고리즘

기사 색상 그룹(Y/R/O/WHITE/BLUE) 분리

기사별 최대 가능 물량(MAX) 검증

그룹 중심점 ↔ 기사 위치 기반 최소 거리 배정

WHITE 기사 관련:

소형 그룹 병합

대형 그룹 재분할(K-means)

③ 오버랩 주문 처리

배치 실행 이후 들어온 주문을
가장 가까운 그룹으로 자동 할당

기존 클러스터 라벨·driver_type 유지

④ 결과 저장 및 모니터링

그룹 · 기사 · 배송 아이템 단위 JSON 파일 → S3 저장

Slack Webhook을 통한
성공/에러/통계 메시지 자동 발송

📊 결과 예시 (요약)
zipcode	group	driver_type	cluster_label
01786	A	WHITE	1
01812	B	YELLOW	2
01811	C	BLUE	1
🛠️ 기술 스택
AWS

Lambda

EventBridge

S3

CloudWatch

Python

Pandas

GeoPandas

Shapely

Scikit-learn (K-means++ 기반 클러스터링)

Database

MySQL

PostgreSQL

Monitoring

Slack Webhook Integration

🔍 프로젝트 핵심 가치
⭐ 실서비스 물량 기반 클러스터링

실제 운영 환경(기사 스케줄 · MAX · zipgroup)을 반영한 운영 가능한 실전 알고리즘 구현

🗺️ 공간 기반 클러스터링

우편번호 그룹 + 좌표 기반 K-means 하이브리드 모델

🔁 운영 친화적 기능

오버랩 주문 자동 흡수
Slack 기반 실시간 모니터링

📈 높은 확장성

지역 추가

모델 스키마 변경

기사 정책 변경
에 유연하게 대응 가능
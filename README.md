# Postalcode Clustering Lambda

본 프로젝트는 우편번호 기반 배송 작업을 **운영 제약(기사 스케줄, 용량 제한, 우편번호 그룹 정책)을 반영하여 자동 클러스터링하는 엔진**입니다.  
배송 아이템, 기사 스케줄, 우편번호 그룹을 통합 분석하여 **운영 가능한 단위의 클러스터 생성 및 기사 배정**을 수행하며,  
결과는 S3와 내부 시스템으로 전달됩니다.

전체 파이프라인은 AWS Lambda + EventBridge 기반의 **서버리스 배치 구성**으로 실행됩니다.

---

## 아키텍처 개요

```text
EventBridge → Lambda(app.py)
      ↓
데이터 로딩
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
오버랩 주문 자동 매핑 (배치 이후 유입)
      ↓
S3 업로드 및 Slack 모니터링
```

---

## 디렉터리 구조

```text
lambda/
└─ postalcode-clustering/
   ├─ app.py                      # Lambda 엔트리포인트 및 전체 오케스트레이션
   ├─ utils/
   │  ├─ run_clustering.py        # 지역 단위 클러스터링 실행
   │  ├─ process_region.py        # 공간 매칭 + K-means 조정 + 기사 배정
   │  ├─ drivers/                 # 기사 배정 및 그룹 후처리 로직
   │  ├─ zipcode/                 # 우편번호 그룹(MySQL/PG) 로딩
   │  ├─ data/                    # 배송/스케줄/제약 데이터 로더
   │  ├─ overlap/                 # 오버랩 주문 처리 모듈
   │  ├─ upload_cluster_data.py   # 결과 S3 업로드
   │  └─ slack/                   # Slack 알림 템플릿 및 Webhook 발송
```

---

## 핵심 로직

### 1. 지역 단위 공간 클러스터링

```text
- 우편번호 폴리곤과 배송 좌표 간 공간 매칭
- 기사 스케줄 및 MAX 제약을 반영한 K-means++ 기반 분할/병합
- group_name, cluster_label, driver_type, driver_code 자동 생성
```

단순 거리 기반 K-means가 아닌,  
**실제 운영 제약(기사 근무 지역, 최대 용량, 우편번호 그룹 정책)을 함께 고려한 하이브리드 방식**입니다.

---

### 2. 기사 배정 로직

```text
- 기사 색상(Y/R/O/WHITE/BLUE)별 작업 범위 분리
- 기사별 최대 작업량(MAX)을 기반으로한 제약 검증
- 그룹 중심점 기준 최소 이동 거리 기반 배정
- WHITE 기사:
    • 소형 그룹 병합
    • 대형 그룹 재분할(K-means 활용)
```

운영 팀이 수작업으로 수행하던 로직을 자동화하여  
**작업량 불균형과 비효율을 줄이는 방향으로 설계되었습니다.**

---

### 3. 오버랩 주문 처리

```text
- 배치 실행 이후 유입된 주문을 최근 생성된 클러스터에 자동 매핑
- 기존 cluster_label 및 driver_type 유지
- 지연 발생에도 운영 일관성을 유지하는 구조
```

---

### 4. 결과 저장 및 모니터링

```text
- 배송 아이템 단위, 기사 단위, 클러스터 단위 JSON → S3 저장
- Slack Webhook 기반 실행 결과/통계/오류 자동 보고
```

---

## 출력 예시

```text
zipcode     group    driver_type    cluster_label
01786       A        WHITE          1
01812       B        YELLOW         2
01811       C        BLUE           1
```

---

## 기술 스택

```text
AWS     : Lambda, EventBridge, S3, CloudWatch
Python  : Pandas, GeoPandas, Shapely, scikit-learn(K-means++)
DB      : MySQL, PostgreSQL
Ops     : Slack Webhook 기반 모니터링 및 배치 자동화
```

---

## 프로젝트 특징

```text
• 운영 제약 기반 클러스터링
  - 기사 스케줄, 최대 작업량(MAX), 지역 정책 등을 함께 고려한 프로덕션 수준 로직

• 공간 정보 활용
  - 우편번호 폴리곤 + 좌표 기반 K-means 하이브리드 클러스터링

• 안정적인 운영 자동화
  - 오버랩 주문 처리
  - Slack 실시간 모니터링 및 오류 대응

• 확장성과 유지보수 용이성
  - 지역·우편번호 그룹 정책 변경에 유연히 대응
  - 기사 정책 변경 시 모듈 단위 교체 가능
```

---
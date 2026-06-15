# Delivus Postalcode Clustering Lambda

## 당일배송 허브 운영 병목을 해결한 Production MLOps 시스템

> 당일배송 허브의 수작업 클러스터 편집 병목을 자동화하기 위해 구축한 운영형 클러스터링 시스템입니다.  
> ML 기반 클러스터링과 AWS 서버리스 아키텍처를 결합하여 출차 속도와 운영 효율을 개선했습니다.

---

## Executive Impact

- **허브 편집 시간 38% 단축** (39.5분 → 24.3분)
- **평균 배송지 간 거리 22% 감소** (141.3m → 110.05m)
- **추가 주문 자동 편성 누락률 0%**
- **AWS Lambda + EventBridge + S3** 기반 자동 운영
- 실제 운영팀이 사용하는 **허브 관리자 앱(Hub Admin App)** 연동

---

## 비즈니스 문제 (Business Problem)

당일배송 운영에서는 출차 전 짧은 시간 안에 수백 건의 배송 물량을 기사별로 분류해야 합니다.

기존 운영 방식의 문제점:

- 운영팀의 수작업 클러스터 편집
- 기사별 물량 불균형
- 출차 지연 및 SLA 악화
- 추가 유입 주문 재편성 필요
- 숙련 운영자 의존도가 높음

이러한 병목은 곧 **배송 품질 저하와 운영 비용 증가**로 이어졌습니다.

---

## 내가 수행한 역할 (My Role)

본 프로젝트에서 클러스터링 시스템의 설계부터 운영 적용까지 End-to-End로 수행했습니다.

- 우편번호 그룹 기반 클러스터링 전략 설계
- **KMeans++ + Rule-based Logic** 구현
- 기사 스케줄 / 기사별 MAX 물량 제약 반영
- AWS Lambda 기반 서버리스 배치 시스템 구축
- 결과 데이터 S3 적재 및 허브앱 연동
- Slack 알림 / 모니터링 체계 구축
- KPI 측정 및 지속 개선

---

## 솔루션 개요 (Solution Overview)

본 시스템은 **ML 클러스터링 + 운영 제약조건 + 자동화된 클라우드 운영**을 결합한 구조입니다.

### 핵심 프로세스

1. 배송 아이템 / 기사 스케줄 / 우편번호 그룹 데이터 로딩  
2. 우편번호 그룹(Polygon) 기준 지역 매핑  
3. **KMeans++** 기반 1차 클러스터 생성  
4. 소형 클러스터 병합 및 비효율 그룹 재조정  
5. 기사별 처리량(MAX), 기사 타입 정책 반영  
6. 추가 유입 주문은 **Overlap Clustering**으로 자동 편성  
7. 결과를 S3 저장 후 허브 관리자 앱에 반영

---

## 시스템 아키텍처 (Architecture)

```text
EventBridge Trigger / 수동 실행
            ↓
AWS Lambda (Docker Image)
            ↓
MySQL / PostgreSQL 데이터 조회
            ↓
Clustering Engine
(KMeans++ + Constraint Rules)
            ↓
S3 결과 저장 (JSON)
            ↓
Slack 알림 / CloudWatch Logs
            ↓
허브 관리자 앱
(지도 시각화 + 수동 미세조정)
```

---

## 기술 스택 (Tech Stack)

- **Python**
- Pandas / NumPy / Scikit-learn
- AWS Lambda (Container Image)
- Amazon S3
- EventBridge
- CloudWatch Logs
- Slack Webhook
- MySQL / PostgreSQL
- AWS SAM 배포

---

## 실제 운영 화면 (Real Operation Screenshots)

### 전체 지역 클러스터링 결과

![Hub Overview](./docs/images/image1.png)

### 특정 지역 상세 클러스터 결과

![Cluster Detail](./docs/images/image2.png)

---

## 왜 이 프로젝트가 강한 MLOps 경험인가?

이 프로젝트는 단순 분석용 Notebook 프로젝트가 아닙니다.

**실제 운영 현장의 병목 문제를 ML 시스템으로 해결하고, Production 환경에 배포하여 KPI를 개선한 프로젝트**입니다.

### 증명 가능한 역량

- 비즈니스 문제를 ML 문제로 구조화
- ML 알고리즘과 운영 정책 결합
- AWS 서버리스 운영 자동화
- 데이터 파이프라인 구축
- 장애 알림 / 운영 모니터링
- KPI 기반 지속 개선

---

## 성과 지표 (Measured Results)

| 지표 | 개선 전 | 개선 후 | 효과 |
|---|---:|---:|---:|
| 허브 편집 시간 | 39.5분 | 24.3분 | **38% 단축** |
| 평균 배송지 간 거리 | 141.3m | 110.05m | **22% 감소** |
| 추가 주문 편성 | 수작업 | 자동화 | **누락률 0%** |

---

## 디렉토리 구조 (Repository Structure)

```text
lambda/postalcode-clustering/
├── app.py
├── template.yaml
├── Dockerfile
├── utils/
│   ├── run_clustering.py
│   ├── process_region.py
│   ├── overlap/
│   ├── zipcode/
│   └── slack/
└── events/
```

---

## Key Takeaway

> 운영 현장의 출차 병목을 해결하기 위해 ML 클러스터링 시스템을 직접 설계·배포·운영했으며,  
> AWS 기반 MLOps 방식으로 실제 KPI 개선을 만든 프로젝트입니다.

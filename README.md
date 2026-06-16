# Delivus Postalcode Clustering Lambda

> Korean version: [README_Kver.md](./README_Kver.md)

## Production MLOps System for Solving Same-Day Delivery Hub Bottlenecks

This project is an operational delivery clustering system built to automate the manual cluster editing bottleneck that occurred before same-day delivery dispatch.  
It combines zipcode group-based spatial matching, KMeans++ clustering, driver schedule constraints, MAX capacity constraints, and AWS Lambda-based automation to improve real hub operation KPIs.

---

## Executive Impact

| Metric | Before | After | Impact |
|---|---:|---:|---|
| Hub editing time | 39.5 min | 24.3 min | **38% reduction** |
| Average distance between delivery points | 141.3 m | 110.05 m | **22% reduction** |
| Additional order assignment | Manual | Automated | **0% missing assignment maintained** |
| Operation method | Manual-heavy | Lambda automation | Reduced operator dependency |

---

## Business Problem

In same-day delivery operations, hundreds of delivery items need to be grouped by driver within a short time window before dispatch.  
The existing process required operators to manually adjust clusters on a map, which repeatedly caused the following issues:

- Long manual editing time for the operations team
- Imbalanced delivery volume by driver
- Dispatch delays and SLA volatility
- Additional incoming orders had to be manually assigned again
- High dependency on experienced operators

This bottleneck directly affected delivery quality, dispatch speed, and operational cost.

---

## My Role

I owned the design, implementation, deployment, and operational improvement of the clustering system end-to-end.

- Designed a zipcode group-based clustering strategy
- Implemented KMeans++ based initial clustering logic
- Implemented small-cluster merge and inefficient-group adjustment logic
- Applied driver schedule and driver-level MAX capacity constraints
- Implemented Overlap Clustering for additional incoming orders
- Built a serverless batch system using AWS Lambda Container Image
- Stored result data in S3 and integrated it with the Hub Admin App
- Built Slack alerts and CloudWatch log monitoring
- Measured KPIs and continuously improved the system

---

## Solution Overview

This system combines **ML clustering + spatial matching + operational constraints + serverless automation**.

```text
EventBridge Trigger / Manual Trigger
        ↓
AWS Lambda Container
        ↓
MySQL / PostgreSQL Data Load
        ↓
Zipcode Polygon Matching
        ↓
KMeans++ Clustering
        ↓
Constraint Rules
(driver schedule / max capacity / area policy)
        ↓
Overlap Clustering for Additional Orders
        ↓
S3 JSON Save
        ↓
Slack Alert / CloudWatch Logs
        ↓
Hub Admin App
```

---

## Core Process

### 1. Data Loading

The pipeline loads delivery items, driver schedules, zipcode groups, and regional operation policies.

### 2. Zipcode Polygon Matching

Delivery coordinates are matched with zipcode group polygons to create region-based candidate groups.

### 3. Initial Clustering

KMeans++ is used to generate initial clusters based on delivery coordinate distribution.

### 4. Constraint Adjustment

Real operational constraints are applied.

- Driver-level MAX capacity
- Driver work schedule
- Regional operation policy
- Small-cluster merge
- Overloaded / underloaded cluster adjustment

### 5. Overlap Clustering

Orders that arrive after the initial clustering are automatically assigned to existing clusters based on spatial overlap and distance criteria.

### 6. Operation Integration

Final results are saved to S3 and connected to the Hub Admin App for map-based review.

---

## Real Operation Screenshots

### Hub Overview

![Hub Overview](./docs/images/image1.png)

### Cluster Detail

![Cluster Detail](./docs/images/image2.png)

---

## Tech Stack

| Category | Stack |
|---|---|
| Language | Python |
| Data Processing | Pandas, NumPy |
| ML / Clustering | Scikit-learn, KMeans++ |
| Spatial Data | GeoPandas, Shapely |
| Infrastructure | AWS Lambda, AWS SAM, Docker Image |
| Storage | Amazon S3 |
| Scheduler | EventBridge |
| Database | MySQL, PostgreSQL |
| Monitoring | CloudWatch Logs, Slack Webhook |

---

## Repository Structure

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

## Why This Is Strong MLOps Experience

This is not a notebook-based analysis project. It is a production-oriented MLOps system used in real operations.

- Structured a business bottleneck as an ML clustering problem
- Combined clustering algorithms with real operational constraints
- Automated the workflow using AWS Lambda
- Stored results in S3 and integrated them with an operations system
- Built Slack/CloudWatch-based monitoring
- Improved system performance based on operational KPIs

---

## Security / Redaction

The following items were removed or replaced with sample values for the public portfolio repository.

- Actual database credentials
- Actual AWS Account ID
- Actual S3 bucket name
- Some internal operation table names
- Actual delivery data and customer information
- Deployment-only `samconfig.toml`

---

## Key Takeaway

> I designed, deployed, and operated an ML clustering system to solve hub dispatch bottlenecks, creating measurable KPI improvements through an AWS-based automation pipeline.

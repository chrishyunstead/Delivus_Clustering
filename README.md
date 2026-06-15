# Delivus Postal Code Clustering Lambda

> Korean version: [README_Kver.md](./README_Kver.md)

## Production MLOps System for Reducing Same-Day Delivery Hub Bottlenecks

> A production-grade clustering system built to automate the manual cluster-editing process in a same-day delivery hub.  
> The system combines machine-learning-based clustering with AWS serverless architecture to improve dispatch speed, reduce operational workload, and support real-time hub operations.

---

## Executive Impact

- Reduced **hub cluster editing time by 38%**: 39.5 min → 24.3 min
- Reduced **average distance between delivery destinations by 22%**: 141.3 m → 110.05 m
- Achieved **0% missed assignment rate** for additional incoming orders
- Automated operations using **AWS Lambda + EventBridge + S3**
- Integrated clustering results with the internal **Hub Admin App** used by the operations team

---

## Business Problem

In same-day delivery operations, hundreds of delivery items must be grouped and assigned to drivers within a short time window before dispatch.

Before this project, the hub operations team faced several recurring bottlenecks:

- Manual cluster editing by operators
- Unbalanced delivery volume across drivers
- Dispatch delays and SLA risk
- Reassignment workload for additional incoming orders
- High dependency on experienced operators

These issues directly affected delivery quality, dispatch efficiency, and operational cost.

---

## My Role

I owned the clustering system end-to-end, from algorithm design to production deployment and operational monitoring.

Key responsibilities:

- Designed a postal-code-group-based clustering strategy
- Implemented **KMeans++ with rule-based operational constraints**
- Reflected driver schedules and maximum delivery capacity per driver
- Built a serverless batch processing system using **AWS Lambda**
- Stored clustering results in **Amazon S3** and integrated them with the Hub Admin App
- Implemented Slack notifications and CloudWatch-based monitoring
- Measured KPI improvements and iterated on the clustering logic

---

## Solution Overview

The system combines **ML clustering, business constraints, and automated cloud operations**.

### Core Workflow

1. Load delivery items, driver schedules, and postal code group data
2. Map delivery destinations to postal code group polygons
3. Generate initial clusters using **KMeans++**
4. Merge small clusters and adjust inefficient groups
5. Apply driver capacity limits and driver-type policies
6. Automatically assign additional incoming orders using **overlap clustering**
7. Save results to S3 and expose them to the Hub Admin App

---

## System Architecture

```text
EventBridge Trigger / Manual Execution
            ↓
AWS Lambda (Docker Image)
            ↓
MySQL / PostgreSQL Query
            ↓
Clustering Engine
(KMeans++ + Constraint Rules)
            ↓
S3 Result Storage (JSON)
            ↓
Slack Notification / CloudWatch Logs
            ↓
Hub Admin App
(Map Visualization + Manual Fine-Tuning)
```

---

## Tech Stack

- **Language**: Python
- **Data & ML**: Pandas, NumPy, Scikit-learn
- **Cloud & Infrastructure**: AWS Lambda, Amazon S3, EventBridge, CloudWatch Logs, AWS SAM
- **Database**: MySQL, PostgreSQL
- **Monitoring & Alerting**: Slack Webhook, CloudWatch Logs
- **Deployment**: AWS Lambda Container Image, AWS SAM

---

## Real Operation Screenshots

### Full Hub Clustering Overview

![Hub Overview](./docs/images/image1.png)

### Detailed Cluster View

![Cluster Detail](./docs/images/image2.png)

---

## Why This Is a Strong MLOps Project

This was not a one-off notebook analysis project.  
It was a production system built to solve an actual operational bottleneck, deployed into a live logistics environment, and evaluated through measurable business KPIs.

### Demonstrated Capabilities

- Translated a real business bottleneck into an ML system design
- Combined ML algorithms with operational rules and constraints
- Built an automated AWS serverless batch pipeline
- Designed a data flow from database query to S3 result delivery
- Implemented operational monitoring and failure notifications
- Improved the system based on measured KPI outcomes

---

## Measured Results

| Metric | Before | After | Impact |
|---|---:|---:|---:|
| Hub cluster editing time | 39.5 min | 24.3 min | **38% reduction** |
| Average distance between delivery destinations | 141.3 m | 110.05 m | **22% reduction** |
| Additional order assignment | Manual | Automated | **0% missed assignments** |

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

## Key Takeaway

> I designed, deployed, and operated a production ML clustering system to reduce dispatch bottlenecks in a same-day delivery hub.  
> By combining clustering logic, operational constraints, and AWS-based MLOps, the system produced measurable improvements in real-world logistics operations.

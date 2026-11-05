# FV-SEC001 - Software Engineer Challenge — Ad Performance Aggregator

## Introduction
This is a data processing challenge for Developer candidates applying to our company.  
You will work with a large CSV dataset (~1GB) containing advertising performance records.

The goal is to evaluate your ability to write clean code, handle large datasets efficiently, optimize performance/memory usage, and design a robust data-processing workflow.

---

## Input Data

### Download the Dataset

1. Download the `ad_data.csv.zip` file from this repository folder
2. Unzip it to get the `ad_data.csv` file (~1GB)
3. Use this CSV file for your solution

```bash
# Example: Unzip the file
unzip ad_data.csv.zip
```

### CSV Schema

| Column         | Type      | Description |
|----------------|-----------|-------------|
| campaign_id    | string    | Campaign ID |
| date           | string    | Date in `YYYY-MM-DD` format |
| impressions    | integer   | Number of impressions |
| clicks         | integer   | Number of clicks |
| spend          | float     | Advertising cost (USD) |
| conversions    | integer   | Number of conversions |

### Example:

| campaign_id | date       | impressions | clicks | spend | conversions |
|-------------|------------|-------------|--------|-------|-------------|
| CMP001      | 2025-01-01 | 12000       | 300    | 45.50 | 12          |
| CMP002      | 2025-01-01 | 8000        | 120    | 28.00 | 4           |
| CMP001      | 2025-01-02 | 14000       | 340    | 48.20 | 15          |
| CMP003      | 2025-01-01 | 5000        | 60     | 15.00 | 3           |
| CMP002      | 2025-01-02 | 8500        | 150    | 31.00 | 5           |

---

# 🎯 Task Requirements

You must build a **console application (CLI)** in any programming language (Python, NodeJS, Go, Java, Rust, etc.) that processes the CSV file and produces aggregated analytics.

---

## 1. Aggregate data by `campaign_id`

For each `campaign_id`, compute:

- `total_impressions`
- `total_clicks`
- `total_spend`
- `total_conversions`
- `CTR` = total_clicks / total_impressions  
- `CPA` = total_spend / total_conversions  
  - If conversions = 0, ignore or return `null` for CPA

---

## 2. Generate two result lists

### **A. Top 10 campaigns with the highest CTR**

Output as CSV format.

**Expected output format (`top10_ctr.csv`):**

| campaign_id | total_impressions | total_clicks | total_spend | total_conversions | CTR    | CPA   |
|-------------|-------------------|--------------|-------------|-------------------|--------|-------|
| CMP042      | 125000            | 6250         | 12500.50    | 625               | 0.0500 | 20.00 |
| CMP015      | 340000            | 15300        | 30600.25    | 1530              | 0.0450 | 20.00 |
| CMP008      | 890000            | 35600        | 71200.75    | 3560              | 0.0400 | 20.00 |
| CMP023      | 445000            | 15575        | 31150.00    | 1557              | 0.0350 | 20.00 |
| CMP031      | 670000            | 20100        | 40200.50    | 2010              | 0.0300 | 20.00 |

### **B. Top 10 campaigns with the lowest CPA**

Output as CSV format. Exclude campaigns with zero conversions.

**Expected output format (`top10_cpa.csv`):**

| campaign_id | total_impressions | total_clicks | total_spend | total_conversions | CTR    | CPA   |
|-------------|-------------------|--------------|-------------|-------------------|--------|-------|
| CMP007      | 450000            | 13500        | 13500.00    | 1350              | 0.0300 | 10.00 |
| CMP019      | 780000            | 23400        | 23400.00    | 2340              | 0.0300 | 10.00 |
| CMP033      | 290000            | 8700         | 10440.00    | 870               | 0.0300 | 12.00 |
| CMP012      | 560000            | 16800        | 21840.00    | 1680              | 0.0300 | 13.00 |
| CMP025      | 320000            | 9600         | 13440.00    | 960               | 0.0300 | 14.00 |

---

## 3. Technical Requirements

- The file is large (~1GB).  
   **Your solution must handle large datasets efficiently with good performance and memory optimization.**
- The program should be runnable via CLI, for example: `python aggregator.py --input ad_data.csv --output results/`

---

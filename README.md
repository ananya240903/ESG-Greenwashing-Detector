# 🛡️ ESG-Analyzer: Real-Time Greenwashing Detection
**A Distributed AI Pipeline for ESG Disclosure Verification**

## 📌 Project Overview
I developed this microservice to address the growing challenge of **Greenwashing** in corporate ESG (Environmental, Social, Governance) disclosures. 

The system uses a **Kafka-driven architecture** to ingest disclosures in real-time and processes them using two specialized **Natural Language Processing (NLP)** models to detect high-positivity language that lacks technical substance.

## 🏗️ System Architecture
The project follows a Producer-Consumer microservice pattern:
1. **Producer:** Simulates corporate disclosure streams (Python).
2. **Message Broker:** Apache Kafka handles the real-time data stream (Zookeeper + Broker).
3. **The Brain (Consumer):** A Python microservice utilizing:
   - `yiyanghkust/finbert-esg`: Classifies text into ESG categories.
   - `ProsusAI/finbert`: Analyzes financial sentiment/tone.
4. **Logic:** Flags "Greenwashing" when sentiment is >85% positive but the ESG classification confidence is <60% (vague claims).

## 🛠️ Tech Stack
- **Languages:** Python 3.x
- **Infrastructure:** Apache Kafka, Zookeeper
- **AI/ML:** HuggingFace Transformers, PyTorch, FinBERT
- **Data:** Pandas, Matplotlib (for Risk Reporting)

## 📊 Sample Output
| Company | ESG Category | Sentiment | Risk Score | Status |
| :--- | :--- | :--- | :--- | :--- |
| EnergyInc | Environmental | Positive | 12.4 | ✅ Clean |
| TechCorp | None/General | Positive | 78.2 | 🚩 Greenwash |

## 🚀 How to Run
1. Start Zookeeper & Kafka Broker.
2. Install dependencies: `pip install -r requirements.txt`
3. Run the Analyzer: `python analyzer.py`
4. Run the Test Producer: `python producer_test.py`

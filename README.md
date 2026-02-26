# 🌿 AI-Driven ESG Greenwashing Detector

An end-to-end distributed system designed to ingest corporate ESG disclosures and analyze them for "Greenwashing" risk using specialized Financial NLP models.

## 🏗️ System Architecture
This project follows a **Microservice Architecture** decoupled by a message broker:

1.  **[ingestor-api](./ingestor-api)**: A Java Spring Boot REST API that receives disclosures and produces messages to Kafka.
2.  **[nlp-analyzer](./nlp-analyzer)**: A Python-based AI engine that consumes messages and performs risk scoring using FinBERT.
3.  **Message Broker**: Apache Kafka running in Docker, ensuring reliable data streaming.



## 🛠️ Tech Stack
- **Backend**: Java 17, Spring Boot 3, Hibernate/JPA
- **AI/ML**: Python 3.13, Transformers (HuggingFace), FinBERT
- **Infrastructure**: Docker, Apache Kafka, Zookeeper
- **Database**: H2 (In-memory)

## 🚀 Key Features
- **Scalable Data Stream**: Uses Kafka partitions to allow multiple analyzer instances to work in parallel.
- **FinBERT Integration**: Employs industry-standard NLP models (`finbert-esg` and `finbert-sentiment`) for high-accuracy financial analysis.
- **Automated Visualization**: Generates analytical reports (Bar Charts) comparing the greenwashing risk across different companies.

## 📖 How to Run
1.  **Start Infrastructure**: Run `docker-compose up` in the `ingestor-api` folder.
2.  **Start API**: Run the Spring Boot application via IntelliJ or Maven.
3.  **Start Analyzer**: Run `python analyzer.py` in the `nlp-analyzer` folder.
4.  **Ingest Data**: Send a POST request to `localhost:8080/api/disclosures` using Postman.

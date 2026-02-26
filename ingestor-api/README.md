# 📥 Disclosure Ingestor API

A high-performance Spring Boot service designed to handle corporate ESG (Environmental, Social, and Governance) disclosures. It acts as the gateway for raw data into the analytical pipeline.

## 🚀 Technical Highlights
- **RESTful Architecture**: Provides endpoints for bulk data ingestion via JSON.
- **Asynchronous Processing**: Decouples data reception from analysis by streaming messages to Apache Kafka.
- **Data Persistence**: Uses an H2 Database for local persistence and audit logging.
- **Scalability**: Configured with 3 Kafka partitions to support horizontal scaling of downstream consumers.

## 🛠️ Tech Stack
- **Language**: Java 17
- **Framework**: Spring Boot 3.x
- **Message Broker**: Apache Kafka (Confluent 7.5.0)
- **Database**: H2 (In-memory)
- **Build Tool**: Maven

## 📈 Endpoint Summary
- `POST /api/disclosures`: Accepts a JSON array of corporate disclosures.
- `GET /api/disclosures`: Retrieves all stored disclosures from the database.

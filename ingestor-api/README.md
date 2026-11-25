# ingestor-api

Spring Boot service that accepts BRSR report PDFs, starts them on the analysis pipeline, and serves
what the analyzer found.

1. `POST /api/reports` streams the PDF to the shared reports directory and checks that it really is
   a PDF, hashing it with SHA-256 on the way.
2. If the same file was uploaded before, it returns the existing report (200).
3. Otherwise it saves a `reports` row, then publishes `{"reportId": N}` to the `report.uploaded`
   topic (202). The row is committed before the message is sent, so the parser worker always finds it.

Reading the results (`analysis/`): `GET /api/reports/risk` serves the `report_risk` view, and
`GET /api/reports/{id}/claims?verdict=` serves a report's claims with their verdicts and ranked
evidence. The Python analyzer writes those tables, so this side reads them with plain SQL
(`JdbcTemplate`), not JPA entities.

The table schema is owned by [`db/init/001_schema.sql`](../db/init/001_schema.sql). Hibernate runs with
`ddl-auto=validate`, so the entity and the SQL cannot drift apart without the app failing to start.

| Setting (env var) | Default |
|---|---|
| `DATABASE_URL` | `jdbc:postgresql://localhost:5432/esg` |
| `DATABASE_USER` / `DATABASE_PASSWORD` | `esg` / `esg` |
| `KAFKA_BOOTSTRAP` | `localhost:9092` |
| `REPORTS_DIR` | `../data/reports` |

Tests (`./mvnw test`) use in-memory H2 in PostgreSQL mode with the Kafka publisher mocked, so they
need neither Docker nor a broker. The analysis endpoints are tested with the SQL repository mocked
(H2 has no analyzer tables); the SQL itself was checked against the real Postgres data.

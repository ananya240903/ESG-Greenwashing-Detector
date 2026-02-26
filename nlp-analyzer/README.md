# 🧠 NLP Greenwashing Analyzer

The "Brain" of the project. This Python-based microservice consumes raw disclosure data from Kafka and applies specialized Financial NLP models to detect potential "Greenwashing."

## 🔬 Analysis Methodology
The analyzer uses a two-stage **FinBERT** pipeline to evaluate corporate claims:
1. **ESG Classification**: Categorizes text into Environment, Social, or Governance themes using `yiyanghkust/finbert-esg`.
2. **Sentiment Analysis**: Evaluates the tone (Positive/Neutral/Negative) using `ProsusAI/finbert`.
3. **Risk Scoring**: A custom algorithm calculates a **Greenwashing Risk Score** based on the delta between high-positivity tone and low ESG specificity.

## 📊 Output
- **Real-time Logging**: Flags vague or "hyped" claims in the terminal.
- **Persistence**: Results are stored in `analysis_results.jsonl`.
- **Visualization**: Generates `esg_report.png`, a comparative bar chart of company risk levels.

## ⚙️ Configuration
- **Kafka Consumer**: Subscribed to the `esg-disclosures` topic.
- **Stability**: Uses `confluent-kafka` for robust connectivity in Windows/Docker environments.

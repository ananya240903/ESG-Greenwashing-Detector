import json
import os
from confluent_kafka import Consumer
from transformers import pipeline

# 1. Cleanup old results
if os.path.exists("analysis_results.jsonl"):
    os.remove("analysis_results.jsonl")
    print("🗑️ Old results deleted. Starting a fresh session.")

print("--- [1/3] Loading NLP Engines ---")
print("Engines loaded successfully!")

print("\n--- [2/3] Initializing FinBERT Models ---")
esg_model = pipeline("text-classification", model="yiyanghkust/finbert-esg")
print("✔ ESG Classifier Ready.")

tone_model = pipeline("text-classification", model="ProsusAI/finbert")
print("✔ Sentiment Analyzer Ready.")

print("\n--- [3/3] Connecting to Kafka ---")

conf = {
    'bootstrap.servers': "localhost:9092",
    'group.id': "esg-analyzer-group",
    'auto.offset.reset': 'earliest' 
}

try:
    consumer = Consumer(conf)
    # This matches the topic name in your DisclosureService.java
    consumer.subscribe(['esg-disclosures'])
    print("🚀 Brain is now monitoring the API Ingestion topic...")
except Exception as e:
    print(f"❌ Kafka Error: {e}")

try:
    while True:
        msg = consumer.poll(1.0) 

        if msg is None:
            continue
        if msg.error():
            print(f"Consumer error: {msg.error()}")
            continue

        # Decode the disclosure
        payload = json.loads(msg.value().decode('utf-8'))
        
        # MAPPING LOGIC:
        # Your Disclosure.java uses @JsonProperty("company")
        # so the JSON from Kafka will have the key "company"
        company = payload.get('company', 'Unknown Corp')
        text_data = payload.get('content')
        
        if not text_data:
            continue

        # Run AI Analysis
        esg_res = esg_model(text_data)[0]
        tone_res = tone_model(text_data)[0]
        
        # Scoring Logic
        greenwash_score = (tone_res['score'] * (1 - esg_res['score'])) * 100
        is_vague = esg_res['label'] == 'None' or (esg_res['score'] < 0.7)
        is_hyped = tone_res['label'].lower() == 'positive' and tone_res['score'] > 0.5
        is_greenwashing = is_vague and is_hyped

        # PRINT FORMATTED RESULT
        print("-" * 50)
        print(f"INCOMING FROM PARTITION: [{msg.partition()}]")
        print(f"COMPANY: {company}")
        print(f"ESG CATEGORY: {esg_res['label']} ({esg_res['score']:.2f})")
        print(f"SENTIMENT   : {tone_res['label']} ({tone_res['score']:.2f})")
        print(f"GREENWASHING RISK SCORE: {greenwash_score:.1f}/100")

        if is_greenwashing:
            print(f"🚩 ALERT: POTENTIAL GREENWASHING DETECTED")
        else:
            print(f"✅ CLEAN: Disclosure appears specific/balanced.")
        
        # Save for Report Generator
        result_data = {
            "company": company,
            "esg_score": float(esg_res['score']),
            "tone_score": float(tone_res['score']),
            "risk_score": float(greenwash_score)
        }
        with open("analysis_results.jsonl", "a") as f:
            f.write(json.dumps(result_data) + "\n")
        print("-" * 50)

except KeyboardInterrupt:
    print("\nStopping the Brain...")
finally:
    consumer.close()
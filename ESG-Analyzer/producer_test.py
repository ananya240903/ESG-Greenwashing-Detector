import json
import time
from confluent_kafka import Producer

# Configuration for the Producer
conf = {
    'bootstrap.servers': 'localhost:9092'
}

# Initialize the Producer
producer = Producer(conf)

# Optional: Delivery report callback to confirm Kafka received the message
def delivery_report(err, msg):
    if err is not None:
        print(f"❌ Message delivery failed: {err}")
    else:
        print(f"📤 Sent disclosure from: {msg.key().decode('utf-8') if msg.key() else 'Unknown'}")

# Test Cases: A mix of Greenwashing and Genuine reporting
disclosures = [
    {
        "company": "TechCorp",
        "content": "Our company is the best and we love the planet more than anyone else. Everything we do is amazing and green!"
    },
    {
        "company": "EnergyInc",
        "content": "We have successfully reduced scope 1 carbon emissions by 15% through the installation of solar arrays at our Gujarat facility."
    },
    {
        "company": "FastFashionCo",
        "content": "We are committed to a sustainable future and use eco-friendly vibes in all our marketing campaigns. Buy more, save the earth!"
    },
    {
        "company": "GlobalBank",
        "content": "Our 2025 roadmap includes a $10M investment into community education and diverse hiring practices across our urban branches."
    },
    {
        "company": "PureHype-Ltd",
        "content": "Sustainability is in our DNA. We are the most ethical company to ever exist. No one cares about trees as much as we do."
    },
    {
        "company": "FoodSystems",
        "content": "We faced a 5% increase in water usage this year due to supply chain disruptions, but have implemented a new recycling protocol."
    }
]

print("🚀 Sending 6 test disclosures to Kafka...")

for d in disclosures:
    # Trigger any available delivery report callbacks from previous produce() calls
    producer.poll(0)

    # Produce the message
    # Note: We use 'key' to identify the company easily in logs
    producer.produce(
        'esg-disclosures', 
        json.dumps(d).encode('utf-8'), 
        key=d['company'], 
        callback=delivery_report
    )
    
    time.sleep(1) # Small delay to see the stream move

# Flush ensures all messages are sent before exiting
producer.flush()
print("\n✅ All messages sent. Check your analyzer terminal!")
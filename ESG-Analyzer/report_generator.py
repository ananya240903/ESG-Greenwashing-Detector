import pandas as pd
import matplotlib.pyplot as plt
import json

# 1. Load the data
data = []
with open("analysis_results.jsonl", "r") as f:
    for line in f:
        data.append(json.loads(line))

df = pd.DataFrame(data)

# 2. Group by company and get the average Risk Score
report = df.groupby('company')['risk_score'].mean().sort_values(ascending=False)

# 3. Create the Plot
plt.figure(figsize=(10, 6))
report.plot(kind='bar', color=['red' if x > 50 else 'green' for x in report])

plt.title('Greenwashing Risk Analysis by Company', fontsize=14)
plt.xlabel('Company Name', fontsize=12)
plt.ylabel('Average Risk Score (0-100)', fontsize=12)
plt.axhline(y=50, color='gray', linestyle='--', label='Warning Threshold')
plt.legend()
plt.grid(axis='y', linestyle='--', alpha=0.7)

# 4. Save and Show
plt.savefig('esg_report.png')
print("Graph saved as esg_report.png!")
plt.show()
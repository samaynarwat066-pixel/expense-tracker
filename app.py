from flask import Flask, render_template, request, redirect, jsonify
import sqlite3
import os
import json
import urllib.request
from database import init_db

app = Flask(__name__)
init_db()

# Securely load API key from environment variable
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

def get_db():
    conn = sqlite3.connect('expenses.db')
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def index():
    conn = get_db()
    expenses = conn.execute('SELECT * FROM expenses ORDER BY date DESC').fetchall()
    conn.close()
    return render_template('index.html', expenses=expenses)

@app.route('/add', methods=['POST'])
def add_expense():
    title    = request.form['title']
    amount   = request.form['amount']
    category = request.form['category']
    date     = request.form['date']
    conn = get_db()
    conn.execute('INSERT INTO expenses (title, amount, category, date) VALUES (?, ?, ?, ?)',
                 (title, amount, category, date))
    conn.commit()
    conn.close()
    return redirect('/')

@app.route('/delete/<int:id>')
def delete_expense(id):
    conn = get_db()
    conn.execute('DELETE FROM expenses WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    return redirect('/')

@app.route('/analyze-ai', methods=['POST'])
def analyze_ai():
    if not GROQ_API_KEY:
        return jsonify({'analysis': '⚠️ GROQ_API_KEY is not set.\nRun this in your terminal before starting the app:\n   set GROQ_API_KEY=your_key_here'})

    conn = get_db()
    expenses = conn.execute('SELECT * FROM expenses ORDER BY date DESC').fetchall()
    conn.close()

    if not expenses:
        return jsonify({'analysis': 'No expenses found. Add some expenses first!'})

    # Build data summary for the prompt
    total        = sum(e['amount'] for e in expenses)
    by_category = {}
    lines        = []

    for e in expenses:
        by_category[e['category']] = by_category.get(e['category'], 0) + e['amount']
        lines.append(f"- {e['title']} | ₹{e['amount']} | {e['category']} | {e['date']}")

    category_summary = "\n".join(f"- {k}: ₹{round(v,2)}" for k, v in by_category.items())
    expense_detail   = "\n".join(lines[:30])

    prompt = f"""You are a friendly personal finance advisor for someone in India (₹).
Analyze the expenses and respond using exactly these four ### headers:

### Spending Insights
What patterns do you notice? Which category dominates?

### Overspending Alerts
Which categories look high? Be specific with amounts.

### Budget Recommendations
Suggest a realistic monthly budget for each category.

### Top 3 Action Items
Three concrete steps to save money, each as a dash bullet point.

Keep it concise and motivating.

--- DATA ---
Total: ₹{round(total, 2)}
By category:
{category_summary}
Recent expenses:
{expense_detail}
---"""

    payload = json.dumps({
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 800,
        "temperature": 0.7
    }).encode("utf-8")

    req = urllib.request.Request(
    "https://api.groq.com/openai/v1/chat/completions",
    data    = payload,
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type":  "application/json",
        "User-Agent":    "Mozilla/5.0"
    },
    method = "POST"
)

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result   = json.loads(resp.read().decode("utf-8"))
            analysis = result["choices"][0]["message"]["content"]
            return jsonify({"analysis": analysis})
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        return jsonify({"analysis": f"⚠️ Groq API error {e.code}: {error_body}"}), 500
    except Exception as e:
        return jsonify({"analysis": f"⚠️ Error: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(debug=True)
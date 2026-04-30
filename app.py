from flask import Flask, jsonify
import os
from datetime import datetime

app = Flask(__name__)

@app.route('/health', methods=['GET'])
def health():
    """Ultra-simple health check"""
    return jsonify({
        "status": "healthy", 
        "timestamp": datetime.utcnow().isoformat(),
        "port": os.environ.get('PORT', 'not-set')
    })

@app.route('/', methods=['GET'])
def root():
    """Root endpoint"""
    return jsonify({"message": "Slack Bridge is running!"})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=False)

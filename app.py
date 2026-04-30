"""
Slack Bridge App for Owner Time Reconstruction Agent
"""

import os
import json
from flask import Flask, request, jsonify
from slack_sdk import WebClient
from slack_sdk.signature import SignatureVerifier
from datetime import datetime
import logging

# Configuration
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

SLACK_BOT_TOKEN = os.environ.get('SLACK_BOT_TOKEN')
SLACK_SIGNING_SECRET = os.environ.get('SLACK_SIGNING_SECRET')
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY')
TIME_TRACKING_CHANNEL = os.environ.get('TIME_TRACKING_CHANNEL', '@franck')

slack_client = WebClient(token=SLACK_BOT_TOKEN)
signature_verifier = SignatureVerifier(SLACK_SIGNING_SECRET)

# State management
conversation_state = {}

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "timestamp": datetime.utcnow().isoformat()})

@app.route('/slack/events', methods=['POST'])
def slack_events():
    """Handle Slack events"""
    
    # Verify Slack signature
    if not signature_verifier.is_valid_request(request.get_data(), request.headers):
        return jsonify({"error": "Invalid signature"}), 403
    
    data = request.json
    
    # Handle URL verification
    if data.get('type') == 'url_verification':
        return jsonify({"challenge": data['challenge']})
    
    # Handle message events
    if data.get('type') == 'event_callback':
        event = data['event']
        
        if event['type'] == 'message' and event.get('channel'):
            handle_message(event)
    
    return jsonify({"status": "ok"})

@app.route('/morning-message', methods=['POST'])
def receive_morning_message():
    """Receive morning message from Claude Code routine"""
    
    try:
        data = request.json
        message = data['message']
        date = data['date']
        analysis_data = data.get('analysis', {})
        
        # Store state for this conversation
        conversation_state[date] = {
            'status': 'waiting_for_franck',
            'analysis': analysis_data,
            'messages': [{'role': 'assistant', 'content': message}],
            'started_at': datetime.utcnow().isoformat()
        }
        
        # Post to Slack
        response = slack_client.chat_postMessage(
            channel=TIME_TRACKING_CHANNEL,
            text=message,
            username="Time Reconstruction Agent",
            icon_emoji=":clock1:"
        )
        
        logging.info(f"Posted morning message for {date}")
        return jsonify({'status': 'posted', 'ts': response['ts']})
        
    except Exception as e:
        logging.error(f"Error posting morning message: {e}")
        return jsonify({"error": str(e)}), 500

def handle_message(event):
    """Handle incoming Slack messages"""
    
    if event.get('user') == 'USLACKBOT' or event.get('bot_id'):
        return  # Ignore bot messages
    
    text = event['text'].strip()
    
    # Find active conversation
    active_date = find_active_conversation()
    
    if not active_date:
        respond_to_slack("No active time reconstruction conversation. The morning routine will post the next day's analysis at 7am ET.")
        return
    
    # Handle special commands
    if text.upper() == 'APPROVE':
        handle_approve_command(active_date)
        return
    
    # Regular conversation
    respond_to_slack("✅ I received your message. Full Claude API integration coming soon!")

def handle_approve_command(active_date):
    """Handle APPROVE command"""
    
    respond_to_slack("✅ Processing approved entries... ClickUp integration coming soon!")

def find_active_conversation():
    """Find the active conversation date"""
    
    for date, state in conversation_state.items():
        if state['status'] in ['waiting_for_franck', 'in_progress', 'ready_for_approve']:
            return date
    
    return None

def respond_to_slack(message):
    """Send a message to Slack"""
    
    slack_client.chat_postMessage(
        channel=TIME_TRACKING_CHANNEL,
        text=message,
        username="Time Reconstruction Agent",
        icon_emoji=":clock1:"
    )

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)

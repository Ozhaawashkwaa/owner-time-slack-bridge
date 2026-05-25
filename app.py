"""
Slack Bridge App for Owner Time Reconstruction Agent

Handles real-time conversation between Franck and the Claude routine.
Deployed on Railway.app or similar platform.

Key Features:
- Receives morning messages from Claude Code routine
- Handles Franck's replies and questions
- Triggers Claude API calls with conversation context
- Manages state across the conversation
- Handles APPROVE command to post to ClickUp
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

# State management (in production, use Redis or database)
conversation_state = {}

# ─── Block Kit helpers ────────────────────────────────────────────────────────

def post_slack_message(channel, text=None, blocks=None, thread_ts=None):
    """Post to Slack with Block Kit blocks and a plain-text fallback for notifications."""
    kwargs = {
        "channel": channel,
        "username": "Time Reconstruction Agent",
        "icon_emoji": ":clock1:",
    }
    if text:
        kwargs["text"] = text
    if blocks:
        kwargs["blocks"] = blocks
    if thread_ts:
        kwargs["thread_ts"] = thread_ts
    return slack_client.chat_postMessage(**kwargs)


def _md_to_mrkdwn(text):
    """Convert GitHub markdown to Slack mrkdwn syntax."""
    import re
    # **bold** → *bold*
    text = re.sub(r'\*\*(.+?)\*\*', r'*\1*', text, flags=re.DOTALL)
    # ## Heading / ### Heading → *Heading*
    text = re.sub(r'^#{1,6}\s+(.+)$', r'*\1*', text, flags=re.MULTILINE)
    # Standalone --- or === lines → remove (Block Kit dividers handle section breaks)
    text = re.sub(r'^[-=]{3,}\s*$', '', text, flags=re.MULTILINE)
    # Collapse 3+ blank lines left by removed --- into a single blank line
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text


def _split_to_mrkdwn_blocks(text, max_len=2900):
    """Convert GH markdown → Slack mrkdwn, then split into section blocks (limit: 3000 chars)."""
    text = _md_to_mrkdwn(text)
    blocks = []
    paragraphs = text.split("\n\n")
    current = ""
    for para in paragraphs:
        candidate = (current + "\n\n" + para).strip() if current else para
        if len(candidate) > max_len:
            if current:
                blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": current.strip()}})
            current = para
        else:
            current = candidate
    if current:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": current.strip()}})
    return blocks


def build_no_active_conversation_blocks():
    """Block Kit layout for the 'no active conversation' reply."""
    return [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "Owner Time Reconstruction", "emoji": True},
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "No active time reconstruction conversation is currently open.\n\n"
                    "The morning routine will post the next day's analysis at *7am ET*.\n\n"
                    "You can also ask me to reopen a specific day once the routine/state layer is connected."
                ),
            },
        },
    ]


def build_morning_message_blocks(date, message, analysis):
    """
    Build Block Kit blocks for the morning time reconstruction message.

    The `analysis` dict is provided by routine/slack_bridge_client.py and contains:
        aw_total_minutes, fit_summary {strong, partial, weak},
        blocks_count, questions_count, ghost_meetings_count, version

    FUTURE: when the routine passes fully structured sections (proposed_entries,
    questions list, off-computer data), replace _split_to_mrkdwn_blocks() here
    with dedicated section/context/input blocks per message section.
    """
    aw_min = analysis.get("aw_total_minutes", 0)
    aw_hrs = f"{aw_min // 60}h{aw_min % 60:02d}"
    fs = analysis.get("fit_summary", {})
    summary_line = (
        f"*AW actif:* {aw_hrs}  |  "
        f"*Fits:* {fs.get('strong', 0)} strong / {fs.get('partial', 0)} partial / {fs.get('weak', 0)} weak  |  "
        f"*Blocs:* {analysis.get('blocks_count', '?')}  |  "
        f"*Questions:* {analysis.get('questions_count', '?')}"
    )

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"Owner Time Reconstruction — {date}", "emoji": True},
        },
        {"type": "divider"},
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": summary_line}],
        },
        {"type": "divider"},
    ]

    # Body: Claude-generated message split into mrkdwn section blocks
    blocks += _split_to_mrkdwn_blocks(message)

    blocks += [
        {"type": "divider"},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "_Réponds à ce message pour continuer. Tape `APPROVE` quand tout est confirmé._",
            },
        },
    ]
    return blocks


# ─── Flask routes ─────────────────────────────────────────────────────────────

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy", 
        "timestamp": datetime.utcnow().isoformat(),
        "port": os.environ.get('PORT', 'not-set')
    })

@app.route('/slack/events', methods=['POST'])
def slack_events():
    """Handle Slack events with deduplication"""
    
    data = request.get_json()
    
    # Handle URL verification
    if data and data.get('type') == 'url_verification':
        return {'challenge': data['challenge']}
    
    # Handle messages with deduplication
    if data and data.get('type') == 'event_callback':
        event = data.get('event', {})
        
        # Only respond to actual user messages (not bot messages)
        if (event.get('type') == 'message' and 
            not event.get('bot_id') and 
            not event.get('subtype') and
            event.get('user')):
            
            try:
                post_slack_message(
                    channel=event.get('channel'),
                    text="No active time reconstruction conversation. The morning routine will post the next day's analysis at 7am ET.",
                    blocks=build_no_active_conversation_blocks(),
                )
            except Exception as e:
                print(f"Error sending message: {e}")
    
    return {'status': 'ok'}

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
        
        # Build Block Kit blocks from message + analysis metadata
        blocks = build_morning_message_blocks(date, message, analysis_data)

        # Post to Slack; plain text is the notification fallback
        response = post_slack_message(
            channel=TIME_TRACKING_CHANNEL,
            text=f"Owner Time Reconstruction — {date}",
            blocks=blocks,
        )
        
        logging.info(f"Posted morning message for {date}")
        return jsonify({'status': 'posted', 'ts': response['ts']})
        
    except Exception as e:
        logging.error(f"Error posting morning message: {e}")
        return jsonify({"error": str(e)}), 500

def handle_message(event):
    """Handle incoming Slack messages from Franck"""
    
    if event.get('user') == 'USLACKBOT' or event.get('bot_id'):
        return  # Ignore bot messages
    
    text = event['text'].strip()
    user_id = event['user']
    
    # Find active conversation
    active_date = find_active_conversation()
    
    if not active_date:
        respond_to_slack("No active time reconstruction conversation. The morning routine will post the next day's analysis at 7am ET.")
        return
    
    # Handle special commands
    if text.upper() == 'APPROVE':
        handle_approve_command(active_date)
        return
    
    if text.upper().startswith('SKIP'):
        handle_skip_command(active_date, text)
        return
    
    # Regular conversation - call Claude API
    handle_conversation(active_date, text)

def handle_conversation(date, user_message):
    """Handle conversation with Claude API"""
    
    state = conversation_state[date]
    state['messages'].append({'role': 'user', 'content': user_message})
    
    # Build context for Claude API call
    system_prompt = build_conversation_prompt(state)
    
    # Call Claude API
    response = call_claude_api(system_prompt, state['messages'])
    
    # Update state
    state['messages'].append({'role': 'assistant', 'content': response})
    
    # Check if response contains approval table
    if "| # | Duration |" in response:
        state['status'] = 'ready_for_approve'
    
    # Post response to Slack
    respond_to_slack(response)

def handle_approve_command(date):
    """Handle APPROVE command to post time entries to ClickUp"""
    
    state = conversation_state[date]
    
    if state['status'] != 'ready_for_approve':
        respond_to_slack("❌ Nothing ready to approve yet. Please answer the remaining questions first.")
        return
    
    try:
        # Extract approved entries from conversation
        entries = extract_approved_entries(state)
        
        # Post to ClickUp
        results = post_entries_to_clickup(entries)
        
        # Update state
        state['status'] = 'completed'
        
        # Respond with results
        success_count = sum(1 for r in results if r['success'])
        total_count = len(results)
        
        message = f"✅ Posted {success_count}/{total_count} entries to ClickUp."
        
        if success_count < total_count:
            failed = [r for r in results if not r['success']]
            message += f"\n\n❌ Failed entries:\n"
            for fail in failed:
                message += f"• {fail['description']}: {fail['error']}\n"
        
        respond_to_slack(message)
        
    except Exception as e:
        logging.error(f"Error in APPROVE command: {e}")
        respond_to_slack(f"❌ Error posting to ClickUp: {str(e)}")

def handle_skip_command(date, text):
    """Handle SKIP command for partial completion"""
    
    # Extract what to skip from command
    # SKIP [reason] or SKIP DATE [reason]
    
    state = conversation_state[date]
    state['status'] = 'skipped'
    
    respond_to_slack(f"⏭️ Skipped {date}. {text[4:].strip()}")

def call_claude_api(system_prompt, messages):
    """Call Claude API with conversation context"""
    
    # Build full prompt with behavior spec and current state
    # Include MCP servers for ClickUp, Google Calendar, etc.
    
    api_payload = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 1000,
        "messages": messages,
        "system": system_prompt,
        "mcp_servers": [
            {"type": "url", "url": "https://mcp.clickup.com/mcp", "name": "clickup"},
            {"type": "url", "url": "https://calendarmcp.googleapis.com/mcp/v1", "name": "google-calendar"},
            {"type": "url", "url": "https://gmailmcp.googleapis.com/mcp/v1", "name": "gmail"},
            {"type": "url", "url": "https://drivemcp.googleapis.com/mcp/v1", "name": "google-drive"}
        ]
    }
    
    # Make API call (placeholder for now)
    # In production, use actual Anthropic API
    return "I received your message. Full Claude API integration coming soon!"

def build_conversation_prompt(state):
    """Build system prompt for Claude API call"""
    
    # Include agent_behavior_spec.md rules
    # Include current analysis data
    # Include conversation history
    # Include ClickUp mapping context
    
    return """
    You are the Owner Time Reconstruction Agent. Your job is to help Franck accurately track his billable time.
    
    You have access to:
    - ActivityWatch data for this day
    - Google Calendar events
    - Gmail signals  
    - ClickUp workspace structure
    - Previous conversation context
    
    Follow the rules in agent_behavior_spec.md exactly.
    Ask clarifying questions when needed.
    Produce the approval table only when all questions are resolved.
    
    Current conversation state: [state data here]
    """

def extract_approved_entries(state):
    """Extract approved entries from conversation for ClickUp posting"""
    
    # Parse the final approval table from conversation
    # Extract task IDs, durations, descriptions
    
    return []

def post_entries_to_clickup(entries):
    """Post time entries to ClickUp"""
    
    results = []
    
    for entry in entries:
        try:
            # Use ClickUp API to create time entry
            # Handle task creation if needed
            
            results.append({
                'success': True,
                'description': entry['description'],
                'task_id': entry['task_id']
            })
            
        except Exception as e:
            results.append({
                'success': False,
                'description': entry['description'],
                'error': str(e)
            })
    
    return results

def find_active_conversation():
    """Find the active conversation date"""
    
    for date, state in conversation_state.items():
        if state['status'] in ['waiting_for_franck', 'in_progress', 'ready_for_approve']:
            return date
    
    return None

def respond_to_slack(message):
    """Send a message to the Slack channel using mrkdwn blocks."""
    post_slack_message(
        channel=TIME_TRACKING_CHANNEL,
        text=message,
        blocks=_split_to_mrkdwn_blocks(message),
    )

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=False)

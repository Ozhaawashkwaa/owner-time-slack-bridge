#!/usr/bin/env python3
"""
Slack Bridge App for Owner Time Reconstruction Agent - Version Conservative

GARDE LA STRUCTURE EXACTE DE L'ANCIEN CODE
AJOUTE SEULEMENT LA RECONNAISSANCE RÉTROACTIVE

Deployed on Railway.app
"""

import os
import json
import re
import requests
from flask import Flask, request, jsonify
from datetime import datetime, timedelta
import logging

# Configuration - IDENTIQUE À L'ANCIEN CODE
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

SLACK_BOT_TOKEN = os.environ.get('SLACK_BOT_TOKEN')
SLACK_SIGNING_SECRET = os.environ.get('SLACK_SIGNING_SECRET')
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY')
TIME_TRACKING_CHANNEL = os.environ.get('TIME_TRACKING_CHANNEL')

# User configuration - EXACTEMENT COMME AVANT
FRANCK_USER_ID = "U079HU5EM99"  # User ID de Franck

# State management - IDENTIQUE
conversation_state = {}

@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint - IDENTIQUE"""
    return {"status": "healthy", "version": "conservative-retroactive"}, 200

@app.route("/slack/events", methods=["POST"])
def handle_slack_events():
    """Handle Slack events - STRUCTURE IDENTIQUE AVEC AJOUT MINIMAL"""
    data = request.json
    
    # URL verification challenge - IDENTIQUE
    if "challenge" in data:
        return {"challenge": data["challenge"]}
    
    # Handle events - IDENTIQUE
    if "event" in data:
        event = data["event"]
        
        # Process message events - IDENTIQUE
        if event["type"] == "message" and "bot_id" not in event:
            user_id = event["user"]
            channel_id = event["channel"]
            message_text = event.get("text", "").strip()
            
            # ⚡ NOUVELLE LOGIQUE RÉTROACTIVE (insertion minimale)
            if user_id == FRANCK_USER_ID and channel_id == TIME_TRACKING_CHANNEL:
                if check_and_handle_retroactive_command(message_text, channel_id):
                    return "", 200  # Sortie rapide si commande rétroactive gérée
            
            # 🔄 LOGIQUE ORIGINALE CONSERVÉE EXACTEMENT
            if user_id == FRANCK_USER_ID and channel_id == TIME_TRACKING_CHANNEL:
                response = generate_response(message_text)
                
                if response:
                    send_slack_message(channel_id, response)
    
    return "", 200

def check_and_handle_retroactive_command(message_text, channel_id):
    """
    🆕 FONCTION AJOUTÉE - Vérifie les commandes rétroactives
    Retourne True si commande rétroactive traitée, False sinon
    """
    try:
        text = message_text.lower().strip()
        
        # Patterns simples de reconnaissance
        retroactive_patterns = [
            # Français
            r"(?:reconstituer|reconstruire|analyser?)\s+.*temps.*(?:pour|du|de)\s+(.+)",
            r"(?:est.ce\s+qu.on\s+peut|peux.tu)\s+.*(?:reconstituer|reconstruire)\s+.*temps.*(?:pour|du|de)\s+(.+)",
            
            # Anglais 
            r"reconstruct\s+(?:my\s+)?(?:time\s+)?(?:for\s+)?(.+)",
            r"analyze\s+(?:my\s+)?(?:time\s+)?(?:for\s+)?(.+)",
        ]
        
        for pattern in retroactive_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                date_str = match.group(1).strip()
                target_date = parse_simple_date(date_str)
                
                if target_date:
                    send_slack_message(channel_id, f"🔄 **Reconnaissance de commande rétroactive!**\n\nDate détectée: {target_date}\nTexte original: {date_str}\n\n⚠️ **Fonctionnalité en développement** - L'analyse complète sera disponible après intégration Claude Code.")
                    return True
                    
        return False
        
    except Exception as e:
        logging.error(f"Error in retroactive command check: {e}")
        return False

def parse_simple_date(date_str):
    """Parse simple de date - version basique pour test"""
    try:
        date_str = date_str.lower().strip()
        
        # Format ISO
        if re.search(r'\d{4}-\d{2}-\d{2}', date_str):
            iso_match = re.search(r'(\d{4}-\d{2}-\d{2})', date_str)
            return iso_match.group(1)
            
        # Dates relatives simples
        today = datetime.now().date()
        
        if 'hier' in date_str or 'yesterday' in date_str:
            yesterday = today - timedelta(days=1)
            return yesterday.strftime('%Y-%m-%d')
            
        # Français: "27 avril"
        french_match = re.search(r'(\d{1,2})\s+(avril|mai|juin)', date_str)
        if french_match:
            day = french_match.group(1).zfill(2)
            month_name = french_match.group(2)
            
            month_map = {'avril': '04', 'mai': '05', 'juin': '06'}
            month = month_map.get(month_name)
            
            if month:
                year = str(datetime.now().year)
                return f"{year}-{month}-{day}"
        
        return None
        
    except Exception as e:
        logging.error(f"Error parsing date '{date_str}': {e}")
        return None

def generate_response(message_text):
    """
    Generate response for regular conversations - FONCTION ORIGINALE CONSERVÉE
    """
    text = message_text.lower().strip()
    
    # Check if this is part of an ongoing reconstruction conversation
    if any(word in text for word in ['oui', 'yes', 'approve', 'correct', 'exact']):
        return "Parfait! Je procède à la création des entrées dans ClickUp avec ces informations validées."
    
    elif any(word in text for word in ['non', 'no', 'change', 'modify', 'incorrect']):
        return "D'accord, que veux-tu modifier? Donne-moi les corrections et je mettrai à jour les propositions."
    
    elif 'help' in text or 'aide' in text:
        return """Commandes disponibles:
        
**Reconstruction rétroactive (NOUVEAU):**
• `reconstituer mes temps pour le 27 avril`
• `reconstruct 2026-04-27`
• `analyze yesterday`

**Conversation courante:**
• `oui/yes` - Approuver les entrées proposées
• `non/change` - Modifier les propositions  
• `status` - Voir le statut actuel

La routine matinale automatique s'exécute à 6h EST et analyse le jour précédent."""
    
    else:
        return "No active time reconstruction conversation. The morning routine will post the next day's analysis at 7am ET."

@app.route("/morning-message", methods=["POST"])
def handle_morning_message():
    """
    Handle morning messages from Claude Code routine - FONCTION ORIGINALE CONSERVÉE
    """
    try:
        data = request.json
        message = data.get('message', '')
        date = data.get('date', '')
        
        if message and TIME_TRACKING_CHANNEL:
            # Add context that this is from the daily routine
            formatted_message = f"🌅 **Routine Matinale - Analyse {date}**\n\n{message}"
            send_slack_message(TIME_TRACKING_CHANNEL, formatted_message)
            
            return {"status": "success", "message": "Morning analysis sent to Slack"}
        
        return {"status": "error", "message": "Missing message or channel"}, 400
        
    except Exception as e:
        logging.error(f"Error handling morning message: {e}")
        return {"status": "error", "message": str(e)}, 500

def send_slack_message(channel_id, text):
    """Send message to Slack - FONCTION ORIGINALE CONSERVÉE"""
    try:
        url = "https://slack.com/api/chat.postMessage"
        headers = {
            "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
            "Content-Type": "application/json"
        }
        data = {
            "channel": channel_id,
            "text": text,
            "parse": "none"
        }
        
        response = requests.post(url, headers=headers, json=data, timeout=10)
        
        if response.status_code != 200:
            logging.error(f"Slack API error: {response.status_code}")
        else:
            response_data = response.json()
            if not response_data.get("ok"):
                logging.error(f"Slack API error: {response_data.get('error')}")
            
    except Exception as e:
        logging.error(f"Error sending Slack message: {e}")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)

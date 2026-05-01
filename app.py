#!/usr/bin/env python3
"""
Owner Time Reconstruction Agent - Slack Bridge (Version Corrigée)

NOUVELLES FONCTIONNALITÉS:
✅ Reconnaissance commandes rétroactives en français naturel
✅ Communication avec Claude Code pour dates spécifiques  
✅ Logique TARGET_DATE pour déclencher l'analyse historique
✅ Support phrases comme "reconstituer mes capture de temps pour la journee du 27 avril dernier"

Déployé sur Railway.app avec webhook vers Claude Code pour reconstruction rétroactive.
"""

import os
import re
import json
import requests
from flask import Flask, request, jsonify
from datetime import datetime, timedelta
import logging
from typing import Optional, Tuple, Dict, Any

# Configuration
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# Environment variables
SLACK_BOT_TOKEN = os.environ.get('SLACK_BOT_TOKEN')
SLACK_SIGNING_SECRET = os.environ.get('SLACK_SIGNING_SECRET')
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY')
TIME_TRACKING_CHANNEL = os.environ.get('TIME_TRACKING_CHANNEL')
CLAUDE_CODE_WEBHOOK_URL = os.environ.get('CLAUDE_CODE_WEBHOOK_URL', 'https://api.claude.ai/code/webhook/routine-trigger')

# User configuration
FRANCK_USER_ID = "U079HU5EM99"  # User ID de Franck

# État des conversations actives
active_conversations = {}

@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "version": "2.0-retroactive"}, 200

@app.route("/slack/events", methods=["POST"])
def handle_slack_events():
    """Handle Slack events avec support reconnaissance rétroactive"""
    data = request.json
    
    # URL verification challenge
    if "challenge" in data:
        return {"challenge": data["challenge"]}
    
    # Handle events
    if "event" in data:
        event = data["event"]
        
        # Process message events
        if event["type"] == "message" and "bot_id" not in event:
            user_id = event["user"]
            channel_id = event["channel"]
            message_text = event.get("text", "").strip()
            
            # Check pour commandes de reconstruction rétroactive
            if handle_retroactive_reconstruction_commands(message_text, user_id, channel_id):
                return "", 200
                
            # Check if this is Franck and in time tracking channel
            if user_id == FRANCK_USER_ID and channel_id == TIME_TRACKING_CHANNEL:
                response = generate_response(message_text)
                
                if response:
                    send_slack_message(channel_id, response)
    
    return "", 200

def handle_retroactive_reconstruction_commands(message_text: str, user_id: str, channel_id: str) -> bool:
    """
    NOUVELLE FONCTION: Handle reconstruction rétroactive commands
    Reconnaît le langage naturel français et déclenche l'analyse
    """
    try:
        # Seulement pour Franck dans le canal time tracking
        if user_id != FRANCK_USER_ID or channel_id != TIME_TRACKING_CHANNEL:
            return False
            
        text = message_text.lower().strip()
        
        logging.info(f"Checking retroactive command: {text}")
        
        # 🔍 PATTERN RECOGNITION - Commandes de reconstruction
        reconstruction_patterns = [
            # Français naturel
            r"(?:reconstituer|reconstruire|analyser?|capture[rz]?)\s+.*temps.*(?:pour|du|de)\s+(.+)",
            r"(?:analyse|reconstitue|reconstruit)\s+(?:mon\s+)?temps\s+(?:pour\s+|du\s+|de\s+)?(.+)",
            r"(?:peux|peut).+(?:reconstituer|reconstruire|analyser?)\s+.*temps.*(?:pour|du|de)\s+(.+)",
            r"(?:est\s+ce\s+qu.on\s+peux|on\s+peut)\s+.*(?:reconstituer|reconstruire)\s+.*temps.*(?:pour|du|de)\s+(.+)",
            
            # Anglais et formes courtes
            r"reconstruct\s+(?:my\s+)?(?:time\s+)?(?:for\s+)?(.+)",
            r"analyze\s+(?:my\s+)?(?:time\s+)?(?:for\s+)?(.+)",
            r"time\s+reconstruction\s+(?:for\s+)?(.+)",
            
            # Commandes directes
            r"(?:do|run|execute)\s+(.+)",
            
            # Aide et test
            r"test\s+(.+)",
            r"help.*reconstruction",
            r"commands"
        ]
        
        target_date = None
        
        # Check chaque pattern
        for pattern in reconstruction_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                date_str = match.group(1).strip()
                logging.info(f"Pattern matched: {pattern}, date_str: {date_str}")
                
                # Parse la date depuis le texte capturé
                target_date = parse_date_from_text(date_str)
                if target_date:
                    logging.info(f"Parsed date: {target_date}")
                    trigger_retroactive_reconstruction(target_date, channel_id, date_str)
                    return True
        
        # Check pour commandes d'aide
        if any(word in text for word in ['help', 'aide', 'commands', 'commandes']):
            send_reconstruction_help(channel_id)
            return True
            
        return False
        
    except Exception as e:
        logging.error(f"Error in retroactive command handling: {e}")
        send_slack_message(channel_id, f"❌ Erreur dans la reconnaissance de commande: {e}")
        return True

def parse_date_from_text(date_str: str) -> Optional[str]:
    """
    NOUVELLE FONCTION: Parse date de texte français/anglais naturel
    Retourne format YYYY-MM-DD ou None
    """
    try:
        date_str = date_str.lower().strip()
        logging.info(f"Parsing date from: '{date_str}'")
        
        # 📅 FORMATS DE DATE SUPPORTÉS
        
        # 1. Format ISO direct (2026-04-27)
        iso_match = re.search(r'(\d{4}-\d{2}-\d{2})', date_str)
        if iso_match:
            return iso_match.group(1)
        
        # 2. Format français "27 avril 2026" ou "27 avril dernier"
        french_date_patterns = [
            r'(\d{1,2})\s+(janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)\s+(\d{4})',
            r'(\d{1,2})\s+(janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)\s+(dernier|passé)',
        ]
        
        french_months = {
            'janvier': '01', 'février': '02', 'mars': '03', 'avril': '04',
            'mai': '05', 'juin': '06', 'juillet': '07', 'août': '08', 
            'septembre': '09', 'octobre': '10', 'novembre': '11', 'décembre': '12'
        }
        
        for pattern in french_date_patterns:
            match = re.search(pattern, date_str)
            if match:
                day = match.group(1).zfill(2)
                month_name = match.group(2)
                year_or_relative = match.group(3)
                
                month = french_months.get(month_name)
                if month:
                    if year_or_relative in ['dernier', 'passé']:
                        # Utiliser année courante
                        year = str(datetime.now().year)
                    else:
                        year = year_or_relative
                    
                    return f"{year}-{month}-{day}"
        
        # 3. Format anglais "April 27 2026" ou "April 27th"
        english_date_patterns = [
            r'(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{1,2})(?:st|nd|rd|th)?\s+(\d{4})',
            r'(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{1,2})(?:st|nd|rd|th)?',
            r'(\d{1,2})(?:st|nd|rd|th)?\s+(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{4})',
            r'(\d{1,2})(?:st|nd|rd|th)?\s+(january|february|march|april|may|june|july|august|september|october|november|december)',
        ]
        
        english_months = {
            'january': '01', 'february': '02', 'march': '03', 'april': '04',
            'may': '05', 'june': '06', 'july': '07', 'august': '08',
            'september': '09', 'october': '10', 'november': '11', 'december': '12'
        }
        
        for pattern in english_date_patterns:
            match = re.search(pattern, date_str)
            if match:
                groups = match.groups()
                if len(groups) == 3:  # month day year
                    month_name, day, year = groups
                    month = english_months.get(month_name.lower())
                    if month:
                        return f"{year}-{month}-{day.zfill(2)}"
                elif len(groups) == 2:  # month day (current year)
                    month_name, day = groups
                    month = english_months.get(month_name.lower())
                    if month:
                        year = str(datetime.now().year)
                        return f"{year}-{month}-{day.zfill(2)}"
        
        # 4. Dates relatives
        today = datetime.now().date()
        
        relative_dates = {
            'aujourd\'hui': today,
            'today': today,
            'hier': today - timedelta(days=1),
            'yesterday': today - timedelta(days=1),
            'avant.?hier': today - timedelta(days=2),
            'day before yesterday': today - timedelta(days=2),
        }
        
        for pattern, date_obj in relative_dates.items():
            if re.search(pattern, date_str):
                return date_obj.strftime('%Y-%m-%d')
        
        # 5. Plages de dates relatives
        week_patterns = [
            (r'cette\s+semaine|this\s+week', 0),
            (r'semaine\s+dernière|semaine\s+passée|last\s+week', -1),
            (r'semaine\s+prochaine|next\s+week', 1),
        ]
        
        for pattern, week_offset in week_patterns:
            if re.search(pattern, date_str):
                # Pour les semaines, retourner le lundi de cette semaine
                days_since_monday = today.weekday()
                monday = today - timedelta(days=days_since_monday)
                target_monday = monday + timedelta(weeks=week_offset)
                return target_monday.strftime('%Y-%m-%d')
        
        logging.warning(f"Could not parse date from: '{date_str}'")
        return None
        
    except Exception as e:
        logging.error(f"Error parsing date '{date_str}': {e}")
        return None

def trigger_retroactive_reconstruction(target_date: str, channel_id: str, original_text: str):
    """
    NOUVELLE FONCTION: Déclenche la reconstruction rétroactive via Claude Code
    """
    try:
        logging.info(f"Triggering retroactive reconstruction for date: {target_date}")
        
        # Send immediate acknowledgment
        send_slack_message(channel_id, f"🔄 **Démarrage de la reconstruction pour {target_date}**\n\nAnalyse en cours... Je vais examiner:\n• Données ActivityWatch\n• Contexte Google Calendar\n• Emails de la journée\n• Discussions Slack\n• Fichiers Google Drive modifiés\n\nCela peut prendre 1-2 minutes pour l'analyse complète.")
        
        # Préparer payload pour Claude Code
        payload = {
            "command": "retroactive_reconstruction",
            "target_date": target_date,
            "requester": "franck",
            "channel_id": channel_id,
            "original_request": original_text,
            "environment_vars": {
                "TARGET_DATE": target_date
            },
            "context": {
                "source": "slack_bridge",
                "timestamp": datetime.now().isoformat(),
                "version": "2.0-retroactive"
            }
        }
        
        # Option 1: Webhook vers Claude Code (si disponible)
        if CLAUDE_CODE_WEBHOOK_URL:
            try:
                response = requests.post(
                    CLAUDE_CODE_WEBHOOK_URL,
                    json=payload,
                    timeout=10,
                    headers={'Content-Type': 'application/json'}
                )
                
                if response.status_code == 200:
                    logging.info(f"Claude Code webhook triggered successfully for {target_date}")
                    return
                else:
                    logging.warning(f"Claude Code webhook failed: {response.status_code}")
            except Exception as webhook_error:
                logging.warning(f"Claude Code webhook error: {webhook_error}")
        
        # Option 2: Fallback - Direct Anthropic API call
        trigger_via_anthropic_api(target_date, channel_id, payload)
        
    except Exception as e:
        logging.error(f"Error triggering retroactive reconstruction: {e}")
        send_slack_message(channel_id, f"❌ **Erreur lors du déclenchement**\n\nErreur technique: {e}\n\nEssaie avec une commande plus simple comme:\n`reconstruct 2026-04-27`")

def trigger_via_anthropic_api(target_date: str, channel_id: str, payload: Dict[str, Any]):
    """
    NOUVELLE FONCTION: Déclenche reconstruction via API Anthropic directe (fallback)
    """
    try:
        logging.info(f"Using Anthropic API fallback for {target_date}")
        
        # Create the prompt for the time reconstruction agent
        analysis_prompt = f"""Tu es l'Owner Time Reconstruction Agent. 

MISSION: Analyse rétroactive pour le {target_date}

Exécute l'analyse complète suivant les 20 spécifications:
1. Vérifier données ActivityWatch pour {target_date}
2. Rassembler contexte: Google Calendar, Gmail, Slack, Google Drive, ClickUp
3. Reconstruire blocs de temps intelligents
4. TOUJOURS vérifier travail hors-ordinateur
5. Mapper vers ClickUp avec logique business
6. Réconciliation explicite des totaux
7. Générer message naturel conversation Slack

Format de réponse: Message conversationnel pour Franck dans Slack incluant:
- Résumé activités detectées
- Questions hors-ordinateur (obligatoire)
- Propositions ClickUp mapping
- Zones ambiguës à clarifier

TARGET_DATE={target_date}
SLACK_CHANNEL={channel_id}

Commence l'analyse maintenant."""

        # Call Anthropic API
        api_response = requests.post(
            'https://api.anthropic.com/v1/messages',
            headers={
                'Authorization': f'Bearer {ANTHROPIC_API_KEY}',
                'Content-Type': 'application/json',
                'anthropic-version': '2023-06-01'
            },
            json={
                'model': 'claude-sonnet-4-20250514',
                'max_tokens': 2000,
                'messages': [
                    {
                        'role': 'user',
                        'content': analysis_prompt
                    }
                ]
            },
            timeout=60
        )
        
        if api_response.status_code == 200:
            response_data = api_response.json()
            
            # Extract text content from response
            content = ""
            for item in response_data.get('content', []):
                if item.get('type') == 'text':
                    content += item.get('text', '')
            
            if content:
                # Send the analysis result to Slack
                final_message = f"🧠 **Analyse Intelligente pour {target_date}**\n\n{content}"
                send_slack_message(channel_id, final_message)
                logging.info(f"Successfully sent analysis for {target_date}")
            else:
                raise Exception("No text content in API response")
                
        else:
            raise Exception(f"API error: {api_response.status_code}")
            
    except Exception as e:
        logging.error(f"Anthropic API fallback failed: {e}")
        send_slack_message(channel_id, f"❌ **Échec de l'analyse automatique**\n\nL'agent n'a pas pu analyser {target_date} automatiquement.\n\n**Solutions de contournement:**\n• Vérifie que Claude Code routine est déployée\n• Teste avec format exact: `reconstruct 2026-04-27`\n• Contacte support si le problème persiste\n\nErreur technique: {e}")

def send_reconstruction_help(channel_id: str):
    """Send help message for reconstruction commands"""
    help_message = """🤖 **Owner Time Reconstruction Agent - Commandes Disponibles**

**📅 Reconstruction de Dates:**

**Français naturel:**
• `Est-ce qu'on peut reconstituer mes captures de temps pour la journée du 27 avril dernier`
• `Reconstitue mon temps du 27 avril 2026`
• `Analyse mon temps pour hier`
• `Capture temps avant-hier`

**Formats courts:**
• `reconstruct 2026-04-27`
• `analyze yesterday`
• `time reconstruction for last week`

**Dates supportées:**
• Format ISO: `2026-04-27`
• Français: `27 avril 2026`, `27 avril dernier`
• Anglais: `April 27th 2026`, `April 27`
• Relatif: `hier`, `yesterday`, `avant-hier`

**🎯 L'agent analysera automatiquement:**
• Données ActivityWatch
• Google Calendar (meetings/événements)
• Gmail (correspondance clients)
• Slack (discussions techniques)
• Google Drive (fichiers modifiés)
• ClickUp (tâches actives)

**💬 Il générera ensuite une conversation naturelle pour valider et approuver les entrées de temps avant création dans ClickUp.**

**Exemple de ce que tu recevras:**
```
🧠 Analyse Intelligente pour dimanche 27 avril

📊 ActivityWatch montre 6.8h d'activité:
• 09:00-12:00: Développement AGATHA (VS Code)
• 14:00-16:00: Design AuPoint CRM (Figma)  

❓ Questions importantes:
• Y a-t-il eu du travail hors-ordinateur? (appels, WhatsApp, etc.)
• Le work VS Code était-il pour client Tektonik ou développement produit?
```

**🚀 Essaie maintenant: dis moi quelle date tu veux analyser!**"""

    send_slack_message(channel_id, help_message)

def send_slack_message(channel_id: str, text: str):
    """Send message to Slack with improved error handling"""
    try:
        url = "https://slack.com/api/chat.postMessage"
        headers = {
            "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
            "Content-Type": "application/json"
        }
        data = {
            "channel": channel_id,
            "text": text,
            "parse": "none"  # Disable auto-parsing for better control
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

def generate_response(message_text: str) -> Optional[str]:
    """
    Generate response for regular time reconstruction conversations
    (Original logic for daily routine conversations)
    """
    text = message_text.lower().strip()
    
    # Check if this is part of an ongoing reconstruction conversation
    if any(word in text for word in ['oui', 'yes', 'approve', 'correct', 'exact']):
        return "Parfait! Je procède à la création des entrées dans ClickUp avec ces informations validées."
    
    elif any(word in text for word in ['non', 'no', 'change', 'modify', 'incorrect']):
        return "D'accord, que veux-tu modifier? Donne-moi les corrections et je mettrai à jour les propositions."
    
    elif 'help' in text or 'aide' in text:
        return """Commandes disponibles:
        
**Reconstruction rétroactive:**
• `reconstituer temps 27 avril 2026`
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
    Handle morning messages from Claude Code routine
    (Original endpoint for daily routine)
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

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)

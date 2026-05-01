"""
Action Item Agent - Extracts tasks and action items from meetings
"""
from groq import Groq
import config.settings as settings
import json
import re

class ActionItemAgent:
    """Agent for extracting action items from meeting transcripts"""
    
    def __init__(self):
        """Initialize the action item agent with Groq client"""
        if not settings.GROQ_API_KEY:
            raise ValueError("GROQ_API_KEY not found in environment variables")
        
        # Initialize Groq client without proxy settings
        self.client = Groq(
            api_key=settings.GROQ_API_KEY,
            max_retries=3
        )
        self.model = settings.GROQ_MODEL
        print("[SUCCESS] Action Item Agent initialized")
    
    def extract_action_items(self, transcript):
        """
        Extract action items from meeting transcript
        
        Args:
            transcript: The meeting transcript text
        
        Returns:
            list: List of action items with task, owner, deadline, priority
        """
        try:
            prompt = f"""Analyze this meeting transcript and extract ALL action items, tasks, and commitments.

TRANSCRIPT:
{transcript}

For each action item, provide:
- task: Clear description of what needs to be done
- assignee_name: Person responsible (use "Unassigned" if not mentioned, do not guess)
- deadline: When it's due (use "Not specified" if not mentioned)
- confidence: high, medium, or low based on how explicit the task was
- evidence: A short quote from the transcript providing evidence

Return ONLY a valid JSON array of action items in this exact format:
[
  {{
    "task": "Description of task",
    "assignee_name": "Person name or 'Unassigned'",
    "deadline": "Date or timeframe",
    "confidence": "high/medium/low",
    "evidence": "Direct quote from transcript"
  }}
]

If no action items are found, return an empty array: []"""
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert at identifying action items, tasks, and commitments from meeting transcripts. Always return valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,  # Lower temperature for structured extraction
                max_tokens=2000
            )
            
            result_text = response.choices[0].message.content.strip()
            
            # Extract JSON from response (handle code blocks)
            json_match = re.search(r'\[.*\]', result_text, re.DOTALL)
            if json_match:
                json_text = json_match.group(0)
                action_items = json.loads(json_text)
            else:
                action_items = []
            
            # Add status field
            for item in action_items:
                item['status'] = 'pending'
            
            print(f"[SUCCESS] Extracted {len(action_items)} action items")
            return action_items
            
        except json.JSONDecodeError as e:
            print(f"[WARNING] JSON parsing error: {e}")
            print(f"Response was: {result_text}")
            return []
        except Exception as e:
            print(f"[ERROR] Action item extraction error: {e}")
            raise
    
    def categorize_action_items(self, action_items):
        """
        Categorize action items by priority and owner
        
        Args:
            action_items: List of action items
        
        Returns:
            dict: Categorized action items
        """
        categorized = {
            'by_priority': {'high': [], 'medium': [], 'low': []},
            'by_owner': {},
            'by_status': {'pending': [], 'in_progress': [], 'completed': []}
        }
        
        for item in action_items:
            # By priority
            priority = item.get('priority', 'medium')
            categorized['by_priority'][priority].append(item)
            
            # By owner
            owner = item.get('assignee_name', 'Unassigned')
            if owner not in categorized['by_owner']:
                categorized['by_owner'][owner] = []
            categorized['by_owner'][owner].append(item)
            
            # By status
            status = item.get('status', 'pending')
            categorized['by_status'][status].append(item)
        
        return categorized

"""
Summary Agent - Generates meeting summaries using Groq LLM
"""
from groq import Groq
import config.settings as settings
from datetime import datetime

class SummaryAgent:
    """Agent for generating meeting summaries"""
    
    def __init__(self):
        """Initialize the summary agent with Groq client"""
        if not settings.GROQ_API_KEY:
            raise ValueError("GROQ_API_KEY not found in environment variables")
        
        # Initialize Groq client without proxy settings
        self.client = Groq(
            api_key=settings.GROQ_API_KEY,
            max_retries=3
        )
        self.model = settings.GROQ_MODEL
        print("✓ Summary Agent initialized with Groq")
    
    def clean_transcript(self, raw_transcript: str, participants: str) -> str:
        """
        Post-Process the raw transcript to correct phonetic misspellings of participant names
        and lightly fix grammar without altering tone or over-summarizing.
        """
        try:
            print("🧹 Post-processing transcript for proper noun correction...")
            
            prompt = f"""You are an exact transcription editor. Your job is ONLY to fix phonetic misspellings of names and extremely obvious grammatical speech errors. 
DO NOT summarize the text. DO NOT alter the original tone, meaning, or dialog flow. 

Provided Participant Names that might have been misspelled:
{participants}

RAW TRANSCRIPT:
{raw_transcript}

Return ONLY the cleaned transcript. Do not add any introductory or concluding text."""
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a precise transcription editor. Make surgical spelling corrections and return only the raw text."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,  # extremely low to prevent hallucination/summarization
                max_tokens=min(settings.GROQ_MAX_TOKENS, 8000)
            )
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            print(f"❌ Transcript cleanup error: {e}")
            return raw_transcript # Fail gracefully

    def generate_summary(self, transcript, meeting_context=None):
        """
        Generate a comprehensive meeting summary
        
        Args:
            transcript: The meeting transcript text
            meeting_context: Optional dict with title, date, participants
        
        Returns:
            dict: Summary with key points, decisions, and next steps
        """
        try:
            # Build context
            context = ""
            if meeting_context:
                context = f"""Meeting Title: {meeting_context.get('title', 'Unknown')}
Date: {meeting_context.get('date', datetime.now().strftime('%Y-%m-%d'))}
Participants: {', '.join(meeting_context.get('participants', []))}

"""
            
            # Create prompt
            prompt = f"""{context}Please analyze this meeting transcript and provide a comprehensive summary.

TRANSCRIPT:
{transcript}

Provide a structured summary with:
1. **Overview**: Brief 2-3 sentence summary of the meeting
2. **Key Discussion Points**: Main topics discussed (bullet points)
3. **Decisions Made**: Important decisions (if any)
4. **Next Steps**: What happens next
5. **Important Mentions**: Notable quotes or critical information

Keep it clear, concise, and actionable."""
            
            # Get completion from Groq
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert meeting analyst. Create clear, structured summaries that highlight key information and action items."},
                    {"role": "user", "content": prompt}
                ],
                temperature=settings.GROQ_TEMPERATURE,
                max_tokens=settings.GROQ_MAX_TOKENS
            )
            
            summary_text = response.choices[0].message.content
            
            return {
                'summary': summary_text,
                'model': self.model,
                'generated_at': datetime.now().isoformat()
            }
            
        except Exception as e:
            print(f"❌ Summary generation error: {e}")
            raise
    
    def answer_question(self, transcript, question):
        """
        Answer a question - either about meetings (if transcript provided) or general knowledge
        
        Args:
            transcript: Meeting transcript or relevant context (empty string for general questions)
            question: User's question
        
        Returns:
            str: Answer to the question
        """
        try:
            if transcript and transcript.strip():
                # Answer based on meeting context
                prompt = f"""Based on the following meeting transcript, answer this question:

QUESTION: {question}

CONTEXT:
{transcript}

Provide a clear, concise answer based on the information in the transcript. If the information is not in the transcript, say so and provide a general answer if relevant."""
                
                system_msg = "You are a helpful assistant that answers questions about meetings based on transcripts. You can also provide general knowledge when meeting context doesn't contain the answer."
            else:
                # Answer as general question
                prompt = question
                system_msg = "You are a helpful AI assistant. Provide clear, accurate, and concise answers. Include definitions, examples, and explanations as needed."
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,  # Lower temperature for factual answers
                max_tokens=1000
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            print(f"❌ Question answering error: {e}")
            raise

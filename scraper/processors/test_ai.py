import os
import json
from dotenv import load_dotenv

# Load your API keys from .env
load_dotenv()

from google import genai
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

ANALYSIS_PROMPT = """You are an intelligence analyst specialising in cross-strait 
relations between the People's Republic of China and Taiwan. Analyse this article 
and return a JSON object with this structure:

{
  "title_en": "English title",
  "summary_en": "2-3 sentence summary",
  "topic_primary": "one of: MIL_EXERCISE, MIL_MOVEMENT, MIL_HARDWARE, DIP_STATEMENT, DIP_VISIT, DIP_SANCTIONS, ECON_TRADE, ECON_INVEST, POL_DOMESTIC, POL_UNIFICATION, INFO_WARFARE, LEGAL_GREY, HUMANITARIAN",
  "sentiment": "one of: escalatory, conciliatory, neutral, ambiguous",
  "sentiment_score": "float -1.0 to 1.0",
  "urgency": "one of: flash, priority, routine",
  "entities": [{"name": "...", "name_en": "...", "type": "person|military_unit|location|organisation", "role": "..."}],
  "is_escalation_signal": false,
  "confidence": 0.8
}

Return ONLY valid JSON."""


def analyse_article(title: str, content: str) -> dict:
    """Send an article to Gemini for analysis."""
    
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=f"{ANALYSIS_PROMPT}\n\nTITLE: {title}\n\nCONTENT:\n{content}",
        config={
            "response_mime_type": "application/json",
            "max_output_tokens": 2000
        }
    )
    
    return json.loads(response.text)


if __name__ == '__main__':
    # Test with a sample article
    test_title = "PLA conducts live-fire exercises near Taiwan"
    test_content = """The People's Liberation Army's Eastern Theatre Command 
    conducted live-fire military exercises in waters near Taiwan on Tuesday, 
    according to a statement from China's Ministry of National Defense. 
    The exercises involved naval vessels and aircraft from multiple branches. 
    Taiwan's Ministry of National Defense said it had detected the activity 
    and dispatched forces to monitor the situation."""
    
    print("Sending article to Gemini for analysis...\n")
    result = analyse_article(test_title, test_content)
    print(json.dumps(result, indent=2, ensure_ascii=False))
import os
from dotenv import load_dotenv
from src.errors import UserFacingError

load_dotenv()

def get_openai_api_key() -> str:
    load_dotenv(override=True)
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        raise UserFacingError(
            "OpenAI API key is not configured. Please set OPENAI_API_KEY in your .env file."
        )
    return key

BATCH_SIZE = 50
MAX_CONCURRENT_BATCHES = 5
MAX_FILE_ROWS = 50_000
MAX_FILE_SIZE_MB = 50

TEXT_COLUMN_KEYWORDS = ["text", "content", "comment", "description", "title", "review", "message", "body", "note", "feedback", "remark"]
METADATA_KEYWORDS = ["id", "uuid", "date", "time", "stamp", "created", "updated", "deleted", "status", "rating", "price", "code", "num", "count", "flag", "type", "url", "link", "email", "phone"]

LANGUAGE_MAP: dict[str, str] = {
    "chinese": "zh",
    "english": "en",
    "japanese": "ja",
    "korean": "ko",
    "french": "fr",
    "german": "de",
    "spanish": "es",
    "portuguese": "pt",
    "italian": "it",
    "russian": "ru",
    "arabic": "ar",
    "thai": "th",
    "vietnamese": "vi",
    "indonesian": "id",
    "malay": "ms",
    "dutch": "nl",
    "turkish": "tr",
    "polish": "pl",
    "swedish": "sv",
    "norwegian": "no",
    "danish": "da",
    "finnish": "fi",
    "czech": "cs",
    "hungarian": "hu",
    "romanian": "ro",
    "greek": "el",
    "hebrew": "he",
    "hindi": "hi",
    "bengali": "bn",
    "urdu": "ur",
}

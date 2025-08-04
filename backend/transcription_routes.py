from fastapi import APIRouter

router = APIRouter()

@router.get("/status")
def get_transcription_status():
    return {"status": "Transcription en cours"}

@router.get("/sections")
def get_transcription_sections():
    return {"sections": ["Introduction", "Débat", "Conclusion"]}
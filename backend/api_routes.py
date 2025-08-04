from fastapi import APIRouter

router = APIRouter()

@router.get("/dashboard-stats")
def dashboard_stats():
    return {"success": True, "data": {}}

@router.get("/articles/sources")
def articles_sources():
    return {"success": True, "sources": []}

@router.get("/articles")
def articles():
    return {"success": True, "articles": []}

@router.get("/search")
def search(q: str = ""):
    return {"success": True, "query": q, "results": []}

@router.get("/search/suggestions")
def suggestions(q: str = ""):
    return {"success": True, "query": q, "suggestions": []}

@router.get("/comments")
def comments():
    return {"success": True, "comments": []}

@router.get("/digest")
def digest():
    return {"success": True, "digest": {}}

@router.get("/scheduler/status")
def scheduler_status():
    return {"success": True, "scheduler": "ok"}

"""Isolated live-source server for Android emulator QA; no bot or admin access."""
from fastapi import FastAPI
from app.power_outages import router

app = FastAPI()
app.include_router(router)

@app.get('/health')
def health():
    return {'status': 'ok', 'mode': 'outage-qa-only'}

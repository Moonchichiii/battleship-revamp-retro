"""
Battleship Revamp - FastAPI + HTMX

A modern Battleship game built with FastAPI for performance and HTMX for interactivity.
"""

from fastapi import FastAPI

app = FastAPI(title="Battleship Revamp")

@app.get("/")
async def home():
    return {"message": "Welcome to Battleship Revamp!"}

"""
Patch to add frontend serving endpoint to main.py
Run this once to add the /app endpoint
"""

from pathlib import Path

# Read the current main.py
main_py_path = Path(__file__).parent / "main.py"
with open(main_py_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Check if endpoint already exists
if '@app.get("/app")' in content or 'serve_frontend' in content:
    print("✅ Frontend endpoint already exists!")
    exit(0)

# Add the endpoint at the end
endpoint_code = '''

# Serve frontend HTML
@app.get("/app")
async def serve_frontend():
    """Serve the frontend HTML application"""
    frontend_path = Path(__file__).parent.parent / "frontend" / "index.html"
    if not frontend_path.exists():
        raise HTTPException(status_code=404, detail="Frontend not found")
    return FileResponse(frontend_path)
'''

# Append to file
with open(main_py_path, 'a', encoding='utf-8') as f:
    f.write(endpoint_code)

print("✅ Frontend endpoint added successfully!")
print("   Access the app at: http://localhost:8000/app")

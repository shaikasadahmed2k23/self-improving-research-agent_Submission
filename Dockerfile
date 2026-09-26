# Hugging Face Spaces (Docker SDK) image for the Streamlit app. Also runs locally:
#   docker build -t research-agent . && docker run -p 8501:8501 --env-file .env research-agent
FROM python:3.11-slim

# Spaces run the container as user 1000
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user PATH=/home/user/.local/bin:$PATH PYTHONUNBUFFERED=1
WORKDIR /home/user/app

COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

COPY --chown=user . .
# Seed memory: lessons, trusted sources and runs learned during development (the Space disk resets on restart)
RUN mkdir -p data/traces reports && cp samples/seed_memory.db data/agent_memory.db

EXPOSE 8501
HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')"
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]

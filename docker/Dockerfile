FROM python:3.13-slim

WORKDIR /app

RUN \
  apt-get update && \
  apt-get install -y \
    curl \
    && \
  rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY \
  --exclude=.git \
  --exclude=__py_cache__ \
  . .

VOLUME /apps/data

EXPOSE 8501/tcp

HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/healt

CMD [ "streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0", "--browser.gatherUsageStats=false" ]

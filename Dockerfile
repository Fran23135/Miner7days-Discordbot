FROM python:3.14-slim
WORKDIR /app
RUN apt-get update && apt-get install -y git && apt-get install -y nodejs npm && apt-get install -y libopus0 ffmpeg
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["python", "main.py"]

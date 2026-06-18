FROM python:3.14-slim
WORKDIR /DisBot
RUN apt-get update && apt-get install -y git
COPY requirements.txt .
RUN pip install -r requirements.txt
RUN apt-get update && apt-get install -y nodejs
COPY . .
CMD ["python", "main.py"]

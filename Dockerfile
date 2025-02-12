FROM python:3.10.13-slim
WORKDIR /app

RUN apt-get update && apt-get install -y git

COPY requirements.txt requirements.txt
RUN pip3 install -r requirements.txt

COPY . .

CMD ["sh", "start.sh"]
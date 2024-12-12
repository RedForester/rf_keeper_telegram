FROM python:3.7.5-slim-buster

WORKDIR /rf-keeper-telegram
COPY . .
RUN pip install -r requirements.txt

ENV PYTHONPATH /rf-keeper-telegram

CMD ["python", "./app/main.py" ]
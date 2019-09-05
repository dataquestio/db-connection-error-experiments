FROM python:3

RUN pip install psycopg2

ADD db.py /

CMD ["python", "/db.py"]
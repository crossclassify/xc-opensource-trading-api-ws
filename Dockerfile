FROM python:3.8
LABEL maintainer="Clay yd"

RUN mkdir -p /usr/src/app
WORKDIR /usr/src/app

COPY requirements.txt /usr/src/app/
RUN pip install -r requirements.txt

COPY server.py /usr/src/app
# COPY key.json /usr/src/app

EXPOSE 9000
CMD ["python", "server.py"]
FROM python
ENV PYTHONUNBUFFERED 1
ADD . /todo1
WORKDIR /todo1
RUN pip install -r requirements.txt
CMD [ "slave.py" ]

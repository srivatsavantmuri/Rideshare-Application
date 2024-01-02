#!/usr/bin/env python
import pika
import uuid
import sys
import json
import math
from flask import * 
from flask import request
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import *
from sqlalchemy import exc
from datetime import datetime
import requests
import threading
import docker
import logging
from kazoo.client import KazooClient
from kazoo.client import KazooState


logging.basicConfig()
zk = KazooClient(hosts='zoo:2181')
zk.start()

zk.delete("/worker", recursive=True)
zk.delete("/master", recursive=True)
zk.ensure_path("/worker")
zk.ensure_path("/master")



app = Flask(__name__)
app.config['JSON_SORT_KEYS'] = False

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///requestcount.db'
 
db = SQLAlchemy(app)
engine = create_engine('sqlite:///requestcount.db?check_same_thread=False')
connection = engine.connect()
client = docker.from_env()

class ReqCount(db.Model):
	__tablename__ = 'ReqCount'
	rowid = db.Column(db.Integer, primary_key = True, autoincrement=True)
	content = db.Column(db.String(50))

class QueryTable(db.Model):
	__tablename__ = 'QueryTable'
	rowid = db.Column(db.Integer, primary_key = True, autoincrement=True)
	query = db.Column(db.String(500))

db.create_all()

scale = None
childList = []
workerCount = 0

def IncrementCount():
	row = ReqCount(content="new row")
	db.session.add(row)
	db.session.commit()

def getCount():
	query= "SELECT COUNT(*) from ReqCount"
	result = connection.execute(query)
	res = [dict(x) for x in result]
	count = res[0]["COUNT(*)"]
	return count

def resetCount():
	query= "DELETE from ReqCount"
	result = connection.execute(query)

def scale():
	global workerCount
	count = getCount()
	print("count = ",count)
	num = 0
	if count == 0:
		num = 2
	else:
		num = math.ceil(count/20)+1
	print("num = ",num)
	spawnContainers(num)
	resetCount()
	workerCount = num

def spawnContainers(num):
	l = client.containers.list(filters = {"ancestor": "worker:latest"})
	currentNum = len(l)
	if (currentNum < num):
		newnum = num-currentNum
		for i in range(newnum):
			container = client.containers.run(image = "worker:latest",network_mode = "ccproject_default",links = {"rmq":"rmq","zoo":"zoo"},command = "python slave.py",environment = {"PYTHONUNBUFFERED":"1"},volumes = {'/var/run/docker.sock':{'bind':'/var/run/docker.sock','mode':'rw'}},detach=True)
	elif (currentNum > num):
		global scale
		scale = True
		diffnum = currentNum-num
		containerPID = getContainerPid()
		numslaves = len(containerPID.keys())
		targetpid = sorted(containerPID.values(),reverse=True)[:diffnum]
		containerNames = []
		for i in targetpid:
			for key,value in containerPID.items():
				if value == i:
					containerNames.append(key)
		for name in containerNames:
			if (numslaves<2):
				print("Can not delete Master")
				break
			elif (numslaves == 2):
				container = client.containers.get(name)
				container.kill()
				print("One slave must be running at all times... starting new slave")
				container = client.containers.run(image = "worker:latest",network_mode = "ccproject_default",links = {"rmq":"rmq","zoo":"zoo"},command = "python slave.py",environment = {"PYTHONUNBUFFERED":"1"},volumes = {'/var/run/docker.sock':{'bind':'/var/run/docker.sock','mode':'rw'}},detach=True)
			else:
				container = client.containers.get(name)
				container.kill()
				numslaves -= 1
	printContainers()


def getContainerPid():
    l = client.containers.list(filters = {"ancestor": "worker:latest"})
    containerPID= {}
    for i in l:
        containerPID[i.name] = int(i.top()["Processes"][0][1])
    return containerPID

def set_interval(func, sec):
    def func_wrapper():
        set_interval(func, sec)
        func()
    t = threading.Timer(sec, func_wrapper)
    t.start()
    return t


def printContainers():
    l = client.containers.list(filters = {"ancestor": "worker:latest"})
    containerPID= {}
    for i in l:
        containerPID[i.name] = int(i.top()["Processes"][0][1])
        print("name -> ",i.name)
        print("container ID -> ",i.id)
        print(i.top())
        print()
    print(containerPID)
    print()


class Readreq(object):

    def __init__(self):
        self.connection = pika.BlockingConnection(
            pika.ConnectionParameters(host='rmq'))

        self.channel = self.connection.channel()
        result = self.channel.queue_declare(queue='res_queue', durable=True)

        # result = self.channel.queue_declare(queue='', exclusive=True)
        self.callback_queue = result.method.queue

        self.channel.basic_consume(
            queue=self.callback_queue,
            on_message_callback=self.on_response,
            auto_ack=True)

    def on_response(self, ch, method, props, body):
        if self.corr_id == props.correlation_id:
            self.response = body

    def call(self, query):
        self.response = None
        self.corr_id = str(uuid.uuid4())
        self.channel.basic_publish(
            exchange='',
            routing_key='read_queue',
            properties=pika.BasicProperties(
                reply_to=self.callback_queue,
                correlation_id=self.corr_id,
                delivery_mode=2,
            ),
            body=json.dumps(query))
        while self.response is None:
            self.connection.process_data_events()
        self.connection.close()
        return json.loads(self.response)




### API Handlers ###


### Write API ###
@app.route("/api/v1/db/write",methods=["POST"])
def write_db():
    print("in write api")
    connection = pika.BlockingConnection(
        pika.ConnectionParameters(host='rmq'))
    channel = connection.channel() 
    channel.queue_declare(queue='write_queue', durable=True)
    tbl = request.get_json()["table"]
    data = request.get_json()["insert"]
    flag = request.get_json()["dflag"]
    message = {"table":tbl,"insert":data,"dflag":flag}
    channel.basic_publish(
	    exchange='',
	    routing_key='write_queue',
	    body=json.dumps(message),
	    properties=pika.BasicProperties(
		delivery_mode=2,  # make message persistent
	    ))
    connection.close()
    print(" [x] Sent %r" % message)
    row = QueryTable(query=json.dumps(message))
    db.session.add(row)
    db.session.commit()
    return "Success",200

### Read API ###
@app.route("/api/v1/db/read",methods=["POST"])
def read_db():
    print("in read api")
    IncrementCount()
    query = request.get_json()["query"]
    message = {"query":query}
    readreq = Readreq()
    response = readreq.call(message)
    print(" [x] Sent %r" % message)
    return response

### List workers API ###
@app.route("/api/v1/worker/list",methods=["GET"])
def get_worker_list():
	l = client.containers.list(filters = {"ancestor": "worker:latest"})
	workerList = []
	for i in l:
		workerList.append(int(i.top()["Processes"][0][1]))
	workerList.sort()
	return jsonify(workerList),200

### crash slave API ###
@app.route("/api/v1/crash/slave",methods=["POST"])
def crash_slave():
	containerPID = getContainerPid()
	numslaves = len(containerPID.keys())
	targetpid = sorted(containerPID.values(),reverse=True)[0]
	containerName = ''
	for key,value in containerPID.items():
		if value == targetpid:
			containerName=key
	container = client.containers.get(containerName)
	container.kill()
	li = [targetpid]
	return jsonify(li),200

### crash master API ###
@app.route("/api/v1/crash/master",methods=["POST"])
def crash_master():
	containerPID = getContainerPid()
	numslaves = len(containerPID.keys())
	targetpid = sorted(containerPID.values())[0]
	containerName = ''
	for key,value in containerPID.items():
		if value == targetpid:
			containerName=key
	container = client.containers.get(containerName)
	container.kill()
	li = [targetpid]
	return jsonify(li),200
 
### getDataForNewSlave ### 
@app.route("/api/v1/getDataForNewSlave",methods=["GET"])
def getDataForNewSlave():
    query = "SELECT query FROM QueryTable"
    result = connection.execute(query)
    res = [dict(x) for x in result]
    print(json.dumps(res))
    return json.dumps(res)

## clearDB API ###
@app.route("/api/v1/db/clear",methods=["POST"])
def clear_db():
	print("in clear DB api")
	connection = pika.BlockingConnection(pika.ConnectionParameters(host='rmq'))
	channel = connection.channel() 
	channel.queue_declare(queue='write_queue', durable=True)
	query = "CLEAR DB"
	message = {"table":"All","insert": query,"dflag":True}
	channel.basic_publish(
		exchange='',
		routing_key='write_queue',
		body=json.dumps(message),
		properties=pika.BasicProperties(
		delivery_mode=2,  # make message persistent
		))
	connection.close()
	print(" [x] Sent %r" % message)
	row = QueryTable(query=json.dumps(message))
	db.session.add(row)
	db.session.commit()
	return "Success",200


### Children watch for high availability ###
@zk.ChildrenWatch("/worker")
def watch_children(children):
	global scale
	global childList
	global workerCount
	print("Children are now: %s" % children)
	li = [int(i) for i in children]
	if (len(li)>0):
		master = min(li)
		string = str(master)
		bstr = bytes(string,'utf-8')
		zk.set("/master", bstr)
		print("New master is ",master)
	if (len(li) < len(childList)):
		print("scale = ",scale)
		if (scale == True):
			if (len(li)>workerCount):
				print("Auto scale in progress")
			else:
				scale = False
		else:
			container = client.containers.run(image = "worker:latest",network_mode = "ccproject_default",links = {"rmq":"rmq","zoo":"zoo"},command = "python slave.py",environment = {"PYTHONUNBUFFERED":"1"},volumes = {'/var/run/docker.sock':{'bind':'/var/run/docker.sock','mode':'rw'}},detach=True)
			print("Started new container")
	childList = li



if(__name__=="__main__"):
	printContainers()
	timer = set_interval(scale,120)
	app.run(host="0.0.0.0", debug=False) 

    


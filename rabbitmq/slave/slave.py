#!/usr/bin/env python

### import modules ###

import pika
import time
import sys
import os 
import docker
from threading import Thread
from multiprocessing import Process

from kazoo.client import KazooClient
from kazoo.client import KazooState
from flask import * 
from flask import request
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import *
from sqlalchemy import exc
from datetime import datetime
import requests
from numpy import genfromtxt

### common part ###

client = docker.from_env()
containerid = os.uname()[1]
container = client.containers.get(containerid)
pid = container.top()["Processes"][0][1]
zkname = "/worker/"+pid

import logging
logging.basicConfig()
zk = KazooClient(hosts='zoo:2181')
zk.start()

zk.ensure_path("/worker")
zk.ensure_path("/master")

try:
	zk.create(zkname,ephemeral=True)
	print("Created new znode -> ",zkname)
except:
	print("Znode creation failed")

app = Flask(__name__)
app.config['JSON_SORT_KEYS'] = False

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
 
db = SQLAlchemy(app)


class Area(db.Model):
	__tablename__ = 'Area'
	areano = db.Column(db.Integer, primary_key = True)
	areaname = db.Column(db.String(50))

class Rides(db.Model):
	__tablename__ = 'Rides'
	rideId = db.Column(db.Integer, primary_key = True)
	created_by = db.Column(db.String(50))
	timestamp = db.Column(db.DateTime)
	source = db.Column(db.Integer, db.ForeignKey('Area.areano'))
	dest = db.Column(db.Integer, db.ForeignKey('Area.areano'))

class UserRides(db.Model):
	__tablename__ = 'UserRides'
	rideId = db.Column(db.Integer, db.ForeignKey('Rides.rideId'), primary_key = True)
	username = db.Column(db.String(50), primary_key = True)

class ReqTable(db.Model):
	__tablename__ = 'ReqTable'
	rowid = db.Column(db.Integer, primary_key = True, autoincrement=True)
	content = db.Column(db.String(50))

class ReqTable1(db.Model):
	__tablename__ = 'ReqTable1'
	rowid = db.Column(db.Integer, primary_key = True, autoincrement=True)
	content = db.Column(db.String(50))

class User(db.Model):
	__tablename__ = 'User'
	name = db.Column(db.String(50), primary_key = True)
	password = db.Column(db.String(40))

db.create_all()

def Load_Data(file_name):
	data = genfromtxt(file_name,delimiter=',',converters={1: lambda s: str(s)})
	return data.tolist()
file_name = "AreaNameEnum.csv"
data = Load_Data(file_name)
try:
	for i in data:
		record = Area(areano=i[0],areaname=i[1])
		db.session.add(record)
	db.session.commit()
except:
	db.session.rollback()

### Run a query for read API ###
def runquery(query):
	res = {}
	engine = create_engine('sqlite:///database.db')
	connection = engine.connect()
	result = connection.execute(query)
	res = [dict(x) for x in result]
	return json.dumps(res)

### Update Database ###
def UpdateDb(body):
	tbl = json.loads(body)["table"]
	data = json.loads(body)["insert"]
	flag = json.loads(body)["dflag"]
	if not flag:
		if (tbl == "User"):
			try:
				user = User(name=data[0], password=data[1])
				db.session.add(user)
				db.session.commit()
			except exc.IntegrityError as e:
				db.session().rollback()
		elif (tbl == "ReqTable1"):
			try:
				row = ReqTable1(content=data[0])
				db.session.add(row)
				db.session.commit()
			except exc.IntegrityError as e:
				db.session().rollback()
		elif (tbl == "Rides"):
			frmt = "%d-%m-%Y:%S-%M-%H"
			date = datetime.strptime(data[1],frmt)	
			row = Rides(created_by=data[0],timestamp=date,source=int(data[2]),dest=int(data[3]))
			db.session.add(row)
			db.session.commit()
		elif (tbl == "UserRides"):
			try:
				row = UserRides(rideId=int(data[0]),username=data[1])
				db.session.add(row)
				db.session.commit()
			except exc.IntegrityError as e:
				db.session().rollback()
		elif (tbl == "ReqTable"):
			try:
				row = ReqTable(content=data[0])
				db.session.add(row)
				db.session.commit()
			except exc.IntegrityError as e:
				db.session().rollback()
	else:
		if data == "CLEAR DB":
			engine = create_engine('sqlite:///database.db')
			connection = engine.connect()
			query = "DELETE FROM UserRides"
			connection.execute(query)
			query2 = "DELETE FROM Rides"
			connection.execute(query2)
			query3 = "DELETE FROM User"
			connection.execute(query3)
			query4 = "DELETE FROM ReqTable"
			connection.execute(query4)
			query5 = "DELETE FROM ReqTable1"
			connection.execute(query5)
		else:
			res = {}
			engine = create_engine('sqlite:///database.db')
			connection = engine.connect()
			connection.execute(data)
	print(" [x] Update Db")


### Initial sync ###
def getDataFromOrch():
	r = requests.get(url='http://172.17.0.1:5000/api/v1/getDataForNewSlave')
	req = json.loads(r.text)
	print("Got Data from Orchestrator",flush=True)
	if len(req)>0:
		for i in req:
			body = i["query"]
			UpdateDb(body)


### Run Slave ###

def runAsSlave():
	print("Running as Slave")
	connection = pika.BlockingConnection(pika.ConnectionParameters(host='rmq'))
	channel = connection.channel()

	channel.queue_declare(queue='read_queue', durable=True)
	print(' [*] Waiting for messages. To exit press CTRL+C')

	channel.exchange_declare(exchange='syncQ', exchange_type='fanout')

	result = channel.queue_declare(queue='', exclusive=True)
	queue_name = result.method.queue

	channel.queue_bind(exchange='syncQ', queue=queue_name)

	def callback_read(ch, method, props, body):
	    print(" [x] Received %r" % body)
	    query = json.loads(body)["query"]
	    res = runquery(query)
	    ch.basic_publish(exchange='',
	    				routing_key=props.reply_to,
	    				properties=pika.BasicProperties(correlation_id = props.correlation_id,
	    					delivery_mode=2,),
	    				body=json.dumps(res))
	    print(" [x] Done")
	    ch.basic_ack(delivery_tag=method.delivery_tag)

	channel.basic_qos(prefetch_count=1)
	channel.basic_consume(queue='read_queue', on_message_callback=callback_read)
	print(" [x] Awaiting RPC requests")

	def callback_sync(ch, method, properties, body):
		print(' [*] got data in syncQ')
		UpdateDb(body)

	channel.basic_consume(queue=queue_name, on_message_callback=callback_sync, auto_ack=True)
	channel.start_consuming()
	connection.close()


### Run Master ### 

def runAsMaster():
	print("Running as Master")
	connection = pika.BlockingConnection(pika.ConnectionParameters(host='rmq'))
	channel = connection.channel()

	channel.queue_declare(queue='write_queue', durable = True)

	def callback(ch, method, properties, body):
		print(" [x] Received %r" % body)
		connection2 = pika.BlockingConnection(pika.ConnectionParameters(host='rmq'))
		channel2 = connection2.channel()

		channel2.exchange_declare(exchange='syncQ', exchange_type='fanout')

		UpdateDb(body)
		print(" [x] Done")

		channel2.basic_publish(exchange='syncQ', routing_key='', body=body)
		connection2.close()
		print(" [x] Sent data to syncQ")
		ch.basic_ack(delivery_tag=method.delivery_tag)

	channel.basic_consume(queue='write_queue', on_message_callback=callback)

	print(' [*] Waiting for messages. To exit press CTRL+C')
	channel.start_consuming()
	connection.close()

### Data Watch for toggling between master and slave ###

masterProcess = None
slaveProcess = None
role = None

@zk.DataWatch("/master")
def watch_node(data, stat):
	global pid
	global masterProcess
	global slaveProcess
	global role
	print("Data watch triggered")
	print("Version: %s, data: %s" % (stat.version, data.decode("utf-8")))
	master = data.decode("utf-8")
	if pid == master:
		if role == "master":
			print("already running as master")
		else:
			role = "master"
			try:
				slaveProcess.terminate()
				print("stopped slave process")
			except Exception as e:
				print("couldnt stop slave process")
				print(e)
			masterProcess = Process(target=runAsMaster)
			masterProcess.start()
			print("\nstarted master process\n")
	else:
		if role == "slave":
			print("already running as slave")
		else:
			role = "slave"
			try:
				masterProcess.terminate()
				print("stopped master process")
			except Exception as e:
				print("couldnt stop master process")
				print(e)
			slaveProcess = Process(target=runAsSlave)
			slaveProcess.start()
			print("\nstarted slave process\n")

if(__name__=="__main__"):
	getDataFromOrch()
	app.run(host="0.0.0.0", debug=False) 






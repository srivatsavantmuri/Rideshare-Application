from flask import * 
from flask import request
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import *
from sqlalchemy import exc
from datetime import datetime
import requests

app = Flask(__name__) 
app.config['JSON_SORT_KEYS'] = False

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'

def is_hex(val):
	try:
		a = int(val,16)
		return 1
	except:
		return 0

def increment():
	mydata = {"table":"ReqTable1","insert": ["test"],"dflag":False}
	r = requests.post("http://172.17.0.1:5000/api/v1/db/write",json=mydata)


@app.errorhandler(405)
def method_not_allowed(e):
        increment()
        return jsonify(error=str(e)),405

@app.route("/api/v1/_count",methods=["GET"])
def http_req():
	query= "SELECT COUNT(*) from ReqTable1"
	mydata = {"query":query}
	r = requests.post("http://172.17.0.1:5000/api/v1/db/read",json=mydata)
	res = json.loads(r.text)
	count = res[0]["COUNT(*)"]
	l = [count]
	return jsonify(l),200

@app.route("/api/v1/_count",methods=["DELETE"])
def http_req_del():
	query= "DELETE from ReqTable1"
	mydata = {"table":"ReqTable1","insert": query,"dflag":True}
	r = requests.post("http://172.17.0.1:5000/api/v1/db/write",json=mydata)
	return "200",200

### API 1 ###
@app.route("/api/v1/users",methods=["PUT"])
def add_user():
	increment()
	usr = request.get_json()["username"]
	pas = request.get_json()["password"]
	if(len(pas)!=40 or (is_hex(pas) != 1)):
		return Response("Password must be SHA1 hash hex only",status = 400,mimetype='application/text')
	else:
		query = "SELECT COUNT(*) from User where name = '"+usr+"'"
		mydata = {"query":query}
		r = requests.post("http://172.17.0.1:5000/api/v1/db/read",json=mydata)
		res = json.loads(r.text)
		count = res[0]["COUNT(*)"]
		if count==0:
			mydata = {"table":"User","insert":[usr,pas],"dflag":False}
			r = requests.post("http://172.17.0.1:5000/api/v1/db/write",json=mydata)
			return Response("Added user successfully",status = 201,mimetype='application/text')
		else:
			return Response("Username taken already",status = 400,mimetype='application/text')
		

### API 2 ###
@app.route("/api/v1/users/<username>",methods=["DELETE"])
def del_user(username):
	increment()
	query = "SELECT COUNT(*) from User where name = '"+username+"'"
	mydata = {"query":query}
	r = requests.post("http://172.17.0.1:5000/api/v1/db/read",json=mydata)
	res = json.loads(r.text)
	count = res[0]["COUNT(*)"]
	if count==0:
		return Response("User does not exist",status = 400,mimetype='application/text')
	else:
		query = "DELETE from User where name = '"+username+"'"
		mydata = {"table":"User","insert": query,"dflag":True}
		r = requests.post("http://172.17.0.1:5000/api/v1/db/write",json=mydata)
		return Response("User deleted successfully",status = 200,mimetype='application/text')
		

### API 3 ###
@app.route("/api/v1/users",methods=["GET"])
def get_user():
	increment()
	query = "SELECT name from User "
	mydata = {"query":query}
	r = requests.post("http://172.17.0.1:5000/api/v1/db/read",json=mydata)
	res = json.loads(r.text)
	l = []
	for i in res:
			name = i["name"]
			l.append(name)
	return jsonify(l),200

	

## clearDB API ###
@app.route("/api/v1/db/clear",methods=["POST"])
def clear_db():
	#increment()
	query = "CLEAR DB"
	mydata = {"table":"All","insert": query,"dflag":True}
	r = requests.post("http://172.17.0.1:5000/api/v1/db/write",json=mydata)
	return "200"

# @app.route('/',methods=["GET"])
# def adduser():
# 	return jsonify("in docker2")

if(__name__=="__main__"):
    app.run(host="0.0.0.0", port="5002", debug=True)

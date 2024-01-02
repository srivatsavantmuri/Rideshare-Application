from flask import * 
from flask import request
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import *
from sqlalchemy import exc
from datetime import datetime
import requests
from numpy import genfromtxt

app = Flask(__name__)
app.config['JSON_SORT_KEYS'] = False

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'

def checkloc(source,dest):
	query1 = "SELECT COUNT(*) from Area where areano = '"+source+"'"
	mydata1 = {"query":query1}
	r1 = requests.post("http://172.17.0.1:5000/api/v1/db/read",json=mydata1)
	res1 = json.loads(r1.text)
	count1 = res1[0]["COUNT(*)"]
	query2 = "SELECT COUNT(*) from Area where areano = '"+dest+"'"
	mydata2 = {"query":query2}
	r2 = requests.post("http://172.17.0.1:5000/api/v1/db/read",json=mydata2)
	res2 = json.loads(r2.text)
	count2 = res2[0]["COUNT(*)"]
	if (count1 == 0 or count2 == 0):
		return 0
	else:
		return 1

def getusers():
	read_req=requests.get(url='http://172.17.0.1:5002/api/v1/users')
	res = json.loads(read_req.text)
	return res

def increment():
	mydata = {"table":"ReqTable","insert": ["test"],"dflag":False}
	r = requests.post("http://172.17.0.1:5000/api/v1/db/write",json=mydata)


@app.errorhandler(405)
def method_not_allowed(e):
        increment()
        return jsonify(error=str(e)),405
                       
@app.route("/api/v1/_count",methods=["GET"])
def http_req():
	query= "SELECT COUNT(*) from ReqTable"
	mydata = {"query":query}
	r = requests.post("http://172.17.0.1:5000/api/v1/db/read",json=mydata)
	res = json.loads(r.text)
	count = res[0]["COUNT(*)"]
	l = [count]
	return jsonify(l),200

@app.route("/api/v1/_count",methods=["DELETE"])
def http_req_del():
	query= "DELETE from ReqTable"
	mydata = {"table":"ReqTable","insert": query,"dflag":True}
	r = requests.post("http://172.17.0.1:5000/api/v1/db/write",json=mydata)
	return "200",200

### API 3 ###
@app.route("/api/v1/rides",methods=["POST"])
def create_ride():
	increment()
	create = request.get_json()["created_by"]
	time = request.get_json()["timestamp"]
	src = request.get_json()["source"]
	dst = request.get_json()["destination"]
	usrs = getusers()
	if create not in usrs:
		return Response("Given username does not exist",status = 400,mimetype='application/text')
	else:
		if(checkloc(src,dst)):
			mydata = {"table":"Rides","insert":[create,time,src,dst],"dflag":False}
			r = requests.post("http://172.17.0.1:5000/api/v1/db/write",json=mydata)
			query = "SELECT rideId FROM Rides where created_by = '"+create+"'"
			qdata = {"query":query}
			q = requests.post("http://172.17.0.1:5000/api/v1/db/read",json=qdata)
			qt = q.text
			json_data = json.loads(qt)
			ride = 1
			for item in json_data:
				print("rideid is ",item["rideId"])
				ride = item["rideId"]
				print("ride var is ",ride)
			mydata1 = {"table":"UserRides","insert":[ride,create],"dflag":False}
			r1 = requests.post("http://172.17.0.1:5000/api/v1/db/write",json=mydata1)
			return Response("Created ride successfully",status = 201,mimetype='application/text')
		else:
			return Response("Wrong source or destination code",status = 400,mimetype='application/text')

	

### API 4 ###
@app.route("/api/v1/rides",methods=["GET"])
def up_rides():
	increment()
	d1 = datetime.now()
	s_d1 = str(d1)
	source = request.args.get("source")
	destination = request.args.get("destination")
	if(checkloc(source,destination)):
		query = "SELECT rideId,created_by,timestamp FROM Rides WHERE timestamp >= '"+s_d1+"' and source = '"+source+"' and dest = '"+destination+"'"
		mydata = {"query":query}
		r = requests.post("http://172.17.0.1:5000/api/v1/db/read",json=mydata)
		ch = r.text.replace("created_by","username")
		res = json.loads(ch)
		if len(res)==0:
			return Response("No rides found",status = 204,mimetype='application/text')
		else:
			for i in res:
				tm = i["timestamp"]
				newt = datetime.strptime(tm,"%Y-%m-%d %H:%M:%S.%f")
				convnewt = newt.strftime("%d-%m-%Y:%S-%M-%H")
				i["timestamp"] = convnewt
			return jsonify(res),200
	else:
		return Response("Wrong source or destination code",status = 400,mimetype='application/text')

### API 5 ###
@app.route("/api/v1/rides/<rideId>",methods=["GET"])
def ride_details(rideId):
	increment()
	query = "SELECT created_by,source,dest,timestamp from Rides where rideId = '"+rideId+"'"
	mydata = {"query":query}
	r = requests.post("http://172.17.0.1:5000/api/v1/db/read",json=mydata)
	res = json.loads(r.text)
	if len(res)==0:
		return Response("Invalid Ride ID",status = 400,mimetype='application/text')
	else:
		query2 = "SELECT username from UserRides where rideId = '"+rideId+"'"
		mydata2 = {"query":query2}
		r2 = requests.post("http://172.17.0.1:5000/api/v1/db/read",json=mydata2)
		res2 = json.loads(r2.text)
		usrs = []
		for i in res2:
			name = i["username"]
			usrs.append(name)
		tm = res[0]["timestamp"]
		newt = datetime.strptime(tm,"%Y-%m-%d %H:%M:%S.%f")
		convnewt = newt.strftime("%d-%m-%Y:%S-%M-%H")
		returnjson = {"rideId":rideId,"created_by":res[0]["created_by"],"users":usrs,"timestamp":convnewt,"source":res[0]["source"],"destination":res[0]["dest"]}
		return jsonify(returnjson),200

### API 6 ###
@app.route("/api/v1/rides/<rideId>",methods=["POST"])
def addusrride(rideId):
	increment()
	usn = request.get_json()["username"]
	query = "SELECT COUNT(*) from Rides where rideId = '"+rideId+"'"
	mydata = {"query":query}
	r = requests.post("http://172.17.0.1:5000/api/v1/db/read",json=mydata)
	res = json.loads(r.text)
	count = res[0]["COUNT(*)"]
	if count==0:
		return Response("Invalid rideId",status = 400,mimetype='application/text')
	else:
		usrs = getusers()
		if usn not in usrs:
			return Response("Username does not exist",status = 400,mimetype='application/text')
		else:
			query1 = "SELECT COUNT(*) from UserRides where rideId = '"+rideId+"' and username = '"+usn+"'"
			mydata1 = {"query":query1}
			r1 = requests.post("http://172.17.0.1:5000/api/v1/db/read",json=mydata1)
			res1 = json.loads(r1.text)
			count1 = res1[0]["COUNT(*)"]
			if count1 == 0:
				mydata3 = {"table":"UserRides","insert":[rideId,usn],"dflag":False}
				r3 = requests.post("http://172.17.0.1:5000/api/v1/db/write",json=mydata3)
				return Response("Added user to ride",status = 200,mimetype='application/text')
			else:
				return Response("User already added to the ride",status = 400,mimetype='application/text')

##API 7 ##
@app.route("/api/v1/rides/<rideId>",methods=["DELETE"])
def del_ride(rideId):
	increment()
	query3= "SELECT COUNT(*) from Rides where rideId = '"+rideId+"'"
	mydata3 = {"query":query3}
	r3= requests.post("http://172.17.0.1:5000/api/v1/db/read",json=mydata3)
	res3 = json.loads(r3.text)
	count = res3[0]["COUNT(*)"]
	if count==0:
		return Response("Ride dosen't exist",status = 400,mimetype='application/text')
	else:
		query = "DELETE from UserRides where rideId = '"+rideId+"'"
		mydata = {"table":"UserRides","insert": query,"dflag":True}
		r = requests.post("http://172.17.0.1:5000/api/v1/db/write",json=mydata)
		query2 = "DELETE FROM Rides where rideId = '"+rideId+"'"
		mydata2 = {"table":"Rides","insert": query2,"dflag":True}
		r2 = requests.post("http://172.17.0.1:5000/api/v1/db/write",json=mydata2)
		return Response("Ride deleted successfully",status = 200,mimetype='application/text')
		

@app.route("/api/v1/rides/count",methods=["GET"])
def count_ride():
	increment()
	query= "SELECT COUNT(*) from Rides"
	mydata = {"query":query}
	r = requests.post("http://172.17.0.1:5000/api/v1/db/read",json=mydata)
	res = json.loads(r.text)
	count = res[0]["COUNT(*)"]
	l = [count]
	return jsonify(l)

## clearDB API ###
@app.route("/api/v1/db/clear",methods=["POST"])
def clear_db():
	#increment()
	query = "CLEAR DB"
	mydata = {"table":"All","insert": query,"dflag":True}
	r = requests.post("http://172.17.0.1:5000/api/v1/db/write",json=mydata)
	return "200"

### Test ###
# @app.route("/api/v1/area",methods=["GET"])
# def getarea():
# 	query= "SELECT * from Area"
# 	mydata = {"query":query}
# 	r= requests.post("http://127.0.0.1:5000/api/v1/db/read",json=mydata)
# 	return jsonify(r.text)


### clearDB API ###
# @app.route("/api/v1/db/clear",methods=["POST"])
# def clear_db():
# 	#increment()
# 	engine = create_engine('sqlite:///rides.db')
# 	connection = engine.connect()
# 	query = "DELETE FROM UserRides"
# 	connection.execute(query)
# 	query2 = "DELETE FROM Rides"
# 	connection.execute(query2)
# 	return "200"

# @app.route('/',methods=["GET"])
# def adduser():
# 	return "hello in Docker 01"

# @app.route('/redirect',methods=["GET"])
# def redirect():
# 	read_req=requests.get(url='http://172.17.0.1:8080/')
# 	data=read_req.json()
# 	return data

if(__name__=="__main__"):
    app.run(host="0.0.0.0", port="5001", debug=True)

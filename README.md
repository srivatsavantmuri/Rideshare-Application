The main objective of this project was to build a fault tolerant, highly available database as a service for the RideShare application which was built progressively in the assignments. Using this RideShare application users can book rides between two locations at a time of their choice. There are various types of requests which are handled such as requests to Add a New User, Delete an Existing User, Creating and Deleting a New Ride, etc. 
There were three Amazon EC2 instances which were used to deploy the project. The Load Balancer was also implemented to distribute the incoming HTTP requests to the Users and Rides instances. A message broker service(AMQP) was implemented using RabbitMQ. The Orchestrator is a Flask Application which is used to implement the various message queues such as ‘readQ’, ‘writeQ’, ‘syncQ’ and ‘responseQ’ using RabbitMQ. It is also responsible for bringing up new worker containers as and when desired. Zookeeper was also implemented for Fault Tolerance for the Slave and Master. The Orchestrator will keep count of the incoming HTTP requests for the db read APIs and depending on the count the orchestrator will scale up or scale down the slave workers, that is increase or decrease the number of slave worker containers for every two minutes.
The users and rides microservices were no longer using their own database but a DBaaS was used. DBaaS stands for ‘Database as a Service’ which provides all functionalities of a database. It also has various services running such as RabbitMQ, Zookeeper and Scaling Services. 

The following tools were used for building this project:

1. SqlAlchemy as our Database
2. RabbitMQ as a Message Broker
3. Zookeeper using Kazoo for Fault Tolerance
4. Flask to implement the API’s and to route the requests
5. Docker SDK to dynamically spawn and stop containers


ALGORITHM/DESIGN

The orchestrator exposes the DB read and write APIs which are used by the API handlers in Users and Rides containers. The implementation of read and write API in orchestrator is as follows:
Read API - The orchestrator publishes a request into a ‘read_queue’ which is consumed by slave workers in a round-robin fashion. The slaves publish a response back to the orchestrator in the ‘res_queue’. RPC objects are used to handle the read API.
Write API - The orchestrator publishes a request into the ‘write_queue’ which is consumed by the master worker only. The master updates its database and publishes the request further into the ‘syncQ’ exchange which is consumed by all the slave workers. Hence eventual consistency is attained. No response is sent back to the orchestrator.
For implementation of auto-scaling of workers, we are running an auto-scaling function in a separate thread in the orchestrator, which executes the function in intervals of two minutes. The auto-scaling function counts the number of read requests in the last two minutes and according to the count, scales up to create new workers or scales down to terminate existing workers using Docker SDK.
We used the kazoo library to implement the zookeeper part of the project. High availability for slaves and master using zookeeper was done as follows:
Two znode branches - ‘/worker’ and ‘/master’ are used.
Each worker creates a new ephemeral znode with the name “/worker/<pid>”.
The orchestrator has a children watch on ‘/worker’ branch which is triggered every time a new worker is started or an existing worker is stopped. Every time the children watch is triggered, the worker with the lowest pid is elected as the master. The data in  the master znode is set to the pid of the master.
Each worker has a data watch on the ‘/master’ znode and whenever this data watch is triggered, the worker compares its pid with the data in the master znode. If they are equal, the worker starts the master process. Otherwise it starts the slave process.
The high availability part is taken care of in the children watch in the orchestrator which starts a new worker every time an existing worker crashes. An exception to this is during the scale down process where a new worker does not have to be started. This is done using a ‘scale’ flag which is turned on during the scale down process.

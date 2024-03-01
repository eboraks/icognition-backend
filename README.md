# icognition-backend
The backend application for icognition

# Running with Docker
1. Build icogapi image using `docker build -t icogapi:v1 .`
1. Spin-up containers `docker-compose up -d` 

# Local Development
1. Create conda environment `conda create -n {NAME} python=3.12`
2. Install dependencies `pip install -r requirements.txt`
3. To run from vs code use launch.json. Ask for Eliran to share. 

# GCP Proxy Connection (not needed if using docker-databases)
* Command ./cloud-sql-proxy --port 3306 {connection_name}
* path '/home/eboraks/Projects/gcp-sql-proxy'
* Connect to DB: psql -h 127.0.0.1 -p 3306 -d test-db-eliran -U icog-db-user 

# Load env variable from .env in local. Ths mostly use for testing 
* export $(cat .env | xargs) && env

# icognition-backend
The backend application for icognition

# Python Environment & Local Development 
1. Install conda
1. Create conda environment `conda create -n {NAME} python=3.12`
2. Install dependencies `pip install -r requirements.txt`
3. To run from vs code use launch.json. Ask for Eliran to share. 


# Running with Docker
1. Build icogapi image using `docker build -t icogapi:latest .`
1. Spin-up containers `docker-compose up -d` 


# GCP Proxy Connection (not needed if using docker-databases)
* path '/home/eboraks/Projects/gcp-sql-proxy'
* Command ./cloud-sql-proxy --port 3306 {connection_name}
* Connect to DB: psql -h 127.0.0.1 -p 3306 -d icog_db -U icog-db-user -W Case2214 

# Load env variable from .env in local. Ths mostly use for testing 
* export $(cat .env | xargs) && env



## GCP
## STG DB: see .env files

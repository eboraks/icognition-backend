# icognition-backend
The backend application for icognition

# Python Environment & Local Development 
1. Install conda
1. Create conda environment `conda create -n {NAME} python=3.12`
2. Install dependencies `pip install -r requirements.txt`
3. To run from vs code use launch.json. Ask for Eliran to share. 


# Running with Docker
1. Spin-up containers `docker-compose up -d` 
2. DO NOT USE: Build icogapi image using `docker build -t icogapi:latest .`

# Run database migration
* Load env variable from .env in local. This is mostly used for testing.
* export $(cat .env | xargs) && env

* For local develop: See instructions in migration-local

* For stg on GCP: See instruction on in migration-stg and run the GCP DB proxy.  

## GCP Proxy Connection (not needed if using docker-databases)
* path '/home/eboraks/Projects/gcp-sql-proxy'
* Command ./cloud-sql-proxy --port 3306 {connection_name}
* Connect to DB: psql -h 127.0.0.1 -p 3306 -d icog-db -U user-icog-dev -W Case22145 

# Run application in VSCode
1. Associate the vscode with the python env created above. 
1.1 Within VSCode, press crtl + shift + p
1.2 Select: Python: Select Interpreter
1.3 Select the conda python envrionment create above. 

2. Make sure you have .vscode directory with launch.json and settings.json share from Google Drive. 

3. Run application (F5)


## GCP
## DB: see .env files
Server
psql-icog-dev
Case22145

User
user-icog-dev
Case22145

## GCP Fuse Mount to Bucket
1. gcloud auth application-default login
2. gcsfuse icog-dev-bucket-01 icog-dev-bucket-01
3. fusermount -u icog-dev-bucket-01
